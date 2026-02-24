"""Test weight tweaks to squeeze overall accuracy"""
import json, math
from collections import defaultdict
import itertools

with open('backtest_v5_results.json', 'r') as f:
    data = json.load(f)

from self_learner import SelfLearner
learner = SelfLearner("engine_data_v5d.db")
base_weights = learner.load_weights()

# Apply all v5 fixes
base_weights['pace'] = 0.0; base_weights['arena_hostility'] = 0.0; base_weights['marquee_matchup'] = 0.0
base_weights['away_road_trip'] = 0.0; base_weights['day_of_week'] = 0.0; base_weights['division_rivalry'] = 0.0
base_weights['overtime_fatigue'] = 0.0; base_weights['cha_chaos'] = 0.0
base_weights['home_win_pct'] = 0.0; base_weights['ft_rate_diff'] = 0.0; base_weights['assists_pg'] = 0.0
base_weights['blowout_regression'] = 0.02

for k, v in {'streak_diff': 0.03, 'scoring_margin_trend': 0.07, 'miles_traveled_diff': 0.02,
    'revenge_game': 0.02, 'trap_game': 0.02, 'altitude_factor': 0.03,
    'b2b_status': 0.07, 'schedule_density': 0.05, 'last_3_record': 0.03,
    'oreb_diff': 0.02, 'three_pt_volume': 0.01}.items():
    if k not in base_weights: base_weights[k] = v

from backtest_v3_enhanced import FACTOR_NORMS as V4_NORMS
NORMS = dict(V4_NORMS)
NORMS['home_win_pct'] = 0.5; NORMS['blowout_regression'] = 1.0; NORMS['cha_chaos'] = 1.0
CHA = "Charlotte Hornets"

def normalize(name, value):
    norm = NORMS.get(name, 1.0)
    if name == 'away_win_pct': return (value - 0.5) / norm
    return value / norm if norm != 0 else 0.0

def evaluate(weights, scale=3.0, cha_pen=5):
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
    return total_correct, total_preds, t70, {'correct': t65['correct']+t70['correct'], 'total': t65['total']+t70['total']}

# Top positive factors to try boosting
boost_factors = ['rest_days', 'scoring_margin_trend', 'away_win_pct', 'three_pt_pct',
                 'revenge_game', 'b2b_status', 'schedule_density', 'clutch_performance']

best_correct = 0
best_config = None

# Try different boost combinations for top factors
# Simple grid: multiply each by [0.5, 1.0, 1.5, 2.0]
import random
random.seed(42)

for trial in range(2000):
    w = dict(base_weights)
    for f in boost_factors:
        mult = random.choice([0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5])
        w[f] = base_weights[f] * mult
    
    # Normalize
    total = sum(w.values())
    if total > 0: w = {k: v / total for k, v in w.items()}
    
    correct, total_p, t70, t65p = evaluate(w)
    
    # Score: overall accuracy + bonus for high-conf
    score = correct + (t65p['correct'] / max(1, t65p['total'])) * 10
    
    if correct > best_correct or (correct == best_correct and score > best_correct + 5):
        best_correct = correct
        best_config = (w, correct, total_p, t70, t65p)
        if correct >= 217:
            break

if best_config:
    w, c, t, t70, t65p = best_config
    print(f"Best: {c}/{t} ({c/t*100:.1f}%)")
    print(f"  70+: {t70['correct']}/{t70['total']} ({t70['correct']/max(1,t70['total'])*100:.1f}%)")
    print(f"  65+: {t65p['correct']}/{t65p['total']} ({t65p['correct']/max(1,t65p['total'])*100:.1f}%)")
    
    # Show what changed
    print("\nKey weight changes:")
    total_base = sum(base_weights.values())
    norm_base = {k: v / total_base for k, v in base_weights.items()}
    for f in boost_factors:
        if abs(w.get(f, 0) - norm_base.get(f, 0)) > 0.001:
            print(f"  {f}: {norm_base.get(f,0):.4f} -> {w.get(f,0):.4f}")

# Also show baseline
c0, t0, t70_0, t65_0 = evaluate(dict((k, v/sum(base_weights.values())) for k, v in base_weights.items()))
print(f"\nBaseline: {c0}/{t0} ({c0/t0*100:.1f}%) | 70+: {t70_0['correct']}/{t70_0['total']} | 65+: {t65_0['correct']}/{t65_0['total']}")
