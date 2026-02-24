"""
ParlayGuarantee Engine v5 - Optimized Backtest
Fixes: home_win_pct, away_road_trip, all negative factors
Adds: CHA chaos, blowout regression, weight optimization via train/validation split
"""

import sys
import json
import time
import logging
import sqlite3
import math
import signal
from datetime import datetime, date, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np
import itertools

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats, teamgamelog
from nba_api.stats.static import teams

from engine_v2 import TEAM_ID_MAP, safe_get_data_frames
from self_learner import SelfLearner
from team_locations import (
    calculate_distance, get_timezone_difference, is_division_rival,
    is_conference_game, NBA_TEAM_LOCATIONS, NBA_DIVISIONS, NBA_CONFERENCES
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('backtest_v5_run.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

API_DELAY = 1.8
MAX_RETRIES = 3
TEAM_ABBREV_MAP = {t['abbreviation']: t['full_name'] for t in teams.get_teams()}
TEAM_NAME_TO_ID = {t['full_name']: t['id'] for t in teams.get_teams()}
TEAM_NAME_TO_ABBREV = {t['full_name']: t['abbreviation'] for t in teams.get_teams()}
HIGH_ALTITUDE_TEAMS = {"Denver Nuggets", "Utah Jazz"}

# Charlotte Hornets abbreviation
CHA_FULL = "Charlotte Hornets"

# Import shared utilities from v4 backtest
from backtest_v3_enhanced import (
    api_call_with_retry, _DictWrapper, _api_worker,
    fetch_all_team_stats, fetch_all_gamelogs, get_scoreboard_results,
    get_games_before_date, calc_rest_days, calc_recent_form,
    calc_home_away_pct, calc_win_streak, calc_scoring_margin_trend,
    calc_road_trip_length, calc_miles_traveled_7d, calc_overtime_games_7d,
    calc_revenge_game, is_trap_game, calc_altitude_factor,
    calc_b2b_status, calc_games_in_7_days,
    FACTOR_NORMS as V4_FACTOR_NORMS, normalize_factor as v4_normalize_factor
)

import multiprocessing
import socket

# ==================== NEW V5 FACTOR CALCULATIONS ====================

def calc_blowout_regression(gl, target_date):
    """Check if team won by 20+ in their last game (regression risk).
    Returns 1.0 if last game was a 20+ point win, 0.0 otherwise."""
    recent = get_games_before_date(gl, target_date)
    if recent.empty or 'PLUS_MINUS' not in recent.columns:
        return 0.0
    last_game = recent.iloc[0]
    try:
        pm = float(last_game['PLUS_MINUS'])
        if pm >= 20:
            return 1.0
        return 0.0
    except:
        return 0.0


def calc_last_margin(gl, target_date):
    """Get the margin of the last game (for blowout regression)"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty or 'PLUS_MINUS' not in recent.columns:
        return 0.0
    try:
        return float(recent.iloc[0]['PLUS_MINUS'])
    except:
        return 0.0


# ==================== V5 FACTOR COMPUTATION ====================

def compute_factors_v5(home_team, away_team, game_date, team_stats, gamelogs):
    """Compute ALL prediction factors with v5 fixes"""
    hs = team_stats.get(home_team, {})
    aws = team_stats.get(away_team, {})
    hgl = gamelogs.get(home_team, pd.DataFrame())
    agl = gamelogs.get(away_team, pd.DataFrame())

    factors = {}

    # === TEAM PERFORMANCE ===
    factors['season_win_pct'] = hs.get('win_pct', 0.5) - aws.get('win_pct', 0.5)

    # FIX #1: home_win_pct - make it a DIFFERENTIAL (home team's home% - away team's road%)
    # This prevents double-counting with other factors
    home_home_pct = calc_home_away_pct(hgl, game_date, True)
    away_road_pct = calc_home_away_pct(agl, game_date, False)
    factors['home_win_pct'] = home_home_pct - away_road_pct  # Differential: positive = home advantage in this matchup

    # away_win_pct: INVERTED (higher = away team worse on road = good for home)
    factors['away_win_pct'] = 1.0 - away_road_pct

    # Recent form
    factors['last_10_record'] = calc_recent_form(hgl, game_date, 10) - calc_recent_form(agl, game_date, 10)
    factors['last_5_record'] = calc_recent_form(hgl, game_date, 5) - calc_recent_form(agl, game_date, 5)

    # Advanced metrics
    factors['offensive_rating'] = hs.get('offensive_rating', 110) - aws.get('offensive_rating', 110)
    factors['defensive_rating'] = aws.get('defensive_rating', 110) - hs.get('defensive_rating', 110)
    factors['net_rating'] = hs.get('net_rating', 0) - aws.get('net_rating', 0)
    factors['pace'] = 0.0  # REMOVED
    factors['ppg'] = hs.get('ppg', 110) - aws.get('ppg', 110)
    factors['points_allowed'] = aws.get('opp_ppg', 110) - hs.get('opp_ppg', 110)

    # === SITUATIONAL ===
    hr = calc_rest_days(hgl, game_date)
    ar = calc_rest_days(agl, game_date)
    factors['rest_days'] = (hr - ar) / 3.0

    # FIX #3: day_of_week ZEROED (negatively correlated -0.0555)
    factors['day_of_week'] = 0.0
    factors['game_time'] = 0.0

    factors['travel_distance'] = 0.0
    try:
        tz_diff = get_timezone_difference(away_team, home_team)
        factors['timezone_change'] = abs(tz_diff) / 3.0
    except:
        factors['timezone_change'] = 0.0

    factors['days_since_last'] = (hr + ar) / 4.0

    # === MATCHUP ===
    factors['head_to_head'] = 0.0
    # FIX #3: division_rivalry ZEROED (negatively correlated -0.0421)
    factors['division_rivalry'] = 0.0
    factors['conference_game'] = 1.0 if is_conference_game(home_team, away_team) else 0.0

    # === ADVANCED ===
    factors['strength_of_schedule'] = 0.0
    factors['clutch_performance'] = hs.get('plus_minus', 0) - aws.get('plus_minus', 0)
    factors['turnover_diff'] = (aws.get('tov_pg', 14) - hs.get('tov_pg', 14))
    factors['rebound_diff'] = hs.get('reb_pg', 44) - aws.get('reb_pg', 44)
    factors['ft_rate_diff'] = hs.get('fta_pg', 22) - aws.get('fta_pg', 22)
    factors['three_pt_pct'] = hs.get('fg3_pct', 0.35) - aws.get('fg3_pct', 0.35)
    factors['assists_pg'] = hs.get('ast_pg', 25) - aws.get('ast_pg', 25)
    factors['defensive_activity'] = (hs.get('stl_pg', 8) + hs.get('blk_pg', 5)) - \
                                     (aws.get('stl_pg', 8) + aws.get('blk_pg', 5))

    # Injuries/Market (skip for backtest)
    factors['key_player_status'] = 0.0
    factors['star_player_penalty'] = 0.0
    factors['line_movement'] = 0.0
    factors['public_betting'] = 0.0
    factors['closing_line_value'] = 0.0

    # === NEW V3 FACTORS ===
    h_streak = calc_win_streak(hgl, game_date)
    a_streak = calc_win_streak(agl, game_date)
    factors['streak_diff'] = (h_streak - a_streak) / 10.0

    h_margin = calc_scoring_margin_trend(hgl, game_date, 5)
    a_margin = calc_scoring_margin_trend(agl, game_date, 5)
    factors['scoring_margin_trend'] = (h_margin - a_margin) / 15.0

    # FIX #2: away_road_trip ZEROED (negatively correlated -0.0746)
    factors['away_road_trip'] = 0.0

    h_miles = calc_miles_traveled_7d(hgl, game_date, home_team)
    a_miles = calc_miles_traveled_7d(agl, game_date, away_team)
    factors['miles_traveled_diff'] = (a_miles - h_miles) / 3000.0

    # FIX #3: overtime_fatigue ZEROED (negatively correlated -0.0677)
    factors['overtime_fatigue'] = 0.0

    h_revenge = calc_revenge_game(hgl, game_date, away_team)
    a_revenge = calc_revenge_game(agl, game_date, home_team)
    factors['revenge_game'] = (h_revenge - a_revenge)

    factors['trap_game'] = is_trap_game(home_team, away_team, team_stats)
    factors['altitude_factor'] = calc_altitude_factor(home_team, away_team)
    factors['arena_hostility'] = 0.0  # REMOVED
    factors['marquee_matchup'] = 0.0  # REMOVED

    h_b2b = calc_b2b_status(hgl, game_date)
    a_b2b = calc_b2b_status(agl, game_date)
    factors['b2b_status'] = (a_b2b - h_b2b) / 2.0

    h_density = calc_games_in_7_days(hgl, game_date)
    a_density = calc_games_in_7_days(agl, game_date)
    factors['schedule_density'] = (a_density - h_density) / 4.0

    factors['last_3_record'] = calc_recent_form(hgl, game_date, 3) - calc_recent_form(agl, game_date, 3)
    factors['oreb_diff'] = hs.get('oreb_pg', 10) - aws.get('oreb_pg', 10)
    factors['three_pt_volume'] = hs.get('fg3a_pg', 35) - aws.get('fg3a_pg', 35)

    # === NEW V5 FACTORS ===

    # Blowout regression: team that won by 20+ last game gets penalized
    h_blowout = calc_blowout_regression(hgl, game_date)
    a_blowout = calc_blowout_regression(agl, game_date)
    factors['blowout_regression'] = (a_blowout - h_blowout)  # Positive = away had blowout (good for home)

    # Charlotte Hornets chaos factor (applied post-prediction as confidence reduction)
    # We track it as a factor so it's visible, but the main effect is confidence reduction
    factors['cha_chaos'] = 0.0  # Placeholder, actual effect applied in predict function

    # Sanitize
    for k, v in factors.items():
        if not isinstance(v, (int, float)) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            factors[k] = 0.0

    return factors


# ==================== NORMALIZATION ====================

FACTOR_NORMS_V5 = dict(V4_FACTOR_NORMS)
# home_win_pct is now a differential (-1 to +1 range), not absolute
FACTOR_NORMS_V5['home_win_pct'] = 0.5  # typical differential range
FACTOR_NORMS_V5['blowout_regression'] = 1.0  # binary-ish
FACTOR_NORMS_V5['cha_chaos'] = 1.0


def normalize_factor_v5(name, value):
    norm = FACTOR_NORMS_V5.get(name, 1.0)
    # home_win_pct is now a differential, don't center at 0.5
    if name == 'away_win_pct':
        return (value - 0.5) / norm
    return value / norm if norm != 0 else 0.0


def predict_game_v5(factors, weights, home_team=None, away_team=None):
    """Generate prediction with v5 fixes including CHA chaos"""
    factors['home_court'] = 1.0

    home_score = 0.0
    for f in weights:
        raw = factors.get(f, 0)
        normalized = normalize_factor_v5(f, raw)
        normalized = max(-2.0, min(2.0, normalized))
        home_score += normalized * weights.get(f, 0)

    scaled = home_score * 3.0
    home_probability = 1.0 / (1.0 + math.exp(-scaled))
    home_probability = max(0.20, min(0.80, home_probability))

    if home_probability >= 0.5:
        confidence = home_probability * 100
        is_home = True
    else:
        confidence = (1 - home_probability) * 100
        is_home = False

    # Charlotte Hornets chaos factor: reduce confidence by 5% on any CHA game
    if home_team == CHA_FULL or away_team == CHA_FULL:
        confidence = max(50.0, confidence - 5.0)

    return confidence, is_home


# ==================== WEIGHT OPTIMIZATION ====================

def evaluate_weights(predictions_data, weights):
    """Evaluate a set of weights on pre-computed factor data.
    Returns (overall_accuracy, high_conf_accuracy, count)"""
    correct = 0
    total = 0
    high_conf_correct = 0
    high_conf_total = 0
    
    for p in predictions_data:
        factors = p['factors']
        actual_winner = p['actual_winner']
        home_team = p['home_team']
        away_team = p['away_team']
        
        confidence, is_home = predict_game_v5(factors, weights, home_team, away_team)
        predicted = home_team if is_home else away_team
        
        total += 1
        if predicted == actual_winner:
            correct += 1
        
        if confidence >= 65:
            high_conf_total += 1
            if predicted == actual_winner:
                high_conf_correct += 1
    
    overall_acc = correct / max(1, total)
    high_conf_acc = high_conf_correct / max(1, high_conf_total)
    
    return overall_acc, high_conf_acc, high_conf_total


def optimize_weights(train_data, val_data, base_weights):
    """Optimize weights using iterative coordinate descent on train, validate on val.
    For each factor, try multipliers and pick the one that maximizes train accuracy.
    Then validate on held-out data."""
    
    print("\n" + "=" * 70)
    print("WEIGHT OPTIMIZATION (Coordinate Descent)")
    print(f"Train: {len(train_data)} games, Validation: {len(val_data)} games")
    print("=" * 70)
    
    best_weights = dict(base_weights)
    
    # Get baseline
    train_acc, train_hc, _ = evaluate_weights(train_data, best_weights)
    val_acc, val_hc, val_hc_n = evaluate_weights(val_data, best_weights)
    print(f"\nBaseline - Train: {train_acc:.3f}, Val: {val_acc:.3f}, Val 65+: {val_hc:.3f} ({val_hc_n})")
    
    # Factors worth optimizing (non-zero weight, not removed)
    active_factors = [f for f, w in best_weights.items() if w > 0.001]
    multipliers = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    
    # Run 3 passes of coordinate descent
    for pass_num in range(3):
        improved = False
        for factor in active_factors:
            original_weight = best_weights[factor]
            best_score = -1
            best_mult = 1.0
            
            for mult in multipliers:
                test_weights = dict(best_weights)
                test_weights[factor] = original_weight * mult
                
                # Re-normalize
                total_w = sum(test_weights.values())
                if total_w > 0:
                    test_weights = {k: v / total_w for k, v in test_weights.items()}
                
                acc, hc_acc, hc_n = evaluate_weights(train_data, test_weights)
                # Score: weighted combo of overall and high-confidence accuracy
                score = acc * 0.6 + hc_acc * 0.4
                
                if score > best_score:
                    best_score = score
                    best_mult = mult
            
            if best_mult != 1.0:
                best_weights[factor] = original_weight * best_mult
                # Re-normalize
                total_w = sum(best_weights.values())
                if total_w > 0:
                    best_weights = {k: v / total_w for k, v in best_weights.items()}
                improved = True
        
        train_acc, train_hc, _ = evaluate_weights(train_data, best_weights)
        val_acc, val_hc, val_hc_n = evaluate_weights(val_data, best_weights)
        print(f"Pass {pass_num+1} - Train: {train_acc:.3f}, Val: {val_acc:.3f}, Val 65+: {val_hc:.3f} ({val_hc_n})")
        
        if not improved:
            print("  No improvement, stopping early")
            break
    
    # Final validation
    val_acc, val_hc, val_hc_n = evaluate_weights(val_data, best_weights)
    print(f"\nFinal Validation: {val_acc:.3f} overall, {val_hc:.3f} on 65%+ ({val_hc_n} games)")
    
    return best_weights


# ==================== MAIN BACKTEST ====================

def run_backtest():
    start_date = date(2026, 1, 1)
    end_date = date(2026, 2, 12)
    split_date = date(2026, 1, 22)  # Train: Jan 1-21, Val: Jan 22-Feb 12

    print("=" * 70)
    print("ParlayGuarantee Engine v5 - OPTIMIZED BACKTEST")
    print(f"Period: {start_date} to {end_date}")
    print(f"Train/Val Split: {split_date}")
    print(f"API delay: {API_DELAY}s, Max retries: {MAX_RETRIES}")
    print("=" * 70)

    db_path = "engine_data_v5.db"
    learner = SelfLearner(db_path)
    
    # Base weights from v4
    weights = learner.load_weights()
    
    # Apply v4 overrides
    weights['pace'] = 0.0
    weights['arena_hostility'] = 0.0
    weights['marquee_matchup'] = 0.0
    weights['rest_days'] = 0.10
    weights['clutch_performance'] = 0.06
    weights['turnover_diff'] = 0.05
    
    # V5 fixes: zero out negatively correlated factors
    weights['away_road_trip'] = 0.0  # was -0.0746
    weights['day_of_week'] = 0.0     # was -0.0555
    weights['division_rivalry'] = 0.0 # was -0.0421
    weights['overtime_fatigue'] = 0.0 # was -0.0677
    
    # New v5 factors
    weights['blowout_regression'] = 0.02
    weights['cha_chaos'] = 0.0  # Applied as confidence reduction, not weight
    
    # Add new factor weights from v4 if missing
    new_factor_weights = {
        'streak_diff': 0.03,
        'scoring_margin_trend': 0.07,
        'miles_traveled_diff': 0.02,
        'revenge_game': 0.02,
        'trap_game': 0.02,
        'altitude_factor': 0.03,
        'b2b_status': 0.07,
        'schedule_density': 0.05,
        'last_3_record': 0.03,
        'oreb_diff': 0.02,
        'three_pt_volume': 0.01,
    }
    for k, v in new_factor_weights.items():
        if k not in weights:
            weights[k] = v
    
    # Normalize weights
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    print(f"Using {len(weights)} factor weights (sum={sum(weights.values()):.3f})")

    # Pre-fetch all data
    team_stats = fetch_all_team_stats()
    print("\nPre-fetching all team gamelogs (30 teams)...")
    gamelogs = fetch_all_gamelogs()

    # ==================== PHASE 1: Collect all predictions data ====================
    print("\n" + "=" * 70)
    print("Phase 1: Computing factors for all games...")
    print("=" * 70)

    all_game_data = []  # Raw factor data for weight optimization
    current_date = start_date
    consecutive_empty = 0
    
    while current_date <= end_date:
        results = get_scoreboard_results(current_date)
        if not results:
            consecutive_empty += 1
            current_date += timedelta(days=1)
            continue
        
        consecutive_empty = 0
        print(f"  {current_date}: {len(results)} games")
        
        for game in results:
            home_team = game['home_team']
            away_team = game['away_team']
            actual_winner = game['actual_winner']
            
            try:
                factors = compute_factors_v5(home_team, away_team, current_date, team_stats, gamelogs)
                all_game_data.append({
                    'game_date': current_date,
                    'home_team': home_team,
                    'away_team': away_team,
                    'actual_winner': actual_winner,
                    'home_score': game['home_score'],
                    'away_score': game['away_score'],
                    'factors': factors,
                })
            except Exception as e:
                logger.error(f"Error computing factors for {away_team} @ {home_team}: {e}")
        
        current_date += timedelta(days=1)

    print(f"\nTotal games with factors: {len(all_game_data)}")

    # ==================== PHASE 2: Weight optimization ====================
    train_data = [g for g in all_game_data if g['game_date'] < split_date]
    val_data = [g for g in all_game_data if g['game_date'] >= split_date]
    
    print(f"Train: {len(train_data)} games (Jan 1-21)")
    print(f"Validation: {len(val_data)} games (Jan 22-Feb 12)")
    
    optimized_weights = optimize_weights(train_data, val_data, weights)

    # ==================== PHASE 3: Full backtest with optimized weights ====================
    print("\n" + "=" * 70)
    print("Phase 3: Full backtest with optimized weights")
    print("=" * 70)

    total_correct = 0
    total_predictions = 0
    by_confidence_tier = defaultdict(lambda: {'correct': 0, 'total': 0})
    home_picks = {'correct': 0, 'total': 0}
    away_picks = {'correct': 0, 'total': 0}
    factor_values_all = defaultdict(lambda: {'correct_vals': [], 'incorrect_vals': []})
    daily_results = []
    all_predictions = []
    
    # Group by date for daily reporting
    by_date = defaultdict(list)
    for g in all_game_data:
        by_date[g['game_date']].append(g)
    
    for game_date in sorted(by_date.keys()):
        games = by_date[game_date]
        day_correct = 0
        day_total = 0
        
        print(f"\n--- {game_date} ({game_date.strftime('%A')}) ---")
        
        for game in games:
            home_team = game['home_team']
            away_team = game['away_team']
            actual_winner = game['actual_winner']
            factors = game['factors']
            
            confidence, is_home = predict_game_v5(factors, optimized_weights, home_team, away_team)
            predicted_winner = home_team if is_home else away_team
            correct = (predicted_winner == actual_winner)
            
            # Record in self-learner
            game_id = f"{away_team}@{home_team}_{game_date.isoformat()}"
            learner.record_prediction(game_id, game_date, home_team, away_team,
                                     predicted_winner, confidence / 100, factors)
            learner.record_result(game_id, actual_winner)
            
            total_predictions += 1
            day_total += 1
            if correct:
                total_correct += 1
                day_correct += 1
            
            if is_home:
                home_picks['total'] += 1
                if correct: home_picks['correct'] += 1
            else:
                away_picks['total'] += 1
                if correct: away_picks['correct'] += 1
            
            tier = "70+" if confidence >= 70 else \
                   "65-70" if confidence >= 65 else \
                   "60-65" if confidence >= 60 else \
                   "55-60" if confidence >= 55 else "<55"
            
            by_confidence_tier[tier]['total'] += 1
            if correct:
                by_confidence_tier[tier]['correct'] += 1
            
            for fname, fval in factors.items():
                if correct:
                    factor_values_all[fname]['correct_vals'].append(fval)
                else:
                    factor_values_all[fname]['incorrect_vals'].append(fval)
            
            mark = "OK" if correct else "XX"
            cha_tag = " [CHA]" if home_team == CHA_FULL or away_team == CHA_FULL else ""
            print(f"  [{mark}] {away_team} @ {home_team}: "
                  f"Pred={predicted_winner} ({confidence:.0f}%) | "
                  f"Actual={actual_winner} ({game['away_score']}-{game['home_score']}){cha_tag}")
            
            all_predictions.append({
                'game_date': game_date.isoformat(),
                'home_team': home_team,
                'away_team': away_team,
                'predicted_winner': predicted_winner,
                'confidence': round(confidence, 1),
                'actual_winner': actual_winner,
                'home_score': game['home_score'],
                'away_score': game['away_score'],
                'correct': correct,
                'factors': {k: round(v, 4) for k, v in factors.items()}
            })
        
        if day_total > 0:
            day_acc = day_correct / day_total * 100
            daily_results.append({
                'date': game_date.isoformat(),
                'total': day_total,
                'correct': day_correct,
                'accuracy': round(day_acc, 1)
            })
            running_acc = total_correct / total_predictions * 100
            print(f"  Day: {day_correct}/{day_total} ({day_acc:.1f}%) | "
                  f"Running: {total_correct}/{total_predictions} ({running_acc:.1f}%)")

    # === FINAL REPORT ===
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS - v5 OPTIMIZED")
    print("=" * 70)

    if total_predictions == 0:
        print("No predictions were made!")
        return

    overall_acc = total_correct / total_predictions * 100
    print(f"\nOverall: {total_correct}/{total_predictions} ({overall_acc:.1f}%)")
    
    print(f"\nHome picks: {home_picks['correct']}/{home_picks['total']} "
          f"({home_picks['correct']/max(1,home_picks['total'])*100:.1f}%)")
    print(f"Away picks: {away_picks['correct']}/{away_picks['total']} "
          f"({away_picks['correct']/max(1,away_picks['total'])*100:.1f}%)")

    print("\nBy Confidence Tier:")
    for tier in ["70+", "65-70", "60-65", "55-60", "<55"]:
        d = by_confidence_tier.get(tier, {'correct': 0, 'total': 0})
        if d['total'] > 0:
            acc = d['correct'] / d['total'] * 100
            print(f"  {tier}%: {d['correct']}/{d['total']} ({acc:.1f}%)")
    
    # 65+ combined
    t65 = by_confidence_tier.get('65-70', {'correct': 0, 'total': 0})
    t70 = by_confidence_tier.get('70+', {'correct': 0, 'total': 0})
    c65 = t65['correct'] + t70['correct']
    n65 = t65['total'] + t70['total']
    if n65 > 0:
        print(f"  65%+ combined: {c65}/{n65} ({c65/n65*100:.1f}%)")

    # Charlotte Hornets analysis
    cha_games = [p for p in all_predictions if CHA_FULL in (p['home_team'], p['away_team'])]
    cha_correct = sum(1 for p in cha_games if p['correct'])
    if cha_games:
        print(f"\nCharlotte Hornets games: {cha_correct}/{len(cha_games)} ({cha_correct/len(cha_games)*100:.1f}%)")

    # Day of week analysis
    print("\nDay of Week Analysis:")
    dow_results = defaultdict(lambda: {'correct': 0, 'total': 0})
    for p in all_predictions:
        d = datetime.fromisoformat(p['game_date']).strftime('%A')
        dow_results[d]['total'] += 1
        if p['correct']:
            dow_results[d]['correct'] += 1
    for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
        d = dow_results.get(day, {'correct': 0, 'total': 0})
        if d['total'] > 0:
            print(f"  {day}: {d['correct']}/{d['total']} ({d['correct']/d['total']*100:.1f}%)")

    # Slate size analysis
    print("\nSlate Size Analysis (games per day vs accuracy):")
    slate_results = defaultdict(lambda: {'correct': 0, 'total': 0})
    for dr in daily_results:
        bucket = "1-5" if dr['total'] <= 5 else "6-8" if dr['total'] <= 8 else "9-12" if dr['total'] <= 12 else "13+"
        slate_results[bucket]['correct'] += dr['correct']
        slate_results[bucket]['total'] += dr['total']
    for bucket in ["1-5", "6-8", "9-12", "13+"]:
        d = slate_results.get(bucket, {'correct': 0, 'total': 0})
        if d['total'] > 0:
            print(f"  {bucket} games: {d['correct']}/{d['total']} ({d['correct']/d['total']*100:.1f}%)")

    # Train vs Val accuracy
    train_preds = [p for p in all_predictions if p['game_date'] < split_date.isoformat()]
    val_preds = [p for p in all_predictions if p['game_date'] >= split_date.isoformat()]
    train_correct = sum(1 for p in train_preds if p['correct'])
    val_correct = sum(1 for p in val_preds if p['correct'])
    print(f"\nTrain accuracy (Jan 1-21): {train_correct}/{len(train_preds)} ({train_correct/max(1,len(train_preds))*100:.1f}%)")
    print(f"Val accuracy (Jan 22-Feb 12): {val_correct}/{len(val_preds)} ({val_correct/max(1,len(val_preds))*100:.1f}%)")

    # Factor correlation analysis
    print("\n" + "=" * 70)
    print("FACTOR CORRELATION ANALYSIS")
    print("=" * 70)
    
    factor_correlations = {}
    for fname, data in factor_values_all.items():
        correct_vals = data['correct_vals']
        incorrect_vals = data['incorrect_vals']
        
        if len(correct_vals) > 5 and len(incorrect_vals) > 5:
            avg_c = np.mean(correct_vals)
            avg_i = np.mean(incorrect_vals)
            all_vals = correct_vals + incorrect_vals
            all_outcomes = [1] * len(correct_vals) + [0] * len(incorrect_vals)
            
            if np.std(all_vals) > 0:
                corr = np.corrcoef(all_vals, all_outcomes)[0, 1]
            else:
                corr = 0.0
            
            factor_correlations[fname] = {
                'avg_correct': round(avg_c, 4),
                'avg_incorrect': round(avg_i, 4),
                'diff': round(abs(avg_c - avg_i), 4),
                'correlation': round(corr, 4) if not np.isnan(corr) else 0.0,
                'weight': round(optimized_weights.get(fname, 0), 5)
            }
    
    sorted_factors = sorted(factor_correlations.items(), 
                           key=lambda x: abs(x[1]['correlation']), reverse=True)
    
    print("\nTop 15 Most Predictive Factors:")
    for i, (fname, d) in enumerate(sorted_factors[:15]):
        direction = "+" if d['correlation'] > 0 else "-"
        print(f"  {i+1}. {fname}: corr={direction}{abs(d['correlation']):.4f}, "
              f"weight={d['weight']:.5f}")
    
    print("\nNegatively Correlated Factors:")
    neg_factors = [(f, d) for f, d in sorted_factors if d['correlation'] < -0.02]
    for fname, d in neg_factors:
        print(f"  ⚠️  {fname}: corr={d['correlation']:.4f}, weight={d['weight']:.5f}")

    print("\nDaily Performance:")
    for day in daily_results:
        print(f"  {day['date']}: {day['correct']}/{day['total']} ({day['accuracy']}%)")

    # Save results
    results_data = {
        'backtest_period': f"{start_date} to {end_date}",
        'engine_version': 'v5-optimized',
        'total_factors': len(optimized_weights),
        'overall': {
            'total_predictions': total_predictions,
            'correct': total_correct,
            'accuracy': round(overall_acc, 1)
        },
        'home_picks': home_picks,
        'away_picks': away_picks,
        'by_confidence_tier': {k: {
            'correct': v['correct'], 'total': v['total'],
            'accuracy': round(v['correct']/v['total']*100, 1) if v['total'] > 0 else 0
        } for k, v in by_confidence_tier.items()},
        'sixty_five_plus': {
            'correct': c65, 'total': n65,
            'accuracy': round(c65/max(1,n65)*100, 1)
        },
        'train_val_split': {
            'train_accuracy': round(train_correct/max(1,len(train_preds))*100, 1),
            'val_accuracy': round(val_correct/max(1,len(val_preds))*100, 1),
            'train_games': len(train_preds),
            'val_games': len(val_preds),
        },
        'factor_correlations': dict(sorted_factors),
        'daily_results': daily_results,
        'weights_used': {k: round(v, 6) for k, v in optimized_weights.items()},
        'all_predictions': all_predictions,
        'generated_at': datetime.now().isoformat()
    }

    with open('backtest_v5_results.json', 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to backtest_v5_results.json")
    print("Done!")
    
    return results_data


if __name__ == "__main__":
    run_backtest()
