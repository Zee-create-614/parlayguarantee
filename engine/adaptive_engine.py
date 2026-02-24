"""
Adaptive Engine — Orchestrates self-learning for ParlayGuarantee
Ties together: results_tracker → self_learner → roster_tracker → weight adjustment

This is the BRAIN that makes the engine smarter over time.
Run weekly (or on-demand) to:
1. Verify all results are accurately scored
2. Analyze which factors predicted correctly
3. Recalibrate factor weights
4. Incorporate roster changes
5. Generate a learning report

NOT auto-wired into daily pipeline. Run separately.
Created: 2026-02-23
"""
import sys
import json
import sqlite3
import logging
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
RESULTS_DB = ENGINE_DIR / "results.db"
ENGINE_DB = ENGINE_DIR / "engine_data.db"
ROSTER_DB = ENGINE_DIR / "roster_changes.db"
WEIGHTS_FILE = ENGINE_DIR / "learned_weights.json"
WEIGHTS_HISTORY = ENGINE_DIR / "weights_history.json"
LEARNING_LOG = ENGINE_DIR / "learning_log.json"


class AdaptiveEngine:
    """Orchestrates the self-learning feedback loop."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.report = {
            'run_date': datetime.now().isoformat(),
            'dry_run': dry_run,
            'phases': {}
        }
    
    def run_full_cycle(self, days_back: int = 30):
        """Run the complete learning cycle."""
        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Starting adaptive learning cycle...")
        logger.info(f"Analyzing last {days_back} days of data")
        
        # Phase 1: Audit results accuracy
        phase1 = self.audit_results(days_back)
        self.report['phases']['1_results_audit'] = phase1
        
        # Phase 2: Analyze factor performance
        phase2 = self.analyze_factors(days_back)
        self.report['phases']['2_factor_analysis'] = phase2
        
        # Phase 3: Check confidence calibration
        phase3 = self.check_calibration(days_back)
        self.report['phases']['3_calibration'] = phase3
        
        # Phase 4: Incorporate roster changes
        phase4 = self.incorporate_roster_changes()
        self.report['phases']['4_roster_impact'] = phase4
        
        # Phase 5: Generate weight adjustments
        phase5 = self.generate_weight_adjustments(days_back)
        self.report['phases']['5_weight_adjustments'] = phase5
        
        # Phase 6: Save learning report
        self.save_report()
        
        logger.info(f"\n{'='*60}")
        logger.info("ADAPTIVE LEARNING CYCLE COMPLETE")
        logger.info(f"{'='*60}")
        
        return self.report
    
    def audit_results(self, days_back: int) -> Dict:
        """Phase 1: Verify results are correctly scored."""
        logger.info("\n=== Phase 1: Results Audit ===")
        
        if not RESULTS_DB.exists():
            logger.warning("results.db not found — no results to audit")
            return {'status': 'no_data', 'message': 'results.db not found'}
        
        conn = sqlite3.connect(str(RESULTS_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        
        # Get overall stats
        c.execute("""
            SELECT COUNT(*), SUM(correct), AVG(CAST(correct AS REAL)),
                   SUM(spread_correct), COUNT(CASE WHEN spread_correct IS NOT NULL THEN 1 END)
            FROM pick_results WHERE date >= ?
        """, (cutoff,))
        row = c.fetchone()
        
        total = row[0] or 0
        ml_correct = row[1] or 0
        ml_acc = row[2] or 0
        spread_correct = row[3] or 0
        spread_total = row[4] or 0
        spread_acc = (spread_correct / spread_total) if spread_total > 0 else 0
        
        # Check for unscored picks (NULL actual_winner)
        c.execute("SELECT COUNT(*) FROM pick_results WHERE date >= ? AND actual_winner IS NULL", (cutoff,))
        unscored = c.fetchone()[0] or 0
        
        # Daily breakdown
        c.execute("""
            SELECT date, COUNT(*), SUM(correct), 
                   ROUND(AVG(CAST(correct AS REAL)) * 100, 1)
            FROM pick_results WHERE date >= ? AND actual_winner IS NOT NULL
            GROUP BY date ORDER BY date DESC
        """, (cutoff,))
        daily = [{'date': r[0], 'picks': r[1], 'correct': r[2], 'accuracy': r[3]} for r in c.fetchall()]
        
        conn.close()
        
        result = {
            'total_picks': total,
            'ml_correct': ml_correct,
            'ml_accuracy': round(ml_acc * 100, 1),
            'spread_correct': spread_correct,
            'spread_total': spread_total,
            'spread_accuracy': round(spread_acc * 100, 1),
            'unscored_picks': unscored,
            'days_analyzed': len(daily),
            'daily_breakdown': daily[:10]
        }
        
        logger.info(f"  Total picks: {total}")
        logger.info(f"  ML accuracy: {result['ml_accuracy']}% ({ml_correct}/{total})")
        logger.info(f"  Spread accuracy: {result['spread_accuracy']}% ({spread_correct}/{spread_total})")
        logger.info(f"  Unscored picks: {unscored}")
        
        return result
    
    def analyze_factors(self, days_back: int) -> Dict:
        """Phase 2: Analyze which factors are actually predictive."""
        logger.info("\n=== Phase 2: Factor Analysis ===")
        
        if not ENGINE_DB.exists():
            return {'status': 'no_data', 'message': 'engine_data.db not found'}
        
        conn = sqlite3.connect(str(ENGINE_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        
        # Get predictions with factor data
        c.execute("""
            SELECT all_factors_json, correct, confidence
            FROM predictions
            WHERE actual_result IS NOT NULL AND game_date >= ?
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            return {'status': 'no_data', 'predictions_found': 0}
        
        # Analyze each factor
        factor_stats = defaultdict(lambda: {'correct': 0, 'total': 0, 'values': []})
        
        for factors_json, correct, confidence in rows:
            try:
                factors = json.loads(factors_json)
                for name, value in factors.items():
                    factor_stats[name]['total'] += 1
                    factor_stats[name]['correct'] += (correct or 0)
                    factor_stats[name]['values'].append((value, correct or 0))
            except:
                continue
        
        # Calculate per-factor accuracy and correlation
        factor_analysis = {}
        for name, stats in factor_stats.items():
            if stats['total'] < 5:
                continue
            
            accuracy = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
            
            # Simple correlation
            values = [v for v, _ in stats['values']]
            outcomes = [o for _, o in stats['values']]
            correlation = self._correlation(values, outcomes)
            
            factor_analysis[name] = {
                'accuracy': round(accuracy, 3),
                'correlation': round(correlation, 4),
                'sample_size': stats['total'],
                'predictive': correlation > 0.05,
                'harmful': correlation < -0.05
            }
        
        # Sort by correlation (best → worst)
        sorted_factors = sorted(factor_analysis.items(), key=lambda x: x[1]['correlation'], reverse=True)
        
        top_5 = sorted_factors[:5]
        bottom_5 = sorted_factors[-5:]
        
        logger.info(f"  Analyzed {len(factor_analysis)} factors across {len(rows)} predictions")
        logger.info(f"  Top 5 factors:")
        for name, data in top_5:
            logger.info(f"    {name}: corr={data['correlation']:.4f}, acc={data['accuracy']:.1%}")
        logger.info(f"  Bottom 5 factors (potentially harmful):")
        for name, data in bottom_5:
            logger.info(f"    {name}: corr={data['correlation']:.4f}, acc={data['accuracy']:.1%}")
        
        harmful = [name for name, data in factor_analysis.items() if data['harmful']]
        
        return {
            'predictions_analyzed': len(rows),
            'factors_analyzed': len(factor_analysis),
            'top_factors': {n: d for n, d in top_5},
            'bottom_factors': {n: d for n, d in bottom_5},
            'harmful_factors': harmful,
            'all_factors': dict(sorted_factors)
        }
    
    def check_calibration(self, days_back: int) -> Dict:
        """Phase 3: Are we overconfident or underconfident?"""
        logger.info("\n=== Phase 3: Confidence Calibration ===")
        
        if not RESULTS_DB.exists():
            return {'status': 'no_data'}
        
        conn = sqlite3.connect(str(RESULTS_DB))
        c = conn.cursor()
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        
        c.execute("""
            SELECT confidence, correct FROM pick_results
            WHERE date >= ? AND actual_winner IS NOT NULL AND confidence IS NOT NULL
        """, (cutoff,))
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            return {'status': 'no_data'}
        
        # Bin by confidence ranges
        bins = {}
        for conf, correct in rows:
            bucket = round(conf * 10) / 10  # Round to nearest 0.1
            if bucket not in bins:
                bins[bucket] = {'total': 0, 'correct': 0}
            bins[bucket]['total'] += 1
            bins[bucket]['correct'] += (correct or 0)
        
        calibration = {}
        total_error = 0
        count = 0
        
        for bucket in sorted(bins.keys()):
            data = bins[bucket]
            actual_acc = data['correct'] / data['total'] if data['total'] > 0 else 0
            error = actual_acc - bucket
            calibration[f"{bucket:.0%}"] = {
                'predicted': bucket,
                'actual': round(actual_acc, 3),
                'error': round(error, 3),
                'n': data['total'],
                'verdict': 'overconfident' if error < -0.05 else ('underconfident' if error > 0.05 else 'calibrated')
            }
            if data['total'] >= 3:
                total_error += abs(error)
                count += 1
        
        avg_error = total_error / count if count > 0 else 0
        
        logger.info(f"  Average calibration error: {avg_error:.1%}")
        for bucket, data in calibration.items():
            if data['n'] >= 3:
                logger.info(f"    {bucket} confidence → {data['actual']:.1%} actual ({data['verdict']}, n={data['n']})")
        
        return {
            'average_calibration_error': round(avg_error, 3),
            'calibration_score': round(1.0 - avg_error, 3),
            'bins': calibration,
            'total_predictions': len(rows)
        }
    
    def incorporate_roster_changes(self) -> Dict:
        """Phase 4: Factor in roster changes."""
        logger.info("\n=== Phase 4: Roster Impact ===")
        
        if not ROSTER_DB.exists():
            # Try to fetch fresh data
            try:
                from roster_tracker import update_all_rosters
                stored = update_all_rosters()
                logger.info(f"  Fetched {stored} new roster events")
            except Exception as e:
                logger.warning(f"  Could not fetch roster data: {e}")
                return {'status': 'no_data'}
        
        conn = sqlite3.connect(str(ROSTER_DB))
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM roster_events")
        total = c.fetchone()[0]
        
        c.execute("""
            SELECT team, event_type, COUNT(*), SUM(impact_score)
            FROM roster_events
            WHERE event_date >= date('now', '-14 days')
            GROUP BY team, event_type
            ORDER BY SUM(impact_score) DESC
        """)
        recent = c.fetchall()
        conn.close()
        
        team_impacts = {}
        for team, event_type, count, impact in recent:
            if team not in team_impacts:
                team_impacts[team] = 0
            team_impacts[team] += impact
        
        # Sort by most impacted
        sorted_teams = sorted(team_impacts.items(), key=lambda x: abs(x[1]), reverse=True)
        
        logger.info(f"  Total roster events in DB: {total}")
        logger.info(f"  Teams with recent changes: {len(sorted_teams)}")
        for team, impact in sorted_teams[:10]:
            logger.info(f"    {team}: impact={impact:+.3f}")
        
        return {
            'total_events': total,
            'recent_changes': len(recent),
            'most_impacted_teams': {t: round(i, 3) for t, i in sorted_teams[:10]}
        }
    
    def generate_weight_adjustments(self, days_back: int) -> Dict:
        """Phase 5: Propose weight adjustments based on all analysis."""
        logger.info("\n=== Phase 5: Weight Adjustments ===")
        
        # Load current weights
        current_weights = self._load_current_weights()
        if not current_weights:
            return {'status': 'no_weights', 'message': 'No current weights found'}
        
        # Use factor analysis to propose changes
        factor_data = self.report['phases'].get('2_factor_analysis', {})
        all_factors = factor_data.get('all_factors', {})
        
        if not all_factors:
            return {'status': 'insufficient_data', 'message': 'Need more scored predictions'}
        
        proposed_weights = {}
        changes = []
        
        for factor_name, weight in current_weights.items():
            analysis = all_factors.get(factor_name)
            
            if not analysis or analysis.get('sample_size', 0) < 10:
                proposed_weights[factor_name] = weight
                continue
            
            corr = analysis['correlation']
            
            # Max 5% adjustment per cycle
            if corr > 0.08:
                # Strong positive — boost weight
                adjustment = min(0.05, corr * 0.3)
                new_weight = weight + (weight * adjustment)
                changes.append(f"↑ {factor_name}: {weight:.4f} → {new_weight:.4f} (corr={corr:.3f}, BOOST)")
            elif corr < -0.05:
                # Negative correlation — reduce weight
                adjustment = max(-0.05, corr * 0.3)
                new_weight = max(0, weight + (weight * adjustment))
                changes.append(f"↓ {factor_name}: {weight:.4f} → {new_weight:.4f} (corr={corr:.3f}, REDUCE)")
            else:
                new_weight = weight
            
            proposed_weights[factor_name] = round(new_weight, 6)
        
        # Normalize
        total = sum(proposed_weights.values())
        if total > 0:
            proposed_weights = {k: round(v/total, 6) for k, v in proposed_weights.items()}
        
        logger.info(f"  Proposed {len(changes)} weight changes:")
        for change in changes:
            logger.info(f"    {change}")
        
        if not self.dry_run and changes:
            self._save_weights(proposed_weights, changes)
            logger.info("  ✅ Weights saved to learned_weights.json")
        elif self.dry_run:
            logger.info("  [DRY RUN] Weights NOT saved")
        
        return {
            'changes_proposed': len(changes),
            'changes': changes,
            'weights_saved': not self.dry_run and bool(changes)
        }
    
    def _load_current_weights(self) -> Dict:
        """Load current weights from self_learner or file."""
        if WEIGHTS_FILE.exists():
            with open(WEIGHTS_FILE) as f:
                data = json.load(f)
                return data.get('weights', data)
        
        # Fall back to self_learner defaults
        try:
            from self_learner import SelfLearner
            sl = SelfLearner()
            return sl.load_weights()
        except:
            return {}
    
    def _save_weights(self, weights: Dict, changes: List[str]):
        """Save learned weights with history."""
        # Save current weights
        output = {
            'weights': weights,
            'updated_at': datetime.now().isoformat(),
            'changes': changes
        }
        with open(WEIGHTS_FILE, 'w') as f:
            json.dump(output, f, indent=2)
        
        # Append to history
        history = []
        if WEIGHTS_HISTORY.exists():
            with open(WEIGHTS_HISTORY) as f:
                history = json.load(f)
        
        history.append(output)
        
        # Keep last 52 entries (1 year of weekly runs)
        history = history[-52:]
        
        with open(WEIGHTS_HISTORY, 'w') as f:
            json.dump(history, f, indent=2)
    
    def save_report(self):
        """Save the full learning report."""
        with open(LEARNING_LOG, 'w') as f:
            json.dump(self.report, f, indent=2, default=str)
        logger.info(f"\nFull report saved to {LEARNING_LOG}")
    
    def _correlation(self, x: List[float], y: List[float]) -> float:
        """Pearson correlation coefficient."""
        n = len(x)
        if n < 2:
            return 0
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        den_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
        
        if den_x == 0 or den_y == 0:
            return 0
        
        return num / (den_x * den_y)


def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Adaptive Learning Engine')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without saving')
    parser.add_argument('--days', type=int, default=30, help='Days of history to analyze')
    args = parser.parse_args()
    
    engine = AdaptiveEngine(dry_run=args.dry_run)
    report = engine.run_full_cycle(days_back=args.days)
    
    print(f"\n{'='*60}")
    print(f"LEARNING CYCLE {'(DRY RUN) ' if args.dry_run else ''}SUMMARY")
    print(f"{'='*60}")
    
    p1 = report['phases'].get('1_results_audit', {})
    print(f"Results: {p1.get('ml_accuracy', 'N/A')}% ML, {p1.get('spread_accuracy', 'N/A')}% spread")
    
    p2 = report['phases'].get('2_factor_analysis', {})
    print(f"Factors: {p2.get('factors_analyzed', 0)} analyzed, {len(p2.get('harmful_factors', []))} harmful")
    
    p3 = report['phases'].get('3_calibration', {})
    print(f"Calibration: {p3.get('calibration_score', 'N/A')} (1.0 = perfect)")
    
    p5 = report['phases'].get('5_weight_adjustments', {})
    print(f"Weight changes: {p5.get('changes_proposed', 0)} proposed")


if __name__ == '__main__':
    main()
