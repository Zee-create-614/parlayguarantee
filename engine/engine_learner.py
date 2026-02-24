"""
ParlayGuarantee Engine Learner — Self-Learning Feedback Loop
Analyzes historical results, identifies which factors predict correctly,
calibrates confidence, and outputs adjusted weights.

Usage:
    python engine_learner.py                    # full learning cycle
    python engine_learner.py --dry-run          # show what WOULD change
    python engine_learner.py --report           # performance report only
    python engine_learner.py --rollback CYCLE   # rollback to before a cycle
    python engine_learner.py --history          # show weight change history
"""

import sys
import json
import math
import uuid
import argparse
import logging
import statistics
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from results_db import ResultsDB, FACTOR_COLUMNS

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
WEIGHTS_PATH = ENGINE_DIR / "learned_weights.json"
WEIGHTS_HISTORY_DIR = ENGINE_DIR / "weight_history"

# Max weight change per learning cycle: 5%
MAX_CHANGE_PCT = 5.0
MIN_SAMPLES = 30  # Minimum scored picks before we adjust anything


class EngineLearner:
    """Analyzes results and generates weight adjustments."""

    def __init__(self, db: ResultsDB = None):
        self.db = db or ResultsDB()
        WEIGHTS_HISTORY_DIR.mkdir(exist_ok=True)

    def load_current_weights(self) -> Dict[str, float]:
        """Load current weights from learned_weights.json or defaults from self_learner."""
        if WEIGHTS_PATH.exists():
            with open(WEIGHTS_PATH, 'r') as f:
                data = json.load(f)
                return data.get('weights', data)
        # Fall back to self_learner defaults
        try:
            from self_learner import SelfLearner
            sl = SelfLearner()
            return sl.default_weights.copy()
        except Exception:
            return {f: 1.0 / len(ALL_FACTORS) for f in ALL_FACTORS}

    def _pearson(self, xs: List[float], ys: List[float]) -> float:
        n = len(xs)
        if n < 5:
            return 0.0
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        if dx == 0 or dy == 0:
            return 0.0
        return num / (dx * dy)

    def analyze_factor_accuracy(self, scored: List[Dict]) -> Dict[str, Dict]:
        """For each factor, compute correlation with correct picks and accuracy stats."""
        factor_data = defaultdict(lambda: {'values': [], 'outcomes': []})

        for pick in scored:
            fj = pick.get('factors_json')
            if not fj:
                continue
            factors = json.loads(fj)
            ml_correct = pick.get('ml_correct')
            if ml_correct is None:
                continue
            for fname, fval in factors.items():
                if isinstance(fval, (int, float)):
                    factor_data[fname]['values'].append(fval)
                    factor_data[fname]['outcomes'].append(ml_correct)

        results = {}
        for fname, data in factor_data.items():
            n = len(data['values'])
            if n < 10:
                results[fname] = {'samples': n, 'insufficient': True}
                continue

            corr = self._pearson(data['values'], data['outcomes'])
            accuracy = sum(data['outcomes']) / n
            # Accuracy when factor > median
            med = statistics.median(data['values'])
            above = [(v, o) for v, o in zip(data['values'], data['outcomes']) if v > med]
            below = [(v, o) for v, o in zip(data['values'], data['outcomes']) if v <= med]
            acc_above = sum(o for _, o in above) / len(above) if above else 0.5
            acc_below = sum(o for _, o in below) / len(below) if below else 0.5

            results[fname] = {
                'samples': n,
                'correlation': round(corr, 4),
                'overall_accuracy': round(accuracy, 4),
                'accuracy_above_median': round(acc_above, 4),
                'accuracy_below_median': round(acc_below, 4),
                'lift': round(acc_above - acc_below, 4),
            }
        return results

    def analyze_confidence_calibration(self, scored: List[Dict]) -> Dict[str, Dict]:
        """Bin picks by confidence level and check actual hit rate."""
        bins = defaultdict(lambda: {'correct': 0, 'total': 0})
        for pick in scored:
            conf = pick.get('confidence')
            ml = pick.get('ml_correct')
            if conf is None or ml is None:
                continue
            # 5% bins: 50-55, 55-60, ...
            bucket = int(conf * 100 // 5) * 5
            label = f"{bucket}-{bucket+5}%"
            bins[label]['total'] += 1
            if ml:
                bins[label]['correct'] += 1

        calibration = {}
        for label, data in sorted(bins.items()):
            actual = data['correct'] / data['total'] if data['total'] else 0
            expected_mid = (int(label.split('-')[0]) + 2.5) / 100
            calibration[label] = {
                'total': data['total'],
                'correct': data['correct'],
                'actual_rate': round(actual, 4),
                'expected_rate': round(expected_mid, 4),
                'gap': round(actual - expected_mid, 4),
            }
        return calibration

    def compute_weight_adjustments(self, current_weights: Dict[str, float],
                                   factor_analysis: Dict[str, Dict]) -> Dict[str, Dict]:
        """Compute new weights with max 5% change per factor per cycle."""
        adjustments = {}
        for fname, old_w in current_weights.items():
            analysis = factor_analysis.get(fname)
            if not analysis or analysis.get('insufficient'):
                adjustments[fname] = {'old': old_w, 'new': old_w, 'change_pct': 0, 'reason': 'insufficient data'}
                continue

            corr = analysis['correlation']
            lift = analysis.get('lift', 0)

            # Direction: increase if positively correlated + positive lift, decrease otherwise
            # Magnitude: proportional to |correlation| but capped at MAX_CHANGE_PCT
            signal = (corr * 0.6 + lift * 0.4)  # blended signal
            raw_change_pct = signal * 10  # scale to percentage
            clamped = max(-MAX_CHANGE_PCT, min(MAX_CHANGE_PCT, raw_change_pct))

            new_w = old_w * (1 + clamped / 100)
            new_w = max(0.0, new_w)  # no negative weights

            reason = f"corr={corr:+.3f}, lift={lift:+.3f}, signal={signal:+.3f}"
            if abs(corr) < 0.01 and abs(lift) < 0.01:
                reason = "no signal"
                new_w = old_w

            adjustments[fname] = {
                'old': round(old_w, 6),
                'new': round(new_w, 6),
                'change_pct': round((new_w - old_w) / old_w * 100 if old_w else 0, 2),
                'reason': reason,
            }
        return adjustments

    def run_learning_cycle(self, dry_run: bool = False, sport: str = None) -> Dict:
        """Run a full learning cycle. Returns summary."""
        cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info(f"{'[DRY-RUN] ' if dry_run else ''}Starting learning cycle: {cycle_id}")

        scored = self.db.get_scored_picks(sport=sport)
        if len(scored) < MIN_SAMPLES:
            msg = f"Only {len(scored)} scored picks (need {MIN_SAMPLES}). Skipping."
            logger.warning(msg)
            return {'cycle_id': cycle_id, 'skipped': True, 'reason': msg}

        logger.info(f"Analyzing {len(scored)} scored picks...")
        current_weights = self.load_current_weights()
        factor_analysis = self.analyze_factor_accuracy(scored)
        calibration = self.analyze_confidence_calibration(scored)
        adjustments = self.compute_weight_adjustments(current_weights, factor_analysis)

        # Count actual changes
        changed = {k: v for k, v in adjustments.items() if abs(v['change_pct']) > 0.01}
        logger.info(f"Factors with adjustments: {len(changed)}/{len(adjustments)}")

        # Print top movers
        top_up = sorted(changed.items(), key=lambda x: x[1]['change_pct'], reverse=True)[:5]
        top_down = sorted(changed.items(), key=lambda x: x[1]['change_pct'])[:5]
        if top_up:
            logger.info("Top increases:")
            for fname, adj in top_up:
                logger.info(f"  {fname}: {adj['old']:.4f} → {adj['new']:.4f} ({adj['change_pct']:+.2f}%) — {adj['reason']}")
        if top_down and top_down[0][1]['change_pct'] < 0:
            logger.info("Top decreases:")
            for fname, adj in top_down:
                if adj['change_pct'] >= 0:
                    break
                logger.info(f"  {fname}: {adj['old']:.4f} → {adj['new']:.4f} ({adj['change_pct']:+.2f}%) — {adj['reason']}")

        # Calibration report
        logger.info("\nConfidence Calibration:")
        for label, cal in sorted(calibration.items()):
            gap_str = f"{cal['gap']:+.1%}"
            flag = " ⚠️" if abs(cal['gap']) > 0.10 else ""
            logger.info(f"  {label}: said {cal['expected_rate']:.0%}, actual {cal['actual_rate']:.0%} "
                         f"(gap {gap_str}, n={cal['total']}){flag}")

        if not dry_run:
            # Save new weights
            new_weights = {k: v['new'] for k, v in adjustments.items()}
            # Normalize
            total = sum(new_weights.values())
            if total > 0:
                new_weights = {k: v / total for k, v in new_weights.items()}

            weights_data = {
                'weights': new_weights,
                'cycle_id': cycle_id,
                'timestamp': datetime.now().isoformat(),
                'picks_analyzed': len(scored),
            }
            with open(WEIGHTS_PATH, 'w') as f:
                json.dump(weights_data, f, indent=2)
            logger.info(f"Saved learned_weights.json ({len(new_weights)} factors)")

            # Archive a copy
            archive = WEIGHTS_HISTORY_DIR / f"weights_{cycle_id}.json"
            with open(archive, 'w') as f:
                json.dump(weights_data, f, indent=2)

            # Log to DB
            for fname, adj in changed.items():
                self.db.log_weight_change(fname, adj['old'], adj['new'], adj['reason'], cycle_id)

            self.db.log_learning_cycle(cycle_id, len(scored), len(changed), dry_run, {
                'factor_analysis_sample': {k: v for k, v in list(factor_analysis.items())[:5]},
                'calibration': calibration,
                'changes': len(changed),
            })

        summary = {
            'cycle_id': cycle_id,
            'dry_run': dry_run,
            'picks_analyzed': len(scored),
            'factors_adjusted': len(changed),
            'calibration': calibration,
            'top_factors': sorted(
                [(k, v) for k, v in factor_analysis.items() if not v.get('insufficient')],
                key=lambda x: abs(x[1].get('correlation', 0)),
                reverse=True
            )[:10],
        }
        return summary

    def generate_report(self, sport: str = None) -> str:
        """Generate a human-readable performance report."""
        scored = self.db.get_scored_picks(sport=sport)
        if not scored:
            return "No scored picks in database."

        lines = [f"=== ParlayGuarantee Performance Report ===",
                 f"Total scored picks: {len(scored)}"]

        # Overall accuracy
        ml_total = sum(1 for p in scored if p.get('ml_correct') is not None)
        ml_correct = sum(1 for p in scored if p.get('ml_correct') == 1)
        sp_total = sum(1 for p in scored if p.get('spread_correct') is not None)
        sp_correct = sum(1 for p in scored if p.get('spread_correct') == 1)
        ou_total = sum(1 for p in scored if p.get('ou_correct') is not None)
        ou_correct = sum(1 for p in scored if p.get('ou_correct') == 1)

        lines.append(f"\nOverall:")
        lines.append(f"  ML:     {ml_correct}/{ml_total} ({ml_correct/ml_total*100:.1f}%)" if ml_total else "  ML: N/A")
        lines.append(f"  Spread: {sp_correct}/{sp_total} ({sp_correct/sp_total*100:.1f}%)" if sp_total else "  Spread: N/A")
        lines.append(f"  O/U:    {ou_correct}/{ou_total} ({ou_correct/ou_total*100:.1f}%)" if ou_total else "  O/U: N/A")

        # Factor analysis
        fa = self.analyze_factor_accuracy(scored)
        predictive = sorted(
            [(k, v) for k, v in fa.items() if not v.get('insufficient')],
            key=lambda x: abs(x[1].get('correlation', 0)), reverse=True
        )
        lines.append(f"\nTop Predictive Factors (by |correlation|):")
        for fname, data in predictive[:10]:
            lines.append(f"  {fname}: corr={data['correlation']:+.3f}, "
                         f"lift={data.get('lift',0):+.3f}, n={data['samples']}")

        # Worst factors
        worst = sorted(
            [(k, v) for k, v in fa.items() if not v.get('insufficient')],
            key=lambda x: abs(x[1].get('correlation', 0))
        )
        lines.append(f"\nLeast Predictive Factors:")
        for fname, data in worst[:5]:
            lines.append(f"  {fname}: corr={data['correlation']:+.3f}, n={data['samples']}")

        return '\n'.join(lines)

    def rollback(self, cycle_id: str):
        """Rollback to the weights BEFORE a given cycle."""
        history = self.db.get_weight_history(limit=5000)
        # Find the cycle and restore old weights
        restore = {}
        for entry in history:
            if entry['cycle_id'] == cycle_id:
                restore[entry['factor_name']] = entry['old_weight']

        if not restore:
            logger.error(f"No weight changes found for cycle {cycle_id}")
            return

        # Load current and apply rollback
        current = self.load_current_weights()
        for fname, old_w in restore.items():
            current[fname] = old_w

        weights_data = {
            'weights': current,
            'cycle_id': f"rollback_{cycle_id}",
            'timestamp': datetime.now().isoformat(),
            'rollback_from': cycle_id,
        }
        with open(WEIGHTS_PATH, 'w') as f:
            json.dump(weights_data, f, indent=2)
        logger.info(f"Rolled back {len(restore)} factor weights from cycle {cycle_id}")


def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Engine Learner')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving')
    parser.add_argument('--report', action='store_true', help='Print performance report')
    parser.add_argument('--rollback', type=str, help='Rollback to before a cycle ID')
    parser.add_argument('--history', action='store_true', help='Show weight change history')
    parser.add_argument('--sport', type=str, help='Filter by sport')
    parser.add_argument('--db', type=str, help='Custom DB path')
    args = parser.parse_args()

    from pathlib import Path
    db = ResultsDB(Path(args.db)) if args.db else ResultsDB()
    learner = EngineLearner(db)

    if args.report:
        print(learner.generate_report(args.sport))
    elif args.rollback:
        learner.rollback(args.rollback)
    elif args.history:
        history = db.get_weight_history(limit=50)
        for h in history:
            print(f"  {h['timestamp']} | {h['factor_name']}: {h['old_weight']:.4f} → {h['new_weight']:.4f} "
                  f"({h['change_pct']:+.1f}%) — {h['rationale']} [{h['cycle_id']}]")
    else:
        summary = learner.run_learning_cycle(dry_run=args.dry_run, sport=args.sport)
        print(json.dumps(summary, indent=2, default=str))


if __name__ == '__main__':
    main()
