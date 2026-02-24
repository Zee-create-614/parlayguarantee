"""
ParlayGuarantee Adaptive Factors
Seasonal awareness, recency weighting, auto-detects when factors become less
predictive, proposes new patterns. All changes logged and reversible.

Usage:
    python adaptive_factors.py --analyze              # full adaptive analysis
    python adaptive_factors.py --seasonal             # show seasonal patterns
    python adaptive_factors.py --degraded             # show degraded factors
    python adaptive_factors.py --proposals            # show proposed new patterns
    python adaptive_factors.py --apply --dry-run      # preview adaptive changes
"""

import sys
import json
import sqlite3
import logging
import argparse
import math
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
DB_PATH = ENGINE_DIR / "learning.db"

# Season phases for NBA
SEASON_PHASES = {
    'early': {'start_month': 10, 'end_month': 12, 'label': 'Early Season (Oct-Dec)'},
    'mid': {'start_month': 1, 'end_month': 2, 'label': 'Mid Season (Jan-Feb)'},
    'post_asb': {'start_month': 2, 'end_month': 3, 'label': 'Post All-Star (Feb-Mar)', 'start_day': 16},
    'late': {'start_month': 3, 'end_month': 4, 'label': 'Late Season (Mar-Apr)'},
    'playoffs': {'start_month': 4, 'end_month': 6, 'label': 'Playoffs (Apr-Jun)'},
}

# Recency decay: more recent games weighted more
RECENCY_HALF_LIFE_DAYS = 21  # half-life in days for exponential decay


class AdaptiveFactors:
    """Monitors factor predictiveness and adapts over time."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS adaptive_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                factor_name TEXT,
                details TEXT,
                reversible INTEGER DEFAULT 1,
                reverted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS seasonal_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                season_phase TEXT NOT NULL,
                total_picks INTEGER DEFAULT 0,
                correct_picks INTEGER DEFAULT 0,
                accuracy REAL,
                recency_weighted_accuracy REAL,
                last_updated TEXT DEFAULT (datetime('now')),
                UNIQUE(factor_name, season_phase)
            );

            CREATE TABLE IF NOT EXISTS degraded_factors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                detected_at TEXT DEFAULT (datetime('now')),
                accuracy_30d REAL,
                accuracy_90d REAL,
                accuracy_all REAL,
                status TEXT DEFAULT 'degraded',  -- 'degraded', 'recovered', 'removed'
                recommendation TEXT,
                UNIQUE(factor_name, status)
            );

            CREATE TABLE IF NOT EXISTS pattern_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_name TEXT NOT NULL,
                description TEXT,
                evidence TEXT,
                confidence REAL,
                status TEXT DEFAULT 'proposed',  -- 'proposed', 'accepted', 'rejected'
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Season phase detection
    # ------------------------------------------------------------------
    def get_season_phase(self, game_date: str = None) -> str:
        """Determine current season phase."""
        d = date.fromisoformat(game_date) if game_date else date.today()
        month = d.month
        day = d.day

        if month >= 10 or month <= 12 and month >= 10:
            return 'early'
        if month == 1 or (month == 2 and day <= 15):
            return 'mid'
        if month == 2 and day >= 16:
            return 'post_asb'
        if month == 3:
            return 'late'
        if month >= 4 and month <= 6:
            return 'playoffs'
        return 'offseason'

    # ------------------------------------------------------------------
    # Recency-weighted accuracy
    # ------------------------------------------------------------------
    def compute_recency_weighted_accuracy(self, factor: str, pick_type: str = 'moneyline',
                                           days: int = 90) -> Optional[Dict]:
        """
        Compute factor accuracy with exponential recency weighting.
        More recent games count more.
        """
        from results_db import FACTOR_COLUMNS
        if factor not in FACTOR_COLUMNS:
            return None

        col = f"f_{factor}"
        correct_col = {'moneyline': 'ml_correct', 'spread': 'spread_correct',
                       'over_under': 'ou_correct'}.get(pick_type, 'ml_correct')

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        c = self.conn.cursor()

        rows = c.execute(f"""
            SELECT game_date, {col}, {correct_col}
            FROM picks
            WHERE scored = 1 AND {correct_col} IS NOT NULL AND {col} IS NOT NULL
                AND game_date >= ?
            ORDER BY game_date DESC
        """, (cutoff,)).fetchall()

        if len(rows) < 10:
            return None

        today = date.today()
        weighted_correct = 0.0
        weighted_total = 0.0
        unweighted_correct = 0
        unweighted_total = 0

        for row in rows:
            game_d = date.fromisoformat(row['game_date'])
            days_ago = (today - game_d).days
            weight = math.exp(-0.693 * days_ago / RECENCY_HALF_LIFE_DAYS)  # exp decay

            correct = row[correct_col]
            weighted_total += weight
            weighted_correct += weight * correct
            unweighted_total += 1
            unweighted_correct += correct

        recency_acc = (weighted_correct / weighted_total * 100) if weighted_total > 0 else 0
        flat_acc = (unweighted_correct / unweighted_total * 100) if unweighted_total > 0 else 0

        return {
            'factor': factor,
            'recency_weighted_accuracy': round(recency_acc, 1),
            'flat_accuracy': round(flat_acc, 1),
            'delta': round(recency_acc - flat_acc, 1),
            'sample_size': len(rows),
        }

    # ------------------------------------------------------------------
    # Seasonal accuracy
    # ------------------------------------------------------------------
    def compute_seasonal_accuracy(self, pick_type: str = 'moneyline') -> Dict[str, Dict]:
        """Compute per-factor accuracy broken out by season phase."""
        from results_db import FACTOR_COLUMNS

        correct_col = {'moneyline': 'ml_correct', 'spread': 'spread_correct',
                       'over_under': 'ou_correct'}.get(pick_type, 'ml_correct')

        c = self.conn.cursor()
        results = {}

        for factor in FACTOR_COLUMNS:
            col = f"f_{factor}"
            rows = c.execute(f"""
                SELECT game_date, {col}, {correct_col}
                FROM picks
                WHERE scored = 1 AND {correct_col} IS NOT NULL AND {col} IS NOT NULL
            """).fetchall()

            if len(rows) < 20:
                continue

            by_phase = defaultdict(lambda: {'correct': 0, 'total': 0})
            for row in rows:
                phase = self.get_season_phase(row['game_date'])
                by_phase[phase]['total'] += 1
                by_phase[phase]['correct'] += row[correct_col]

            phase_data = {}
            for phase, counts in by_phase.items():
                if counts['total'] >= 5:
                    phase_data[phase] = {
                        'accuracy': round(counts['correct'] / counts['total'] * 100, 1),
                        'total': counts['total'],
                    }

            if phase_data:
                results[factor] = phase_data

        return results

    # ------------------------------------------------------------------
    # Degradation detection
    # ------------------------------------------------------------------
    def detect_degraded_factors(self, threshold: float = 5.0) -> List[Dict]:
        """
        Detect factors whose recent accuracy (30d) is significantly worse
        than their long-term accuracy. Threshold is the minimum % drop.
        """
        from results_db import FACTOR_COLUMNS

        degraded = []
        for factor in FACTOR_COLUMNS:
            recent = self.compute_recency_weighted_accuracy(factor, days=30)
            long_term = self.compute_recency_weighted_accuracy(factor, days=365)

            if not recent or not long_term:
                continue
            if recent['sample_size'] < 15 or long_term['sample_size'] < 30:
                continue

            drop = long_term['flat_accuracy'] - recent['recency_weighted_accuracy']
            if drop > threshold:
                entry = {
                    'factor': factor,
                    'accuracy_30d': recent['recency_weighted_accuracy'],
                    'accuracy_long': long_term['flat_accuracy'],
                    'drop': round(drop, 1),
                    'recommendation': 'reduce_weight' if drop > 10 else 'monitor',
                }
                degraded.append(entry)

                # Store
                c = self.conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO degraded_factors
                    (factor_name, accuracy_30d, accuracy_90d, accuracy_all, status, recommendation)
                    VALUES (?, ?, ?, ?, 'degraded', ?)
                """, (factor, recent['recency_weighted_accuracy'],
                      recent['flat_accuracy'], long_term['flat_accuracy'],
                      entry['recommendation']))

        self.conn.commit()
        return sorted(degraded, key=lambda x: x['drop'], reverse=True)

    # ------------------------------------------------------------------
    # Pattern proposals
    # ------------------------------------------------------------------
    def propose_patterns(self) -> List[Dict]:
        """
        Auto-detect emerging patterns from the data.
        Looks for factor combinations that predict outcomes better than individual factors.
        """
        from results_db import FACTOR_COLUMNS

        c = self.conn.cursor()
        proposals = []

        # Pattern 1: B2B + travel = especially bad
        row = c.execute("""
            SELECT COUNT(*) as total,
                SUM(ml_correct) as correct,
                ROUND(AVG(ml_correct) * 100, 1) as accuracy
            FROM picks
            WHERE scored = 1 AND ml_correct IS NOT NULL
                AND f_b2b_status > 0.5 AND f_travel_distance > 0.5
        """).fetchone()
        if row and row['total'] >= 10:
            proposals.append({
                'pattern': 'b2b_plus_travel',
                'description': 'Back-to-back games with long travel have compounded negative effect',
                'evidence': f"Accuracy: {row['accuracy']}% over {row['total']} picks",
                'confidence': min(row['total'] / 30, 1.0),
            })

        # Pattern 2: Hot streak + home = strong
        row = c.execute("""
            SELECT COUNT(*) as total,
                SUM(ml_correct) as correct,
                ROUND(AVG(ml_correct) * 100, 1) as accuracy
            FROM picks
            WHERE scored = 1 AND ml_correct IS NOT NULL
                AND f_last_5_record > 0.7 AND f_home_court > 0.5
        """).fetchone()
        if row and row['total'] >= 10:
            proposals.append({
                'pattern': 'hot_at_home',
                'description': 'Teams on hot streaks playing at home are even stronger than expected',
                'evidence': f"Accuracy: {row['accuracy']}% over {row['total']} picks",
                'confidence': min(row['total'] / 30, 1.0),
            })

        # Pattern 3: High confidence + low upset composite
        row = c.execute("""
            SELECT COUNT(*) as total,
                SUM(ml_correct) as correct,
                ROUND(AVG(ml_correct) * 100, 1) as accuracy
            FROM picks
            WHERE scored = 1 AND ml_correct IS NOT NULL
                AND confidence > 0.70 AND upset_composite < 0.3
        """).fetchone()
        if row and row['total'] >= 10:
            proposals.append({
                'pattern': 'high_conf_low_upset',
                'description': 'High confidence picks with low upset potential are very reliable',
                'evidence': f"Accuracy: {row['accuracy']}% over {row['total']} picks",
                'confidence': min(row['total'] / 30, 1.0),
            })

        # Store proposals
        for p in proposals:
            c.execute("""
                INSERT OR IGNORE INTO pattern_proposals
                (pattern_name, description, evidence, confidence)
                VALUES (?, ?, ?, ?)
            """, (p['pattern'], p['description'], p['evidence'], p['confidence']))
        self.conn.commit()

        return proposals

    # ------------------------------------------------------------------
    # Apply adaptive changes
    # ------------------------------------------------------------------
    def generate_adaptive_weights(self, dry_run: bool = True) -> Dict:
        """
        Generate weight adjustments based on seasonal awareness and degradation.
        Returns proposed modifications to learned_weights.json.
        """
        weights_file = ENGINE_DIR / "learned_weights.json"
        if weights_file.exists():
            with open(weights_file, 'r') as f:
                data = json.load(f)
                weights = data.get('weights', data)
        else:
            weights = {}

        modifications = {}

        # 1. Reduce weights for degraded factors
        degraded = self.detect_degraded_factors()
        for d in degraded:
            factor = d['factor']
            if factor in weights and d['recommendation'] == 'reduce_weight':
                old = weights[factor]
                new = round(old * 0.8, 5)  # reduce by 20%
                modifications[factor] = {
                    'old': old, 'new': new,
                    'reason': f"Degraded: {d['accuracy_30d']}% (30d) vs {d['accuracy_long']}% (long-term)",
                    'type': 'degradation',
                }

        # 2. Seasonal adjustments (boost factors that do well in current phase)
        phase = self.get_season_phase()
        seasonal = self.compute_seasonal_accuracy()
        for factor, phases in seasonal.items():
            if phase in phases and factor in weights:
                phase_acc = phases[phase]['accuracy']
                # Compare to overall
                all_acc = sum(p['accuracy'] * p['total'] for p in phases.values()) / \
                          sum(p['total'] for p in phases.values()) if phases else 50
                if phase_acc > all_acc + 5 and phases[phase]['total'] >= 15:
                    old = weights[factor]
                    boost = min(0.03, (phase_acc - all_acc) / 500)  # conservative
                    new = round(old + boost, 5)
                    modifications[factor] = {
                        'old': old, 'new': new,
                        'reason': f"Seasonal boost ({SEASON_PHASES.get(phase, {}).get('label', phase)}): "
                                  f"{phase_acc:.1f}% vs {all_acc:.1f}% overall",
                        'type': 'seasonal',
                    }

        # Log
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO adaptive_log (action, details, reversible)
            VALUES (?, ?, 1)
        """, (
            'generate_adaptive_weights',
            json.dumps({'modifications': modifications, 'dry_run': dry_run, 'phase': phase}),
        ))
        self.conn.commit()

        if not dry_run and modifications:
            for factor, mod in modifications.items():
                weights[factor] = mod['new']
            # Normalize
            total = sum(weights.values())
            if total > 0:
                weights = {k: round(v / total, 5) for k, v in weights.items()}
            output = {
                'weights': weights,
                'generated_at': datetime.now().isoformat(),
                'adaptive_modifications': len(modifications),
            }
            with open(weights_file, 'w') as f:
                json.dump(output, f, indent=2)
            logger.info(f"Applied {len(modifications)} adaptive weight modifications")

        return modifications

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Adaptive Factors')
    parser.add_argument('--analyze', action='store_true', help='Full adaptive analysis')
    parser.add_argument('--seasonal', action='store_true', help='Show seasonal accuracy patterns')
    parser.add_argument('--degraded', action='store_true', help='Show degraded factors')
    parser.add_argument('--proposals', action='store_true', help='Show pattern proposals')
    parser.add_argument('--apply', action='store_true', help='Apply adaptive weight changes')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    args = parser.parse_args()

    af = AdaptiveFactors()

    try:
        if args.seasonal:
            seasonal = af.compute_seasonal_accuracy()
            for factor, phases in sorted(seasonal.items()):
                print(f"\n{factor}:")
                for phase, data in sorted(phases.items()):
                    label = SEASON_PHASES.get(phase, {}).get('label', phase)
                    print(f"  {label}: {data['accuracy']}% (n={data['total']})")

        elif args.degraded:
            degraded = af.detect_degraded_factors()
            if not degraded:
                print("No degraded factors detected.")
            else:
                print(f"\n{'Factor':<25} {'30d':>8} {'Long':>8} {'Drop':>8} {'Action':<15}")
                print("-" * 66)
                for d in degraded:
                    print(f"{d['factor']:<25} {d['accuracy_30d']:>7.1f}% {d['accuracy_long']:>7.1f}% "
                          f"{d['drop']:>+7.1f}% {d['recommendation']:<15}")

        elif args.proposals:
            proposals = af.propose_patterns()
            if not proposals:
                print("No patterns detected yet (need more data).")
            else:
                for p in proposals:
                    print(f"\n[{p['pattern']}] {p['description']}")
                    print(f"  Evidence: {p['evidence']}")
                    print(f"  Confidence: {p['confidence']:.0%}")

        elif args.apply:
            mods = af.generate_adaptive_weights(dry_run=args.dry_run)
            if not mods:
                print("No adaptive changes needed.")
            else:
                print(f"\n{'Factor':<25} {'Old':>8} {'New':>8} {'Type':<12} Reason")
                print("-" * 80)
                for factor, m in sorted(mods.items()):
                    print(f"{factor:<25} {m['old']:>8.5f} {m['new']:>8.5f} "
                          f"{m['type']:<12} {m['reason'][:40]}")
                if args.dry_run:
                    print(f"\n[DRY RUN] {len(mods)} changes proposed but not applied.")

        elif args.analyze:
            print("=== Full Adaptive Analysis ===\n")

            print(f"Current season phase: {af.get_season_phase()}")
            print(f"  ({SEASON_PHASES.get(af.get_season_phase(), {}).get('label', '?')})\n")

            print("--- Degraded Factors ---")
            degraded = af.detect_degraded_factors()
            if degraded:
                for d in degraded[:5]:
                    print(f"  ⚠ {d['factor']}: {d['accuracy_30d']:.1f}% (30d) vs "
                          f"{d['accuracy_long']:.1f}% (long) → {d['recommendation']}")
            else:
                print("  None detected.\n")

            print("\n--- Pattern Proposals ---")
            proposals = af.propose_patterns()
            if proposals:
                for p in proposals:
                    print(f"  💡 {p['pattern']}: {p['description']} ({p['evidence']})")
            else:
                print("  None yet.\n")

            print("\n--- Adaptive Weight Proposals ---")
            mods = af.generate_adaptive_weights(dry_run=True)
            if mods:
                for factor, m in sorted(mods.items()):
                    print(f"  {factor}: {m['old']:.5f} → {m['new']:.5f} ({m['type']})")
            else:
                print("  No changes proposed.")

        else:
            parser.print_help()

    finally:
        af.close()


if __name__ == '__main__':
    main()
