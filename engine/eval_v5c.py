"""Test different sigmoid scales and CHA penalties"""
import json, math
from collections import defaultdict

with open('backtest_v5_results.json', 'r') as f:
    data = json.load(f)

from self_learner import SelfLearner
learner = SelfLearner("engine_data_v5c.db")
weights = learner.load_weights()

weights['pace'] = 0.0; weights['arena_hostility'] = 0.0; weights['marquee_matchup'] = 0.0
weights['rest_days'] = 0.10; weights['clutch_performance'] = 0.06; weights['turnover_diff'] = 0.05
weights['away_road_trip'] = 0.0; weights['day_of_week'] = 0.0; weights['division_rivalry'] = 0.0
weights['overtime_fatigue'] = 0.0; weights['blowout_regression'] = 0.02; weights['cha_chaos'] = 0.0
weights['home_win_pct'] = 0.0; weights['ft_rate_diff'] = 0.0; weights['assists_pg'] = 0.0

for k, v in {'streak_diff': 0.03, 'scoring_margin_trend': 0.07, 'miles_traveled_diff': 0.02,
    'revenge_game': 0.02, 'trap_game': 0.02, 'altitude_factor': 0.03,
    'b2b_status': 0.07, 'schedule_density': 0.05, 'last_3_record': 0.03,
    'oreb_diff': 0.02, 'three_pt_volume': 0.01}.items():
    if k not in weights: weights[k] = v

total = sum(weights.values())
weights = {k: v / total for k, v in weights.items()}

from backtest_v3_enhanced import FACTOR_NORMS as V4_NORMS
NORMS = dict(V4_NORMS)
NORMS['home_win_pct'] = 0.5; NORMS['blowout_regression'] = 1.0; NORMS['cha_chaos'] = 1.0
CHA = "Charlotte Hornets"

def normalize(name, value):
    norm = NORMS.get(name, 1.0)
    if name == 'away_win_pct': return (value - 0.5) / norm
    return value / norm if norm != 0 else 0.0

for scale in [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
    for cha_pen in [0, 5]:
        total_correct = 0; total_preds = 0
        tiers = defaultdict(lambda: {'correct': 0, 'total': 0})
        
        for p in data['all_predictions']:
            factors = dict(p['factors']); factors['home_court'] = 1.0
            score = sum(max(-2.0, min(2.0, normalize(f, factors.get(f, 0)))) * weights.get(f, 0) for f in weights)
            hp = 1.0 / (1.0 + math.exp(-score * scale))
            hp = max(0.20, min(0.80, hp))
            if hp >= 0.5: conf, is_home = hp * 100, True
            else: conf, is_home = (1 - hp) * 100, False
            if (p['home_team'] == CHA or p['away_team'] == CHA) and cha_pen > 0:
                conf = max(50.0, conf - cha_pen)
            predicted = p['home_team'] if is_home else p['away_team']
            correct = predicted == p['actual_winner']
            total_preds += 1
            if correct: total_correct += 1
            tier = "70+" if conf >= 70 else "65-70" if conf >= 65 else "60-65" if conf >= 60 else "55-60" if conf >= 55 else "<55"
            tiers[tier]['total'] += 1
            if correct: tiers[tier]['correct'] += 1
        
        t65 = tiers.get('65-70', {'correct': 0, 'total': 0})
        t70 = tiers.get('70+', {'correct': 0, 'total': 0})
        c65 = t65['correct'] + t70['correct']
        n65 = t65['total'] + t70['total']
        
        print(f"scale={scale} CHA={cha_pen}: {total_correct}/{total_preds} ({total_correct/total_preds*100:.1f}%) | "
              f"70+: {t70['correct']}/{t70['total']} ({t70['correct']/max(1,t70['total'])*100:.1f}%) | "
              f"65+: {c65}/{n65} ({c65/max(1,n65)*100:.1f}%)")
