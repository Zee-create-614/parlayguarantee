"""
NHL Over/Under (Totals) Prediction Engine — ParlayGuarantee
Predicts whether NHL games go OVER or UNDER the posted total.

Factors:
1. Team goals for/against averages
2. Goaltending quality (save %)
3. Shot volume matchup
4. Special teams (PP% vs PK%)
5. Home/away scoring splits
6. Recent scoring trends (last 10)
7. Back-to-back / rest adjustment
8. Pace proxy (shots per game)
9. Defensive matchup quality
10. Line value (predicted vs posted)

Usage:
  python nhl_totals_engine.py
  python nhl_totals_engine.py --date 2026-02-20
"""

import sys
import json
import logging
import sqlite3
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nhl_data_fetcher import NHLDataFetcher, ODDS_API_KEY, ODDS_SPORT_KEY

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "nhl_totals.db"

# NHL league averages 2024-25
NHL_AVG_GPG = 3.10
NHL_AVG_TOTAL = 6.20  # combined per game
NHL_AVG_SPG = 30.0
NHL_AVG_SV = 0.905


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS totals_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date DATE,
        home_team TEXT, away_team TEXT,
        predicted_total REAL, posted_total REAL,
        pick TEXT, confidence REAL, edge REAL,
        factors TEXT,
        actual_total REAL, result TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(game_date, home_team, away_team)
    )""")
    conn.commit()
    conn.close()


class NHLTotalsEngine:
    """NHL Over/Under prediction engine."""

    def __init__(self):
        init_db()
        self.fetcher = NHLDataFetcher()

    def generate_picks(self, target_date=None) -> List[Dict]:
        """Generate over/under picks. Main entry point."""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = date.fromisoformat(target_date)

        # Load team stats
        self.fetcher.fetch_standings()

        # Fetch games with totals
        games = self.fetcher.fetch_games_from_odds(target_date)
        games_with_totals = [g for g in games if g.get('total')]

        if not games_with_totals:
            logger.warning(f"No NHL games with totals for {target_date}")
            return []

        predictions = []
        for g in games_with_totals:
            pred = self.predict_total(
                g['home_team'], g['away_team'],
                g['total'], g.get('spread', 0), target_date
            )
            pred['game_date'] = target_date.isoformat()
            pred['game_time'] = g.get('game_time', '')
            pred['sport'] = 'NHL'
            predictions.append(pred)
            self._store_prediction(pred)

        predictions.sort(key=lambda x: abs(x['edge']), reverse=True)
        return predictions

    def predict_total(self, home: str, away: str, posted_total: float,
                      spread: float = 0, game_date: date = None) -> Dict:
        """Core prediction for a single game's total."""
        h = self.fetcher.get_team_stats(home) or self._default()
        a = self.fetcher.get_team_stats(away) or self._default()

        h_gf = h.get('goals_per_game', NHL_AVG_GPG)
        h_ga = h.get('goals_against_per_game', NHL_AVG_GPG)
        a_gf = a.get('goals_per_game', NHL_AVG_GPG)
        a_ga = a.get('goals_against_per_game', NHL_AVG_GPG)

        factors = {}

        # --- Factor 1: Base total (offense vs defense matchup) ---
        home_expected = (h_gf + a_ga) / 2
        away_expected = (a_gf + h_ga) / 2
        raw_total = home_expected + away_expected

        # Regress toward league average
        regression = 0.45
        base_total = raw_total * (1 - regression) + NHL_AVG_TOTAL * regression
        factors['base_total'] = round(base_total, 2)
        factors['home_expected'] = round(home_expected, 2)
        factors['away_expected'] = round(away_expected, 2)

        # --- Factor 2: Goaltending (save %) ---
        h_sv = h.get('save_pct', NHL_AVG_SV)
        a_sv = a.get('save_pct', NHL_AVG_SV)
        # Better goalies = fewer goals
        goalie_adj = ((NHL_AVG_SV - h_sv) + (NHL_AVG_SV - a_sv)) * 30  # ~30 shots each
        base_total += goalie_adj
        factors['goalie_adj'] = round(goalie_adj, 2)

        # --- Factor 3: Shot volume ---
        h_sf = h.get('shots_per_game', NHL_AVG_SPG)
        a_sf = a.get('shots_per_game', NHL_AVG_SPG)
        avg_shots = (h_sf + a_sf) / 2
        shot_factor = avg_shots / NHL_AVG_SPG
        shot_adj = (shot_factor - 1.0) * 1.5  # more shots = more goals
        base_total += shot_adj
        factors['shot_volume_adj'] = round(shot_adj, 2)
        factors['avg_shots'] = round(avg_shots, 1)

        # --- Factor 4: Special teams matchup ---
        # High PP% vs low PK% = more goals
        h_pp = h.get('pp_pct', 0.215)
        a_pp = a.get('pp_pct', 0.215)
        h_pk = h.get('pk_pct', 0.795)
        a_pk = a.get('pk_pct', 0.795)
        # Each team gets ~3 PPs per game
        pp_goals_est = 3 * ((h_pp * (1 - a_pk) + a_pp * (1 - h_pk)) / 2)
        st_adj = (pp_goals_est - 0.15) * 2  # adjust vs average
        st_adj = max(-0.5, min(0.5, st_adj))
        base_total += st_adj
        factors['special_teams_adj'] = round(st_adj, 2)

        # --- Factor 5: Home scoring bump ---
        home_bump = 0.15  # home teams score ~0.15 more in NHL
        base_total += home_bump
        factors['home_bump'] = home_bump

        # --- Factor 6: Back-to-back fatigue ---
        b2b_adj = 0
        if game_date:
            h_b2b = self.fetcher.detect_back_to_back(home, game_date)
            a_b2b = self.fetcher.detect_back_to_back(away, game_date)
            if h_b2b or a_b2b:
                # Tired teams = weaker goaltending = slightly more goals sometimes
                # But also less energy on offense. Net effect is small.
                b2b_adj = 0.1 if (h_b2b and a_b2b) else 0.05
            factors['home_b2b'] = h_b2b if game_date else False
            factors['away_b2b'] = a_b2b if game_date else False
        base_total += b2b_adj
        factors['b2b_adj'] = round(b2b_adj, 2)

        # --- Factor 7: Blowout / close game adjustment ---
        spread_abs = abs(spread) if spread else 0
        if spread_abs >= 2.5:
            blowout_adj = -0.2  # big favorites → lower pace late
        elif spread_abs <= 0.5:
            blowout_adj = -0.15  # tight game → defensive grind
        else:
            blowout_adj = 0
        base_total += blowout_adj
        factors['blowout_adj'] = blowout_adj

        # --- Factor 8: Mean reversion ---
        mean_reversion = -0.3  # slight under bias correction
        base_total += mean_reversion
        factors['mean_reversion'] = mean_reversion

        predicted_total = round(base_total, 1)
        factors['predicted_total'] = predicted_total

        # --- Edge & Pick ---
        edge = round(predicted_total - posted_total, 1)
        factors['edge'] = edge

        if edge > 0:
            pick = "OVER"
        elif edge < 0:
            pick = "UNDER"
        else:
            pick = "PUSH"

        # Confidence
        edge_abs = abs(edge)
        if edge_abs >= 1.0:
            confidence = 0.78
            tier = "🔒 LOCK"
            pick_type = "LOCK"
        elif edge_abs >= 0.7:
            confidence = 0.68
            tier = "🎯 STRONG"
            pick_type = "VALUE"
        elif edge_abs >= 0.4:
            confidence = 0.60
            tier = "📊 VALUE"
            pick_type = "VALUE"
        elif edge_abs >= 0.2:
            confidence = 0.54
            tier = "📈 LEAN"
            pick_type = "LEAN"
        else:
            confidence = 0.50
            tier = "⚖️ COIN FLIP"
            pick_type = "LEAN"

        return {
            'home_team': home,
            'away_team': away,
            'predicted_total': predicted_total,
            'posted_total': posted_total,
            'pick': pick,
            'over_under_pick': f"{pick} {posted_total}",
            'edge': edge,
            'confidence': round(confidence * 100, 1),
            'value_score': round(edge_abs * 20, 1),
            'tier': tier,
            'pick_type': pick_type,
            'predicted_winner': f"{pick} {posted_total}",
            'factors': factors,
            'spread': spread,
        }

    def _default(self) -> Dict:
        return {
            'goals_per_game': NHL_AVG_GPG,
            'goals_against_per_game': NHL_AVG_GPG,
            'shots_per_game': NHL_AVG_SPG,
            'shots_against_per_game': NHL_AVG_SPG,
            'save_pct': NHL_AVG_SV,
            'pp_pct': 0.215, 'pk_pct': 0.795,
        }

    def _store_prediction(self, pred: Dict):
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""INSERT OR REPLACE INTO totals_predictions
                (game_date, home_team, away_team, predicted_total, posted_total,
                 pick, confidence, edge, factors)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (pred.get('game_date'), pred['home_team'], pred['away_team'],
                 pred['predicted_total'], pred['posted_total'],
                 pred['pick'], pred['confidence'], pred['edge'],
                 json.dumps(pred['factors'])))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store totals prediction: {e}")

    def score_results(self, target_date: date) -> Dict:
        """Score predictions against actual results."""
        games = self.fetcher.fetch_scoreboard(target_date)
        conn = sqlite3.connect(str(DB_PATH))
        preds = conn.execute(
            "SELECT home_team, away_team, pick, posted_total, edge FROM totals_predictions WHERE game_date = ?",
            (target_date.isoformat(),)).fetchall()
        conn.close()

        if not preds:
            return {'error': f'No predictions for {target_date}'}

        scores = {}
        for g in games:
            if g.get('status') == 'STATUS_FINAL':
                scores[g['home_team']] = g['home_score'] + g['away_score']

        correct = total = 0
        results = []
        for home, away, pick, posted, edge in preds:
            actual = scores.get(home)
            if actual is None:
                continue
            actual_result = "OVER" if actual > posted else "UNDER"
            hit = pick == actual_result
            total += 1
            if hit:
                correct += 1
            results.append({
                'matchup': f"{away} @ {home}",
                'pick': pick, 'posted': posted, 'actual': actual,
                'result': "✅" if hit else "❌",
            })

        return {
            'date': target_date.isoformat(),
            'results': results,
            'correct': correct, 'total': total,
            'accuracy': correct / total if total > 0 else 0,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    engine = NHLTotalsEngine()

    if '--backtest' in sys.argv:
        yesterday = date.today() - timedelta(days=1)
        results = engine.score_results(yesterday)
        print(json.dumps(results, indent=2))
    else:
        td = date.today()
        for arg in sys.argv[1:]:
            if arg.startswith('--date'):
                continue
            if len(arg) == 10 and '-' in arg:
                td = date.fromisoformat(arg)
        # Check --date VALUE format
        if '--date' in sys.argv:
            idx = sys.argv.index('--date')
            if idx + 1 < len(sys.argv):
                td = date.fromisoformat(sys.argv[idx + 1])

        picks = engine.generate_picks(td)

        if not picks:
            print("No NHL totals predictions.")
        else:
            print(f"\n{'='*70}")
            print(f"  🏒 NHL OVER/UNDER PREDICTIONS — {td}")
            print(f"{'='*70}")

            for p in picks:
                arrow = "⬆️" if p['pick'] == "OVER" else "⬇️"
                print(f"\n  {p['away_team']} @ {p['home_team']}")
                print(f"    Posted: {p['posted_total']}  |  Predicted: {p['predicted_total']}")
                print(f"    {arrow} {p['pick']} {p['posted_total']}  |  Edge: {p['edge']:+.1f}")
                print(f"    {p['tier']}  ({p['confidence']:.0f}%)")

            print(f"\n{'='*70}")
            print(f"  {len(picks)} predictions generated")
