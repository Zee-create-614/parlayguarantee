"""Proper train/val weight search"""
import json, math, random
from collections import defaultdict

with open('backtest_v5_results.json', 'r') as f:
    data = json.load(f)

train = [p for p in data['all_predictions'] if p['game_date'] < '2026-01-22']
val = [p for p in data['all_predictions'] if p['game_date'] >= '2026-01-22']
print(f"Train: {len(train)}, Val: {len(val)}")

from self_learner import SelfLearner
learner = SelfLearner("engine_data_v5e.db")
base_weights = learner.load_weights()

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

def evaluate(preds, weights, scale=3.0, cha_pen=5):
    correct = 0; total = 0
    tiers = defaultdict(lambda: {'correct': 0, 'total': 0})
    for p in preds:
        factors = dict(p['factors']); factors['home_court'] = 1.0
        score = sum(max(-2.0, min(2.0, normalize(f, factors.get(f, 0)))) * weights.get(f, 0) for f in weights)
        hp = 1.0 / (1.0 + math.exp(-score * scale))
        hp = max(0.20, min(0.80, hp))
        if hp >= 0.5: conf, is_home = hp * 100, True
        else: conf, is_home = (1 - hp) * 100, False
        if (p['home_team'] == CHA or p['away_team'] == CHA) and cha_pen > 0:
            conf = max(50.0, conf - cha_pen)
        predicted = p['home_team'] if is_home else p['away_team']
        total += 1
        if predicted == p['actual_winner']: correct += 1
        tier = "70+" if conf >= 70 else "65-70" if conf >= 65 else "60-65" if conf >= 60 else "55-60" if conf >= 55 else "<55"
        tiers[tier]['total'] += 1
        if predicted == p['actual_winner']: tiers[tier]['correct'] += 1
    t65 = tiers.get('65-70', {'c': 0, 't': 0}); t70 = tiers.get('70+', {'c': 0, 't': 0})
    return correct, total, tiers

boost_factors = ['rest_days', 'scoring_margin_trend', 'away_win_pct', 'three_pt_pct',
                 'revenge_game', 'b2b_status', 'schedule_density', 'clutch_performance',
                 'net_rating', 'defensive_rating', 'home_court', 'streak_diff']

random.seed(42)
best_val_score = 0
best_config = None

for trial in range(5000):
    w = dict(base_weights)
    for f in boost_factors:
        mult = random.choice([0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0])
        w[f] = base_weights[f] * mult
    total_w = sum(w.values())
    if total_w > 0: w = {k: v / total_w for k, v in w.items()}
    
    # Evaluate on TRAIN
    train_c, train_t, _ = evaluate(train, w)
    train_acc = train_c / train_t
    
    # Only consider if train accuracy is good enough
    if train_acc < 0.66:
        continue
    
    # Score on val
    val_c, val_t, val_tiers = evaluate(val, w)
    val_acc = val_c / val_t
    
    t65 = val_tiers.get('65-70', {'correct': 0, 'total': 0})
    t70 = val_tiers.get('70+', {'correct': 0, 'total': 0})
    hc_correct = t65['correct'] + t70['correct']
    hc_total = t65['total'] + t70['total']
    hc_acc = hc_correct / max(1, hc_total)
    
    score = val_acc * 0.5 + hc_acc * 0.5
    
    if score > best_val_score:
        best_val_score = score
        best_config = w
        print(f"Trial {trial}: Train={train_acc:.3f}, Val={val_acc:.3f}, Val65+={hc_acc:.3f} ({hc_correct}/{hc_total})")

# Final evaluation on both
if best_config:
    print("\n=== BEST WEIGHTS ===")
    for dataset_name, dataset in [("Train", train), ("Val", val), ("Full", data['all_predictions'])]:
        c, t, tiers = evaluate(dataset, best_config)
        t65 = tiers.get('65-70', {'correct': 0, 'total': 0})
        t70 = tiers.get('70+', {'correct': 0, 'total': 0})
        hc_c = t65['correct'] + t70['correct']
        hc_t = t65['total'] + t70['total']
        print(f"{dataset_name}: {c}/{t} ({c/t*100:.1f}%) | 70+: {t70['correct']}/{t70['total']} ({t70['correct']/max(1,t70['total'])*100:.1f}%) | "
              f"65+: {hc_c}/{hc_t} ({hc_c/max(1,hc_t)*100:.1f}%)")
    
    # Also show baseline
    print("\n=== BASELINE ===")
    bw = {k: v / sum(base_weights.values()) for k, v in base_weights.items()}
    for dataset_name, dataset in [("Train", train), ("Val", val), ("Full", data['all_predictions'])]:
        c, t, tiers = evaluate(dataset, bw)
        t65 = tiers.get('65-70', {'correct': 0, 'total': 0})
        t70 = tiers.get('70+', {'correct': 0, 'total': 0})
        hc_c = t65['correct'] + t70['correct']
        hc_t = t65['total'] + t70['total']
        print(f"{dataset_name}: {c}/{t} ({c/t*100:.1f}%) | 70+: {t70['correct']}/{t70['total']} ({t70['correct']/max(1,t70['total'])*100:.1f}%) | "
              f"65+: {hc_c}/{hc_t} ({hc_c/max(1,hc_t)*100:.1f}%)")
    
    # Show optimized weights for active factors
    print("\nOptimized weights (active only):")
    total_w = sum(base_weights.values())
    bw_norm = {k: v / total_w for k, v in base_weights.items()}
    for f in sorted(best_config.keys(), key=lambda x: best_config[x], reverse=True):
        if best_config[f] > 0.001:
            change = ""
            if f in bw_norm and abs(best_config[f] - bw_norm[f]) > 0.002:
                change = f" (was {bw_norm[f]:.4f})"
            print(f"  {f}: {best_config[f]:.4f}{change}")
