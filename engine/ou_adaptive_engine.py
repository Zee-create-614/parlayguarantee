#!/usr/bin/env python3
"""
O/U Adaptive Engine (V4) — Self-learning for Over/Under predictions.
Analyzes O/U results, identifies which factors predict totals correctly,
calibrates confidence, and outputs adjusted weights for the totals engine.

This is the O/U equivalent of adaptive_engine.py (which handles spread/ML).

Run weekly or on-demand:
  python ou_adaptive_engine.py                # Full learning cycle (dry run)
  python ou_adaptive_engine.py --apply        # Apply weight changes for real
  python ou_adaptive_engine.py --report       # Performance report only
  python ou_adaptive_engine.py --days 14      # Analyze last N days

Created: 2026-02-23
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
RESULTS_DB = ENGINE_DIR / "results.db"
V3_DB = ENGINE_DIR / "totals_engine_v3.db"
OU_WEIGHTS_FILE = ENGINE_DIR / "ou_learned_weights.json"
OU_WEIGHTS_HISTORY = ENGINE_DIR / "ou_weights_history.json"
OU_LEARNING_LOG = ENGINE_DIR / "ou_learning_log.json"

# Default O/U factor weights (what V3.1 currently uses implicitly)
DEFAULT_OU_WEIGHTS = {
    'market_blend': 0.50,         # How much to trust posted total vs our model
    'model_blend': 0.50,          # Our model weight (ORtg BOOST from V3.1)
    'pace_mismatch_mult': 0.06,   # Pace mismatch bonus multiplier (REDUCED in V3.1)
    'drtg_dampen': 0.15,          # DRtg regression to mean (V3.1 addition)
    'form_adj_mult': 0.2,         # Recent form (streak) multiplier
    'spread_adj_blowout': -1.5,   # Spread > 14 adjustment
    'spread_adj_moderate': -0.5,  # Spread 10-14 adjustment
    'spread_adj_tight': 0.5,      # Spread < 2 adjustment
    'min_edge': 1.5,              # Minimum edge to make a pick
    # Per-factor influence weights (for future factor expansion)
    'offensive_rating': 1.0,      # ORtg influence (1.0 = full)
    'defensive_rating': 0.85,     # DRtg influence (0.85 = dampened 15%)
    'pace': 0.40,                 # Pace influence (reduced from 1.0)
    'recent_form': 0.8,           # Streak/form influence
    'spread_context': 1.0,        # Spread-based adjustment influence
    'home_court_scoring': 0.03,   # Home teams score ~1.5 pts more
    'rest_advantage': 0.5,        # Rest days bonus (not yet used)
    'injury_impact': 0.0,         # Star injuries on scoring (not yet used)
}


class OUAdaptiveEngine:
    """Learns from O/U results to improve totals predictions."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.report = {
            'run_date': datetime.now().isoformat(),
            'dry_run': dry_run,
            'engine': 'O/U Adaptive V4',
            'phases': {}
        }

    def run_full_cycle(self, days_back: int = 30):
        """Run the complete O/U learning cycle."""
        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Starting O/U adaptive learning cycle...")
        logger.info(f"Analyzing last {days_back} days of O/U data")

        # Phase 1: Audit O/U results
        phase1 = self.audit_ou_results(days_back)
        self.report['phases']['1_ou_results_audit'] = phase1

        # Phase 2: Analyze prediction factors
        phase2 = self.analyze_ou_factors(days_back)
        self.report['phases']['2_factor_analysis'] = phase2

        # Phase 3: Calibration check (are our edges real?)
        phase3 = self.check_edge_calibration(days_back)
        self.report['phases']['3_edge_calibration'] = phase3

        # Phase 4: Bias detection (over/under lean?)
        phase4 = self.detect_bias(days_back)
        self.report['phases']['4_bias_detection'] = phase4

        # Phase 5: Generate weight adjustments
        phase5 = self.generate_adjustments(days_back)
        self.report['phases']['5_weight_adjustments'] = phase5

        # Save report
        self.save_report()

        logger.info(f"\n{'='*60}")
        logger.info("O/U ADAPTIVE LEARNING CYCLE COMPLETE")
        logger.info(f"{'='*60}")

        return self.report

    def audit_ou_results(self, days_back: int) -> Dict:
        """Phase 1: How are our O/U picks actually performing?"""
        logger.info("\n=== Phase 1: O/U Results Audit ===")

        if not RESULTS_DB.exists():
            return {'status': 'no_data'}

        conn = sqlite3.connect(str(RESULTS_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        # Overall O/U stats
        c.execute("""
            SELECT COUNT(*), SUM(ou_correct), 
                   AVG(CAST(ou_correct AS REAL)),
                   AVG(total_line), AVG(total_actual)
            FROM pick_results 
            WHERE date >= ? AND ou_pick IS NOT NULL AND total_actual IS NOT NULL
        """, (cutoff,))
        row = c.fetchone()
        total = row[0] or 0
        correct = row[1] or 0
        accuracy = row[2] or 0
        avg_line = row[3] or 0
        avg_actual = row[4] or 0

        # By sport
        c.execute("""
            SELECT sport, COUNT(*), SUM(ou_correct), AVG(CAST(ou_correct AS REAL))
            FROM pick_results 
            WHERE date >= ? AND ou_pick IS NOT NULL AND total_actual IS NOT NULL
            GROUP BY sport
        """, (cutoff,))
        by_sport = {r[0] or 'Unknown': {'total': r[1], 'correct': r[2], 'accuracy': round((r[3] or 0) * 100, 1)} 
                    for r in c.fetchall()}

        # By pick type (Over vs Under)
        c.execute("""
            SELECT ou_pick, COUNT(*), SUM(ou_correct), AVG(CAST(ou_correct AS REAL))
            FROM pick_results 
            WHERE date >= ? AND ou_pick IS NOT NULL AND total_actual IS NOT NULL
            GROUP BY ou_pick
        """, (cutoff,))
        by_pick = {r[0]: {'total': r[1], 'correct': r[2], 'accuracy': round((r[3] or 0) * 100, 1)} 
                   for r in c.fetchall()}

        # Error analysis: how far off are we?
        c.execute("""
            SELECT total_line, total_actual, ou_pick, ou_correct
            FROM pick_results 
            WHERE date >= ? AND ou_pick IS NOT NULL AND total_actual IS NOT NULL
        """, (cutoff,))
        errors = []
        for line, actual, pick, correct_flag in c.fetchall():
            if line and actual:
                errors.append({
                    'line': line, 'actual': actual,
                    'error': actual - line,
                    'abs_error': abs(actual - line),
                    'pick': pick, 'correct': correct_flag
                })

        avg_error = sum(e['error'] for e in errors) / len(errors) if errors else 0
        avg_abs_error = sum(e['abs_error'] for e in errors) / len(errors) if errors else 0
        
        # Games where actual was way off the line (> 15 pts)
        blowouts = [e for e in errors if e['abs_error'] > 15]

        conn.close()

        result = {
            'total_picks': total,
            'correct': correct,
            'accuracy': round(accuracy * 100, 1),
            'avg_posted_line': round(avg_line, 1),
            'avg_actual_total': round(avg_actual, 1),
            'avg_error': round(avg_error, 1),
            'avg_abs_error': round(avg_abs_error, 1),
            'by_sport': by_sport,
            'by_pick_type': by_pick,
            'blowout_games': len(blowouts),
        }

        logger.info(f"  O/U record: {correct}/{total} = {result['accuracy']}%")
        logger.info(f"  Avg line: {result['avg_posted_line']}, Avg actual: {result['avg_actual_total']}")
        logger.info(f"  Avg error: {result['avg_error']:+.1f} pts (avg abs: {result['avg_abs_error']:.1f})")
        logger.info(f"  By sport: {by_sport}")
        logger.info(f"  By pick: {by_pick}")
        logger.info(f"  Blowout games (>15 pts off): {len(blowouts)}")

        return result

    def analyze_ou_factors(self, days_back: int) -> Dict:
        """Phase 2: Which factors correlate with O/U outcomes?"""
        logger.info("\n=== Phase 2: O/U Factor Analysis ===")

        # Load V3 predictions with factor data
        if not V3_DB.exists():
            return {'status': 'no_v3_data'}

        conn = sqlite3.connect(str(V3_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        c.execute("""
            SELECT predicted_total, posted_total, our_raw_total, 
                   pick, edge, factors, actual_total, result
            FROM predictions
            WHERE game_date >= ? AND actual_total IS NOT NULL
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            # Fall back to results.db data
            return self._analyze_from_results(days_back)

        factor_correlations = defaultdict(lambda: {'values': [], 'outcomes': []})

        for pred_total, posted, raw, pick, edge, factors_json, actual, result in rows:
            if not factors_json:
                continue
            try:
                factors = json.loads(factors_json)
            except:
                continue

            outcome = 1 if actual > posted else 0  # 1 = over, 0 = under
            error = actual - posted

            for fname, fval in factors.items():
                if isinstance(fval, (int, float)):
                    factor_correlations[fname]['values'].append(fval)
                    factor_correlations[fname]['outcomes'].append(error)

        # Calculate correlations
        analysis = {}
        for fname, data in factor_correlations.items():
            if len(data['values']) < 5:
                continue
            corr = self._pearson(data['values'], data['outcomes'])
            analysis[fname] = {
                'correlation': round(corr, 4),
                'sample_size': len(data['values']),
                'predictive': abs(corr) > 0.05,
                'direction': 'over' if corr > 0 else 'under',
            }

        sorted_factors = sorted(analysis.items(), key=lambda x: abs(x[1]['correlation']), reverse=True)

        logger.info(f"  Analyzed {len(analysis)} O/U factors across {len(rows)} predictions")
        for name, data in sorted_factors[:10]:
            logger.info(f"    {name}: corr={data['correlation']:.4f} ({data['direction']}, n={data['sample_size']})")

        return {
            'predictions_analyzed': len(rows),
            'factors_analyzed': len(analysis),
            'top_factors': dict(sorted_factors[:10]),
            'all_factors': dict(sorted_factors),
        }

    def _analyze_from_results(self, days_back: int) -> Dict:
        """Fallback: analyze from results.db when V3 predictions aren't available."""
        logger.info("  Using results.db fallback (no V3 prediction factors available)")

        conn = sqlite3.connect(str(RESULTS_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        c.execute("""
            SELECT total_line, total_actual, ou_pick, ou_correct, sport
            FROM pick_results 
            WHERE date >= ? AND ou_pick IS NOT NULL AND total_actual IS NOT NULL
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return {'status': 'no_data'}

        # Analyze what we can from line/actual data
        factors = {
            'line_height': {'description': 'Higher lines → over or under bias?', 'values': [], 'outcomes': []},
            'line_deviation': {'description': 'How far actual deviates from line', 'values': [], 'outcomes': []},
        }

        for line, actual, pick, correct, sport in rows:
            if line and actual:
                error = actual - line
                factors['line_height']['values'].append(line)
                factors['line_height']['outcomes'].append(error)

        analysis = {}
        for fname, data in factors.items():
            if len(data['values']) < 5:
                continue
            corr = self._pearson(data['values'], data['outcomes'])
            analysis[fname] = {
                'correlation': round(corr, 4),
                'sample_size': len(data['values']),
                'description': data['description'],
            }
            logger.info(f"    {fname}: corr={corr:.4f} (n={len(data['values'])})")

        return {
            'predictions_analyzed': len(rows),
            'factors_analyzed': len(analysis),
            'factors': analysis,
            'note': 'Limited analysis — no V3 prediction factors available'
        }

    def check_edge_calibration(self, days_back: int) -> Dict:
        """Phase 3: When we predict an edge, is it real?"""
        logger.info("\n=== Phase 3: Edge Calibration ===")

        if not V3_DB.exists():
            return {'status': 'no_v3_data'}

        conn = sqlite3.connect(str(V3_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        c.execute("""
            SELECT edge, predicted_total, posted_total, actual_total, pick, result
            FROM predictions
            WHERE game_date >= ? AND actual_total IS NOT NULL AND pick != 'PASS'
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return {'status': 'no_data', 'note': 'No scored V3 predictions with picks'}

        # Bin by edge size
        bins = defaultdict(lambda: {'total': 0, 'correct': 0, 'errors': []})
        for edge, pred, posted, actual, pick, result in rows:
            if edge is None:
                continue
            abs_edge = abs(edge)
            if abs_edge < 2:
                bucket = 'small (1.5-2)'
            elif abs_edge < 3.5:
                bucket = 'medium (2-3.5)'
            elif abs_edge < 5:
                bucket = 'large (3.5-5)'
            else:
                bucket = 'huge (5+)'

            correct = (pick == 'OVER' and actual > posted) or (pick == 'UNDER' and actual < posted)
            bins[bucket]['total'] += 1
            bins[bucket]['correct'] += (1 if correct else 0)
            bins[bucket]['errors'].append(actual - posted)

        calibration = {}
        for bucket, data in sorted(bins.items()):
            acc = data['correct'] / data['total'] if data['total'] > 0 else 0
            avg_error = sum(data['errors']) / len(data['errors']) if data['errors'] else 0
            calibration[bucket] = {
                'accuracy': round(acc * 100, 1),
                'n': data['total'],
                'avg_actual_error': round(avg_error, 1),
            }
            logger.info(f"    {bucket}: {data['correct']}/{data['total']} = {acc:.1%}")

        return {
            'total_predictions': len(rows),
            'calibration': calibration,
        }

    def detect_bias(self, days_back: int) -> Dict:
        """Phase 4: Are we leaning too hard over or under?"""
        logger.info("\n=== Phase 4: Bias Detection ===")

        conn = sqlite3.connect(str(RESULTS_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()

        c.execute("""
            SELECT ou_pick, COUNT(*), SUM(ou_correct)
            FROM pick_results 
            WHERE date >= ? AND ou_pick IS NOT NULL AND total_actual IS NOT NULL
            GROUP BY ou_pick
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()

        bias = {}
        total_picks = 0
        for pick_type, count, correct in rows:
            acc = (correct or 0) / count if count > 0 else 0
            bias[pick_type] = {
                'count': count,
                'correct': correct or 0,
                'accuracy': round(acc * 100, 1),
            }
            total_picks += count

        # Detect bias
        over_count = bias.get('OVER', {}).get('count', 0)
        under_count = bias.get('UNDER', {}).get('count', 0)

        if total_picks > 0:
            over_pct = over_count / total_picks
            under_pct = under_count / total_picks
        else:
            over_pct = under_pct = 0.5

        bias_direction = None
        if over_pct > 0.65:
            bias_direction = 'OVER-heavy'
        elif under_pct > 0.65:
            bias_direction = 'UNDER-heavy'
        else:
            bias_direction = 'balanced'

        result = {
            'breakdown': bias,
            'over_pct': round(over_pct * 100, 1),
            'under_pct': round(under_pct * 100, 1),
            'bias': bias_direction,
        }

        logger.info(f"  Over: {over_count} ({result['over_pct']}%), Under: {under_count} ({result['under_pct']}%)")
        logger.info(f"  Bias: {bias_direction}")
        if bias_direction != 'balanced':
            logger.info(f"  ⚠️ Strong {bias_direction} bias detected — consider rebalancing")

        return result

    def generate_adjustments(self, days_back: int) -> Dict:
        """Phase 5: Propose weight changes based on analysis."""
        logger.info("\n=== Phase 5: O/U Weight Adjustments ===")

        current_weights = self._load_weights()
        factor_data = self.report['phases'].get('2_factor_analysis', {})
        bias_data = self.report['phases'].get('4_bias_detection', {})
        audit_data = self.report['phases'].get('1_ou_results_audit', {})

        changes = []
        proposed = dict(current_weights)

        # Adjustment based on accuracy
        accuracy = audit_data.get('accuracy', 50)
        avg_error = audit_data.get('avg_error', 0)

        # If we have a systematic over/under lean, adjust
        if avg_error > 2:
            # We're predicting too high (actual > line on average)
            # But we're picking Under... so the model is right to go over
            changes.append(f"📊 Systematic lean: actual averages {avg_error:+.1f} pts vs line")

        # Bias correction
        bias = bias_data.get('bias', 'balanced')
        if bias == 'UNDER-heavy':
            # We're picking Under too much — raise min_edge for Under or lower for Over
            old_edge = proposed['min_edge']
            proposed['min_edge'] = max(1.0, old_edge - 0.25)
            changes.append(f"↓ min_edge: {old_edge} → {proposed['min_edge']} (was UNDER-heavy, lowering threshold to catch more Overs)")

        elif bias == 'OVER-heavy':
            old_edge = proposed['min_edge']
            proposed['min_edge'] = min(2.5, old_edge + 0.25)
            changes.append(f"↑ min_edge: {old_edge} → {proposed['min_edge']} (was OVER-heavy)")

        # Factor-based adjustments (if V3 factor data available)
        all_factors = factor_data.get('all_factors', {}) or factor_data.get('factors', {})
        for fname, fdata in all_factors.items():
            corr = fdata.get('correlation', 0)
            if fname in proposed and abs(corr) > 0.1:
                # Strong correlation — adjust weight
                old_val = proposed[fname]
                adjustment = corr * 0.1  # 10% of correlation
                new_val = max(0, old_val + adjustment)
                if abs(new_val - old_val) > 0.001:
                    proposed[fname] = round(new_val, 4)
                    direction = "↑" if adjustment > 0 else "↓"
                    changes.append(f"{direction} {fname}: {old_val:.4f} → {new_val:.4f} (corr={corr:.3f})")

        logger.info(f"  Proposed {len(changes)} changes:")
        for change in changes:
            logger.info(f"    {change}")

        if not self.dry_run and changes:
            self._save_weights(proposed, changes)
            logger.info("  ✅ O/U weights saved")
        elif self.dry_run:
            logger.info("  [DRY RUN] Weights NOT saved")

        return {
            'changes_proposed': len(changes),
            'changes': changes,
            'weights_saved': not self.dry_run and bool(changes),
            'proposed_weights': proposed,
        }

    def _load_weights(self) -> Dict:
        if OU_WEIGHTS_FILE.exists():
            with open(OU_WEIGHTS_FILE) as f:
                data = json.load(f)
                return data.get('weights', data)
        return dict(DEFAULT_OU_WEIGHTS)

    def _save_weights(self, weights: Dict, changes: List[str]):
        output = {
            'weights': weights,
            'updated_at': datetime.now().isoformat(),
            'changes': changes,
            'engine': 'O/U Adaptive V4',
        }
        with open(OU_WEIGHTS_FILE, 'w') as f:
            json.dump(output, f, indent=2)

        # Append to history
        history = []
        if OU_WEIGHTS_HISTORY.exists():
            with open(OU_WEIGHTS_HISTORY) as f:
                history = json.load(f)
        history.append(output)
        history = history[-52:]
        with open(OU_WEIGHTS_HISTORY, 'w') as f:
            json.dump(history, f, indent=2)

    def save_report(self):
        with open(OU_LEARNING_LOG, 'w') as f:
            json.dump(self.report, f, indent=2, default=str)
        logger.info(f"\nFull O/U report saved to {OU_LEARNING_LOG}")

    def _pearson(self, xs: List[float], ys: List[float]) -> float:
        n = len(xs)
        if n < 5:
            return 0.0
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        if dx == 0 or dy == 0:
            return 0.0
        return num / (dx * dy)


def main():
    parser = argparse.ArgumentParser(description='O/U Adaptive Learning Engine (V4)')
    parser.add_argument('--apply', action='store_true', help='Apply weight changes (remove dry-run safety)')
    parser.add_argument('--report', action='store_true', help='Performance report only')
    parser.add_argument('--days', type=int, default=30, help='Days of history to analyze')
    args = parser.parse_args()

    dry_run = not args.apply
    engine = OUAdaptiveEngine(dry_run=dry_run)
    report = engine.run_full_cycle(days_back=args.days)

    print(f"\n{'='*60}")
    print(f"O/U LEARNING CYCLE {'(DRY RUN) ' if dry_run else ''}SUMMARY")
    print(f"{'='*60}")

    p1 = report['phases'].get('1_ou_results_audit', {})
    print(f"O/U Record: {p1.get('correct', 0)}/{p1.get('total_picks', 0)} = {p1.get('accuracy', 'N/A')}%")
    print(f"Avg Error: {p1.get('avg_error', 'N/A'):+.1f} pts")

    p4 = report['phases'].get('4_bias_detection', {})
    print(f"Bias: {p4.get('bias', 'unknown')}")

    p5 = report['phases'].get('5_weight_adjustments', {})
    print(f"Weight changes: {p5.get('changes_proposed', 0)} proposed")
    if p5.get('changes'):
        for c in p5['changes']:
            print(f"  {c}")


if __name__ == '__main__':
    main()
