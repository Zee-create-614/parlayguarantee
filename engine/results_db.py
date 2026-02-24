"""
ParlayGuarantee Results Database — Self-Learning Infrastructure
Stores every pick with all factor scores, actual outcomes, spread/ML/OU results.
Schema supports per-factor analysis for the learning engine.

Usage:
    from results_db import ResultsDB
    db = ResultsDB()
    db.store_pick(pick_data)
    db.get_factor_accuracy('rest_days', min_samples=20)
"""

import sqlite3
import json
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "learning.db"

# All 38 factor columns stored per pick (matches self_learner.py default_weights)
FACTOR_COLUMNS = [
    'season_win_pct', 'home_win_pct', 'away_win_pct', 'last_10_record',
    'last_5_record', 'offensive_rating', 'defensive_rating', 'net_rating',
    'pace', 'ppg', 'points_allowed',
    'rest_days', 'day_of_week', 'game_time', 'travel_distance',
    'timezone_change', 'days_since_last',
    'head_to_head', 'division_rivalry', 'conference_game',
    'strength_of_schedule', 'clutch_performance', 'turnover_diff',
    'rebound_diff', 'ft_rate_diff', 'three_pt_pct', 'assists_pg',
    'defensive_activity',
    'key_player_status', 'star_player_penalty',
    'line_movement', 'public_betting', 'closing_line_value',
    'home_court',
    'streak_diff', 'scoring_margin_trend', 'away_road_trip',
    'miles_traveled_diff', 'overtime_fatigue', 'revenge_game',
    'trap_game', 'altitude_factor', 'arena_hostility', 'marquee_matchup',
    'b2b_status', 'schedule_density', 'last_3_record',
    'oreb_diff', 'three_pt_volume',
]


class ResultsDB:
    """SQLite database for storing picks with full factor scores and outcomes."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()

        # Build factor columns SQL
        factor_cols = "\n".join(f"    f_{col} REAL," for col in FACTOR_COLUMNS)

        c.executescript(f"""
            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date TEXT NOT NULL,
                game_id TEXT,
                sport TEXT DEFAULT 'NBA',
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,

                -- Pick details
                pick_type TEXT NOT NULL,  -- 'spread', 'moneyline', 'over_under'
                picked_team TEXT,
                picked_side TEXT,         -- 'home'/'away' or 'over'/'under'
                spread_line REAL,
                total_line REAL,
                odds_american INTEGER,
                confidence REAL,
                upset_composite REAL,
                value_score REAL,
                tier TEXT,

                -- All factor scores
            {factor_cols}
                factors_json TEXT,        -- full JSON backup of all factors

                -- Actual outcomes (filled by results_scorer)
                home_score INTEGER,
                away_score INTEGER,
                actual_winner TEXT,
                actual_margin REAL,       -- home_score - away_score
                actual_total INTEGER,

                -- Result flags
                ml_correct INTEGER,       -- 1/0/NULL
                spread_correct INTEGER,   -- 1/0/NULL
                ou_correct INTEGER,       -- 1/0/NULL
                scored INTEGER DEFAULT 0, -- 1 when outcomes filled
                scored_at TEXT,

                -- Metadata
                engine_version TEXT,
                weight_snapshot TEXT,      -- JSON of weights used at pick time
                created_at TEXT DEFAULT (datetime('now')),

                UNIQUE(game_date, home_team, away_team, pick_type, picked_team)
            );

            CREATE INDEX IF NOT EXISTS idx_picks_date ON picks(game_date);
            CREATE INDEX IF NOT EXISTS idx_picks_sport ON picks(sport);
            CREATE INDEX IF NOT EXISTS idx_picks_scored ON picks(scored);
            CREATE INDEX IF NOT EXISTS idx_picks_ml ON picks(ml_correct);
            CREATE INDEX IF NOT EXISTS idx_picks_spread ON picks(spread_correct);

            -- Weight history for rollback
            CREATE TABLE IF NOT EXISTS weight_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_date TEXT NOT NULL,
                weights_json TEXT NOT NULL,
                adjustments_json TEXT,
                metrics_json TEXT,
                is_dry_run INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            -- Per-factor accuracy tracking (materialized for fast queries)
            CREATE TABLE IF NOT EXISTS factor_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                bucket TEXT NOT NULL,       -- e.g. 'high', 'medium', 'low' or numeric range
                pick_type TEXT NOT NULL,     -- 'spread', 'moneyline', 'over_under'
                total_picks INTEGER DEFAULT 0,
                correct_picks INTEGER DEFAULT 0,
                accuracy REAL,
                avg_confidence REAL,
                last_updated TEXT DEFAULT (datetime('now')),
                UNIQUE(factor_name, bucket, pick_type)
            );

            -- Confidence calibration buckets
            CREATE TABLE IF NOT EXISTS calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                confidence_bucket TEXT NOT NULL,  -- e.g. '55-60', '60-65', '65-70'
                pick_type TEXT NOT NULL,
                total_picks INTEGER DEFAULT 0,
                correct_picks INTEGER DEFAULT 0,
                actual_accuracy REAL,
                last_updated TEXT DEFAULT (datetime('now')),
                UNIQUE(confidence_bucket, pick_type)
            );

            -- Audit log for all learning actions
            CREATE TABLE IF NOT EXISTS learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()
        logger.info(f"ResultsDB initialized at {self.db_path}")

    # ------------------------------------------------------------------
    # Store picks
    # ------------------------------------------------------------------
    def store_pick(self, pick: Dict[str, Any]) -> int:
        """Store a single pick with all factor scores. Returns row id."""
        factors = pick.get('factors', {})
        factor_vals = [factors.get(col) for col in FACTOR_COLUMNS]

        cols = [
            'game_date', 'game_id', 'sport', 'home_team', 'away_team',
            'pick_type', 'picked_team', 'picked_side', 'spread_line',
            'total_line', 'odds_american', 'confidence', 'upset_composite',
            'value_score', 'tier', 'factors_json', 'engine_version',
            'weight_snapshot',
        ]
        vals = [
            pick.get('game_date'), pick.get('game_id'), pick.get('sport', 'NBA'),
            pick.get('home_team'), pick.get('away_team'),
            pick.get('pick_type', 'moneyline'), pick.get('picked_team'),
            pick.get('picked_side'), pick.get('spread_line'),
            pick.get('total_line'), pick.get('odds_american'),
            pick.get('confidence'), pick.get('upset_composite'),
            pick.get('value_score'), pick.get('tier'),
            json.dumps(factors) if factors else None,
            pick.get('engine_version'), 
            json.dumps(pick.get('weight_snapshot')) if pick.get('weight_snapshot') else None,
        ]

        # Add factor columns
        f_cols = [f"f_{col}" for col in FACTOR_COLUMNS]
        all_cols = cols + f_cols
        all_vals = vals + factor_vals

        placeholders = ", ".join(["?"] * len(all_vals))
        col_names = ", ".join(all_cols)

        c = self.conn.cursor()
        c.execute(
            f"INSERT OR REPLACE INTO picks ({col_names}) VALUES ({placeholders})",
            all_vals
        )
        self.conn.commit()
        return c.lastrowid

    def store_picks_batch(self, picks: List[Dict[str, Any]]) -> int:
        """Store multiple picks. Returns count stored."""
        count = 0
        for p in picks:
            try:
                self.store_pick(p)
                count += 1
            except Exception as e:
                logger.error(f"Failed to store pick: {e}")
        return count

    # ------------------------------------------------------------------
    # Record outcomes
    # ------------------------------------------------------------------
    def record_outcome(self, game_date: str, home_team: str, away_team: str,
                       home_score: int, away_score: int):
        """Fill in actual scores and compute result flags for all pick types."""
        actual_winner = home_team if home_score > away_score else away_team
        actual_margin = home_score - away_score
        actual_total = home_score + away_score

        c = self.conn.cursor()
        # Get all picks for this game
        rows = c.execute("""
            SELECT id, pick_type, picked_team, picked_side, spread_line, total_line
            FROM picks WHERE game_date = ? AND home_team = ? AND away_team = ? AND scored = 0
        """, (game_date, home_team, away_team)).fetchall()

        for row in rows:
            pid, ptype, picked_team, picked_side, spread_line, total_line = (
                row['id'], row['pick_type'], row['picked_team'],
                row['picked_side'], row['spread_line'], row['total_line']
            )

            ml_correct = None
            spread_correct = None
            ou_correct = None

            # Moneyline
            if ptype in ('moneyline', 'straight'):
                ml_correct = 1 if picked_team == actual_winner else 0

            # Spread
            if ptype == 'spread' and spread_line is not None:
                if picked_side == 'home':
                    adjusted = actual_margin + spread_line
                else:
                    adjusted = -actual_margin + spread_line
                spread_correct = 1 if adjusted > 0 else (0 if adjusted < 0 else None)  # push = None

            # Over/Under
            if ptype == 'over_under' and total_line is not None:
                if picked_side == 'over':
                    ou_correct = 1 if actual_total > total_line else 0
                else:
                    ou_correct = 1 if actual_total < total_line else 0

            c.execute("""
                UPDATE picks SET home_score=?, away_score=?, actual_winner=?,
                    actual_margin=?, actual_total=?, ml_correct=?, spread_correct=?,
                    ou_correct=?, scored=1, scored_at=datetime('now')
                WHERE id = ?
            """, (home_score, away_score, actual_winner, actual_margin,
                  actual_total, ml_correct, spread_correct, ou_correct, pid))

        self.conn.commit()
        logger.info(f"Recorded outcomes for {away_team} @ {home_team} on {game_date}: "
                     f"{away_score}-{home_score}, updated {len(rows)} picks")
        return len(rows)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_factor_accuracy(self, factor_name: str, pick_type: str = 'moneyline',
                            min_samples: int = 10) -> List[Dict]:
        """Get accuracy breakdown by factor value buckets."""
        col = f"f_{factor_name}"
        c = self.conn.cursor()

        # Determine correct column
        correct_col = {'moneyline': 'ml_correct', 'spread': 'spread_correct',
                       'over_under': 'ou_correct'}.get(pick_type, 'ml_correct')

        rows = c.execute(f"""
            SELECT
                CASE
                    WHEN {col} IS NULL THEN 'missing'
                    WHEN {col} <= 0.33 THEN 'low'
                    WHEN {col} <= 0.66 THEN 'medium'
                    ELSE 'high'
                END as bucket,
                COUNT(*) as total,
                SUM({correct_col}) as correct,
                ROUND(AVG({correct_col}) * 100, 1) as accuracy,
                ROUND(AVG(confidence), 3) as avg_conf
            FROM picks
            WHERE scored = 1 AND {correct_col} IS NOT NULL
            GROUP BY bucket
            HAVING total >= ?
            ORDER BY accuracy DESC
        """, (min_samples,)).fetchall()

        return [dict(r) for r in rows]

    def get_calibration(self, pick_type: str = 'moneyline') -> List[Dict]:
        """Get confidence calibration: predicted vs actual accuracy."""
        correct_col = {'moneyline': 'ml_correct', 'spread': 'spread_correct',
                       'over_under': 'ou_correct'}.get(pick_type, 'ml_correct')
        c = self.conn.cursor()
        rows = c.execute(f"""
            SELECT
                CAST(ROUND(confidence * 20) * 5 AS INTEGER) || '-' ||
                CAST(ROUND(confidence * 20) * 5 + 5 AS INTEGER) as bucket,
                COUNT(*) as total,
                SUM({correct_col}) as correct,
                ROUND(AVG({correct_col}) * 100, 1) as actual_accuracy,
                ROUND(AVG(confidence) * 100, 1) as predicted_confidence
            FROM picks
            WHERE scored = 1 AND {correct_col} IS NOT NULL AND confidence IS NOT NULL
            GROUP BY CAST(ROUND(confidence * 20) AS INTEGER)
            HAVING total >= 5
            ORDER BY predicted_confidence
        """).fetchall()
        return [dict(r) for r in rows]

    def get_overall_stats(self, sport: str = None, days: int = None) -> Dict:
        """Get overall accuracy stats."""
        c = self.conn.cursor()
        where = ["scored = 1"]
        params = []
        if sport:
            where.append("sport = ?")
            params.append(sport)
        if days:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            where.append("game_date >= ?")
            params.append(cutoff)

        where_sql = " AND ".join(where)
        row = c.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(ml_correct) as ml_correct,
                ROUND(AVG(ml_correct) * 100, 1) as ml_accuracy,
                SUM(spread_correct) as spread_correct,
                ROUND(AVG(CASE WHEN spread_correct IS NOT NULL THEN spread_correct END) * 100, 1) as spread_accuracy,
                SUM(ou_correct) as ou_correct,
                ROUND(AVG(CASE WHEN ou_correct IS NOT NULL THEN ou_correct END) * 100, 1) as ou_accuracy
            FROM picks WHERE {where_sql}
        """, params).fetchone()
        return dict(row) if row else {}

    def get_unscored_dates(self) -> List[str]:
        """Get dates that have picks but no outcomes yet."""
        c = self.conn.cursor()
        rows = c.execute("""
            SELECT DISTINCT game_date FROM picks WHERE scored = 0
            ORDER BY game_date
        """).fetchall()
        return [r['game_date'] for r in rows]

    def log_action(self, action: str, details: Any = None):
        """Write to the audit log."""
        c = self.conn.cursor()
        c.execute("INSERT INTO learning_log (action, details) VALUES (?, ?)",
                  (action, json.dumps(details) if details else None))
        self.conn.commit()

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description='ParlayGuarantee Results Database')
    parser.add_argument('--stats', action='store_true', help='Show overall stats')
    parser.add_argument('--calibration', action='store_true', help='Show confidence calibration')
    parser.add_argument('--factor', type=str, help='Show accuracy for a specific factor')
    parser.add_argument('--unscored', action='store_true', help='Show dates needing scoring')
    parser.add_argument('--days', type=int, default=None, help='Limit to last N days')
    args = parser.parse_args()

    db = ResultsDB()

    if args.stats:
        stats = db.get_overall_stats(days=args.days)
        print(json.dumps(stats, indent=2))
    elif args.calibration:
        cal = db.get_calibration()
        print(f"{'Bucket':<12} {'Total':<8} {'Correct':<10} {'Actual%':<10} {'Predicted%':<12}")
        print("-" * 52)
        for row in cal:
            print(f"{row['bucket']:<12} {row['total']:<8} {row['correct']:<10} "
                  f"{row['actual_accuracy']:<10} {row['predicted_confidence']:<12}")
    elif args.factor:
        results = db.get_factor_accuracy(args.factor)
        print(f"Factor: {args.factor}")
        for row in results:
            print(f"  {row['bucket']}: {row['accuracy']}% ({row['total']} picks, avg conf {row['avg_conf']})")
    elif args.unscored:
        dates = db.get_unscored_dates()
        print(f"Unscored dates ({len(dates)}):")
        for d in dates:
            print(f"  {d}")
    else:
        parser.print_help()

    db.close()


if __name__ == '__main__':
    main()
