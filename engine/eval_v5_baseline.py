"""Quick eval: v5 factor fixes with ORIGINAL weights (no optimization)"""
import json, math
from collections import defaultdict
from datetime import datetime

# Load all game data from v5 results
with open('backtest_v5_results.json', 'r') as f:
    data = json.load(f)

# Original v4 weights (before optimization)
from self_learner import SelfLearner
learner = SelfLearner("engine_data_v5_eval.db")
weights = learner.load_weights()

# Apply v4/v5 overrides but NO optimization
weights['pace'] = 0.0
weights['arena_hostility'] = 0.0
weights['marquee_matchup'] = 0.0
weights['rest_days'] = 0.10
weights['clutch_performance'] = 0.06
weights['turnover_diff'] = 0.05
weights['away_road_trip'] = 0.0
weights['day_of_week'] = 0.0
weights['division_rivalry'] = 0.0
weights['overtime_fatigue'] = 0.0
weights['blowout_regression'] = 0.02
weights['cha_chaos'] = 0.0

new_factor_weights = {
    'streak_diff': 0.03, 'scoring_margin_trend': 0.07,
    'miles_traveled_diff': 0.02, 'revenge_game': 0.02,
    'trap_game': 0.02, 'altitude_factor': 0.03,
    'b2b_status': 0.07, 'schedule_density': 0.05,
    'last_3_record': 0.03, 'oreb_diff': 0.02, 'three_pt_volume': 0.01,
}
for k, v in new_factor_weights.items():
    if k not in weights:
        weights[k] = v

total = sum(weights.values())
if total > 0:
    weights = {k: v / total for k, v in weights.items()}

# Factor norms from v5
from backtest_v3_enhanced import FACTOR_NORMS as V4_NORMS
NORMS = dict(V4_NORMS)
NORMS['home_win_pct'] = 0.5
NORMS['blowout_regression'] = 1.0
NORMS['cha_chaos'] = 1.0

CHA = "Charlotte Hornets"

def normalize(name, value):
    norm = NORMS.get(name, 1.0)
    if name == 'away_win_pct':
        return (value - 0.5) / norm
    return value / norm if norm != 0 else 0.0

def predict(factors, home_team, away_team):
    factors_copy = dict(factors)
    factors_copy['home_court'] = 1.0
    score = 0.0
    for f in weights:
        raw = factors_copy.get(f, 0)
        n = normalize(f, raw)
        n = max(-2.0, min(2.0, n))
        score += n * weights.get(f, 0)
    scaled = score * 3.0
    hp = 1.0 / (1.0 + math.exp(-scaled))
    hp = max(0.20, min(0.80, hp))
    if hp >= 0.5:
        conf = hp * 100
        is_home = True
    else:
        conf = (1 - hp) * 100
        is_home = False
    if home_team == CHA or away_team == CHA:
        conf = max(50.0, conf - 5.0)
    return conf, is_home

# Evaluate
total_correct = 0
total_preds = 0
tiers = defaultdict(lambda: {'correct': 0, 'total': 0})
import numpy as np
factor_corr = defaultdict(lambda: {'correct_vals': [], 'incorrect_vals': []})

for p in data['all_predictions']:
    factors = p['factors']
    conf, is_home = predict(factors, p['home_team'], p['away_team'])
    predicted = p['home_team'] if is_home else p['away_team']
    correct = predicted == p['actual_winner']
    
    total_preds += 1
    if correct:
        total_correct += 1
    
    tier = "70+" if conf >= 70 else "65-70" if conf >= 65 else "60-65" if conf >= 60 else "55-60" if conf >= 55 else "<55"
    tiers[tier]['total'] += 1
    if correct:
        tiers[tier]['correct'] += 1
    
    for fname, fval in factors.items():
        if correct:
            factor_corr[fname]['correct_vals'].append(fval)
        else:
            factor_corr[fname]['incorrect_vals'].append(fval)

print(f"Overall: {total_correct}/{total_preds} ({total_correct/total_preds*100:.1f}%)")
print("\nBy Confidence Tier:")
for tier in ["70+", "65-70", "60-65", "55-60", "<55"]:
    d = tiers.get(tier, {'correct': 0, 'total': 0})
    if d['total'] > 0:
        print(f"  {tier}%: {d['correct']}/{d['total']} ({d['correct']/d['total']*100:.1f}%)")

t65 = tiers.get('65-70', {'correct': 0, 'total': 0})
t70 = tiers.get('70+', {'correct': 0, 'total': 0})
c65 = t65['correct'] + t70['correct']
n65 = t65['total'] + t70['total']
print(f"  65%+ combined: {c65}/{n65} ({c65/max(1,n65)*100:.1f}%)")

# Factor correlations
print("\nFactor Correlations:")
for fname, d in factor_corr.items():
    cv, iv = d['correct_vals'], d['incorrect_vals']
    if len(cv) > 5 and len(iv) > 5:
        all_v = cv + iv
        all_o = [1]*len(cv) + [0]*len(iv)
        std = np.std(all_v)
        if std > 0:
            corr = np.corrcoef(all_v, all_o)[0, 1]
            if not np.isnan(corr) and corr < -0.02:
                print(f"  ⚠️ {fname}: {corr:.4f} (weight={weights.get(fname, 0):.4f})")
