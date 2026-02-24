"""
ParlayGuarantee Engine v2 - Full Backtest (Optimized)
Pre-fetches all team gamelogs to minimize API calls.
Tests predictions against actual NBA results from Jan 1 - Feb 12, 2026
"""

import sys
import json
import time
import logging
import sqlite3
import math
from datetime import datetime, date, timedelta
from collections import defaultdict
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats, teamgamelog
from nba_api.stats.static import teams

from engine_v2 import TEAM_ID_MAP, safe_get_data_frames
from self_learner import SelfLearner
from team_locations import calculate_distance, get_timezone_difference, is_division_rival, is_conference_game

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('backtest_v2_run.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

API_DELAY = 1.0
TEAM_ABBREV_MAP = {t['abbreviation']: t['full_name'] for t in teams.get_teams()}
TEAM_NAME_TO_ID = {t['full_name']: t['id'] for t in teams.get_teams()}


def api_sleep():
    time.sleep(API_DELAY)


def fetch_all_team_stats():
    """Fetch basic + advanced team stats"""
    print("Fetching team stats (basic)...")
    api_sleep()
    basic = leaguedashteamstats.LeagueDashTeamStats(season='2024-25', league_id_nullable='00', timeout=60)
    basic_df = safe_get_data_frames(basic)[0]
    
    print("Fetching team stats (advanced)...")
    api_sleep()
    adv = leaguedashteamstats.LeagueDashTeamStats(
        season='2024-25', league_id_nullable='00',
        measure_type_detailed_defense='Advanced', timeout=60
    )
    adv_df = safe_get_data_frames(adv)[0]
    adv_by_id = {row['TEAM_ID']: row for _, row in adv_df.iterrows()}
    
    team_stats = {}
    for _, row in basic_df.iterrows():
        tid = row['TEAM_ID']
        name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
        gp = max(row['GP'], 1)
        adv_row = adv_by_id.get(tid, {})
        
        ppg = row['PTS'] / gp
        pm_pg = row['PLUS_MINUS'] / gp
        
        team_stats[name] = {
            'win_pct': row['W_PCT'],
            'ppg': ppg,
            'opp_ppg': ppg - pm_pg,
            'plus_minus': pm_pg,
            'offensive_rating': adv_row.get('OFF_RATING', 110) if isinstance(adv_row, pd.Series) else 110,
            'defensive_rating': adv_row.get('DEF_RATING', 110) if isinstance(adv_row, pd.Series) else 110,
            'net_rating': adv_row.get('NET_RATING', 0) if isinstance(adv_row, pd.Series) else 0,
            'pace': adv_row.get('PACE', 100) if isinstance(adv_row, pd.Series) else 100,
            'fg_pct': row['FG_PCT'],
            'fg3_pct': row['FG3_PCT'],
            'ft_pct': row['FT_PCT'],
            'fg3a_pg': row['FG3A'] / gp,
            'fta_pg': row['FTA'] / gp,
            'reb_pg': row['REB'] / gp,
            'oreb_pg': row['OREB'] / gp,
            'ast_pg': row['AST'] / gp,
            'tov_pg': row['TOV'] / gp,
            'stl_pg': row['STL'] / gp,
            'blk_pg': row['BLK'] / gp,
        }
    
    print(f"Loaded stats for {len(team_stats)} teams")
    return team_stats


def fetch_all_gamelogs():
    """Pre-fetch gamelogs for all 30 NBA teams"""
    gamelogs = {}
    nba_teams = teams.get_teams()
    
    for i, team in enumerate(nba_teams):
        tid = team['id']
        name = team['full_name']
        print(f"  Fetching gamelog {i+1}/30: {name}...", end=" ", flush=True)
        api_sleep()
        try:
            gl = teamgamelog.TeamGameLog(team_id=tid, season='2024-25', timeout=60)
            data = gl.get_dict()
            rs = data['resultSets'][0]
            headers = rs['headers']
            rows = rs['rowSet']
            df = pd.DataFrame(rows, columns=headers)
            df['GAME_DATE_PARSED'] = pd.to_datetime(df['GAME_DATE'], format='mixed')
            gamelogs[name] = df
            print(f"{len(df)} games")
        except Exception as e:
            print(f"ERROR: {e}")
            gamelogs[name] = pd.DataFrame()
    
    return gamelogs


def get_scoreboard_results(game_date: date, retries: int = 3) -> list:
    """Fetch actual game results for a date"""
    date_str = game_date.strftime('%m/%d/%Y')
    for attempt in range(retries):
        try:
            api_sleep()
            sb = scoreboardv2.ScoreboardV2(game_date=date_str, timeout=60)
            data = sb.get_dict()
            result_sets = data['resultSets']
            header_rs = result_sets[0]
            line_rs = result_sets[1]
            
            h_headers = header_rs['headers']
            l_headers = line_rs['headers']
            
            pts_idx = l_headers.index('PTS')
            tid_idx = l_headers.index('TEAM_ID')
            gid_idx_l = l_headers.index('GAME_ID')
            
            line_lookup = {}
            for row in line_rs['rowSet']:
                line_lookup[(row[gid_idx_l], row[tid_idx])] = row[pts_idx]
            
            gid_idx = h_headers.index('GAME_ID')
            home_idx = h_headers.index('HOME_TEAM_ID')
            away_idx = h_headers.index('VISITOR_TEAM_ID')
            
            results = []
            for row in header_rs['rowSet']:
                game_id = row[gid_idx]
                home_id = row[home_idx]
                away_id = row[away_idx]
                home_team = TEAM_ID_MAP.get(home_id, f"Team_{home_id}")
                away_team = TEAM_ID_MAP.get(away_id, f"Team_{away_id}")
                
                home_pts = line_lookup.get((game_id, home_id))
                away_pts = line_lookup.get((game_id, away_id))
                
                if home_pts is None or away_pts is None:
                    continue
                try:
                    home_pts, away_pts = int(home_pts), int(away_pts)
                except (ValueError, TypeError):
                    continue
                if home_pts == 0 and away_pts == 0:
                    continue
                
                results.append({
                    'game_id': game_id,
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_score': home_pts,
                    'away_score': away_pts,
                    'actual_winner': home_team if home_pts > away_pts else away_team,
                })
            return results
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} for {game_date}: {e}")
            time.sleep(3)
    return []


def compute_factors(home_team, away_team, game_date, team_stats, gamelogs):
    """Compute prediction factors using pre-fetched data (no API calls)"""
    hs = team_stats.get(home_team, {})
    aws = team_stats.get(away_team, {})
    hgl = gamelogs.get(home_team, pd.DataFrame())
    agl = gamelogs.get(away_team, pd.DataFrame())
    
    factors = {}
    
    # 1. Season win pct diff
    factors['season_win_pct'] = hs.get('win_pct', 0.5) - aws.get('win_pct', 0.5)
    
    # 2-3. Home/Away splits from gamelogs
    def get_home_away_pct(gl, is_home=True):
        if gl.empty:
            return 0.58 if is_home else 0.42
        if is_home:
            games = gl[~gl['MATCHUP'].str.contains('@', na=False)]
        else:
            games = gl[gl['MATCHUP'].str.contains('@', na=False)]
        if games.empty:
            return 0.58 if is_home else 0.42
        wins = len(games[games['WL'] == 'W'])
        return wins / len(games)
    
    factors['home_win_pct'] = get_home_away_pct(hgl, True)
    factors['away_win_pct'] = get_home_away_pct(agl, False)
    
    # 4-5. Recent form
    def recent_form(gl, n):
        if gl.empty:
            return 0.5
        recent = gl.head(n)
        wins = len(recent[recent['WL'] == 'W'])
        return wins / max(1, len(recent))
    
    factors['last_10_record'] = recent_form(hgl, 10) - recent_form(agl, 10)
    factors['last_5_record'] = recent_form(hgl, 5) - recent_form(agl, 5)
    
    # 6-11. Advanced metrics
    factors['offensive_rating'] = hs.get('offensive_rating', 110) - aws.get('defensive_rating', 110)
    factors['defensive_rating'] = aws.get('offensive_rating', 110) - hs.get('defensive_rating', 110)
    factors['net_rating'] = hs.get('net_rating', 0) - aws.get('net_rating', 0)
    factors['pace'] = (hs.get('pace', 100) + aws.get('pace', 100)) / 200
    factors['ppg'] = hs.get('ppg', 110) - aws.get('ppg', 110)
    factors['points_allowed'] = aws.get('opp_ppg', 110) - hs.get('opp_ppg', 110)
    
    # 12. Rest days
    def rest_days(gl, target_date):
        if gl.empty or 'GAME_DATE_PARSED' not in gl.columns:
            return 2
        target_dt = pd.Timestamp(datetime.combine(target_date, datetime.min.time()))
        recent = gl[gl['GAME_DATE_PARSED'] < target_dt]
        if recent.empty:
            return 2
        last = recent.iloc[0]['GAME_DATE_PARSED']
        return max(0, (target_dt - last).days - 1)
    
    hr = rest_days(hgl, game_date)
    ar = rest_days(agl, game_date)
    factors['rest_days'] = (hr - ar) / 3.0
    
    # 13-14.
    factors['day_of_week'] = game_date.weekday() / 6.0
    factors['game_time'] = 0.0
    
    # 15-16. Travel/timezone
    factors['travel_distance'] = 0.0  # Simplified
    try:
        tz_diff = get_timezone_difference(away_team, home_team)
        factors['timezone_change'] = abs(tz_diff) / 3.0
    except:
        factors['timezone_change'] = 0.0
    
    factors['days_since_last'] = (hr + ar) / 4.0
    
    # 18-20. Matchup
    factors['head_to_head'] = 0.0
    factors['division_rivalry'] = 1.0 if is_division_rival(home_team, away_team) else 0.0
    factors['conference_game'] = 1.0 if is_conference_game(home_team, away_team) else 0.0
    
    # 21. SOS (simplified - use team stats win_pct as proxy)
    factors['strength_of_schedule'] = 0.0
    
    # 22-28. Statistical differentials
    factors['clutch_performance'] = hs.get('plus_minus', 0) - aws.get('plus_minus', 0)
    factors['turnover_diff'] = 0.0
    factors['rebound_diff'] = (hs.get('reb_pg', 44) - 44) - (aws.get('reb_pg', 44) - 44)
    factors['ft_rate_diff'] = 0.0
    factors['three_pt_pct'] = hs.get('fg3_pct', 0.35) - aws.get('fg3_pct', 0.35)
    factors['assists_pg'] = hs.get('ast_pg', 25) - aws.get('ast_pg', 25)
    factors['defensive_activity'] = (hs.get('stl_pg', 8) + hs.get('blk_pg', 5)) - \
                                     (aws.get('stl_pg', 8) + aws.get('blk_pg', 5))
    
    # 29-30. Injury proxy
    factors['key_player_status'] = 0.0
    factors['star_player_penalty'] = 0.0
    
    # 31-33. Market (skip for backtest)
    factors['line_movement'] = 0.0
    factors['public_betting'] = 0.0
    factors['closing_line_value'] = 0.0
    
    # Sanitize
    for k, v in factors.items():
        if not isinstance(v, (int, float)) or (isinstance(v, float) and math.isnan(v)):
            factors[k] = 0.0
    
    return factors


## Factor normalization ranges (must match engine_v2.py FACTOR_NORMS)
FACTOR_NORMS = {
    'season_win_pct': 0.4, 'home_win_pct': 0.5, 'away_win_pct': 0.5,
    'last_10_record': 0.5, 'last_5_record': 0.6,
    'offensive_rating': 10.0, 'defensive_rating': 10.0, 'net_rating': 10.0,
    'pace': 0.1, 'ppg': 15.0, 'points_allowed': 15.0,
    'rest_days': 1.0, 'day_of_week': 1.0, 'game_time': 1.0,
    'travel_distance': 1.0, 'timezone_change': 1.0, 'days_since_last': 1.0,
    'head_to_head': 0.5, 'division_rivalry': 1.0, 'conference_game': 1.0,
    'strength_of_schedule': 0.15, 'clutch_performance': 8.0,
    'turnover_diff': 4.0, 'rebound_diff': 6.0, 'ft_rate_diff': 0.1,
    'three_pt_pct': 0.06, 'assists_pg': 6.0, 'defensive_activity': 4.0,
    'key_player_status': 0.1, 'star_player_penalty': 0.1,
    'line_movement': 1.0, 'public_betting': 1.0, 'closing_line_value': 1.0,
    'home_court': 1.0,
}

def normalize_factor(name, value):
    norm = FACTOR_NORMS.get(name, 1.0)
    if name in ('home_win_pct', 'away_win_pct'):
        return (value - 0.5) / norm
    return value / norm if norm != 0 else 0.0


def predict_game(factors, weights):
    """Generate prediction from factors and weights (v2 fixed)"""
    # Add home court as explicit factor
    factors['home_court'] = 1.0
    
    home_score = 0.0
    for f in weights:
        raw = factors.get(f, 0)
        normalized = normalize_factor(f, raw)
        normalized = max(-2.0, min(2.0, normalized))
        home_score += normalized * weights.get(f, 0)
    
    # Scale and apply logistic function
    scaled = home_score * 3.0
    home_probability = 1.0 / (1.0 + math.exp(-scaled))
    
    # Clamp to realistic NBA range
    home_probability = max(0.20, min(0.80, home_probability))
    
    if home_probability >= 0.5:
        return home_probability * 100, True  # confidence, home_wins
    else:
        return (1 - home_probability) * 100, False


def run_backtest():
    start_date = date(2026, 1, 1)
    end_date = date(2026, 2, 12)
    
    print("=" * 70)
    print("ParlayGuarantee Engine v2 - FULL BACKTEST (Optimized)")
    print(f"Period: {start_date} to {end_date}")
    print("=" * 70)
    
    # Initialize self-learner
    db_path = "engine_data.db"
    learner = SelfLearner(db_path)
    weights = learner.load_weights()
    print(f"Loaded {len(weights)} factor weights")
    
    # Pre-fetch all data
    team_stats = fetch_all_team_stats()
    print("\nPre-fetching all team gamelogs (30 teams)...")
    gamelogs = fetch_all_gamelogs()
    
    print("\n" + "=" * 70)
    print("Starting backtest predictions...")
    print("=" * 70)
    
    all_predictions = []
    total_correct = 0
    total_predictions = 0
    by_confidence_tier = defaultdict(lambda: {'correct': 0, 'total': 0})
    factor_values_correct = defaultdict(list)
    factor_values_incorrect = defaultdict(list)
    daily_results = []
    
    current_date = start_date
    while current_date <= end_date:
        print(f"\n--- {current_date} ({current_date.strftime('%A')}) ---")
        
        results = get_scoreboard_results(current_date)
        
        if not results:
            print(f"  No completed games")
            current_date += timedelta(days=1)
            continue
        
        print(f"  {len(results)} games")
        day_correct = 0
        day_total = 0
        
        for game in results:
            home_team = game['home_team']
            away_team = game['away_team']
            actual_winner = game['actual_winner']
            
            try:
                factors = compute_factors(home_team, away_team, current_date, team_stats, gamelogs)
                confidence, home_wins = predict_game(factors, weights)
                predicted_winner = home_team if home_wins else away_team
                correct = (predicted_winner == actual_winner)
                
                # Record in self-learner
                game_id = f"{away_team}@{home_team}_{current_date.isoformat()}"
                learner.record_prediction(game_id, current_date, home_team, away_team,
                                         predicted_winner, confidence / 100, factors)
                learner.record_result(game_id, actual_winner)
                
                total_predictions += 1
                day_total += 1
                if correct:
                    total_correct += 1
                    day_correct += 1
                
                tier = "70+" if confidence >= 70 else \
                       "65-70" if confidence >= 65 else \
                       "60-65" if confidence >= 60 else \
                       "55-60" if confidence >= 55 else "<55"
                
                by_confidence_tier[tier]['total'] += 1
                if correct:
                    by_confidence_tier[tier]['correct'] += 1
                
                for fname, fval in factors.items():
                    if correct:
                        factor_values_correct[fname].append(fval)
                    else:
                        factor_values_incorrect[fname].append(fval)
                
                mark = "OK" if correct else "XX"
                print(f"  [{mark}] {away_team} @ {home_team}: "
                      f"Pred={predicted_winner} ({confidence:.0f}%) | "
                      f"Actual={actual_winner} ({game['away_score']}-{game['home_score']})")
                
                all_predictions.append({
                    'game_date': current_date.isoformat(),
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
            except Exception as e:
                logger.error(f"Error: {away_team} @ {home_team}: {e}")
                import traceback; traceback.print_exc()
        
        if day_total > 0:
            day_acc = day_correct / day_total * 100
            daily_results.append({
                'date': current_date.isoformat(),
                'total': day_total,
                'correct': day_correct,
                'accuracy': round(day_acc, 1)
            })
            print(f"  Day: {day_correct}/{day_total} ({day_acc:.1f}%) | Running: {total_correct}/{total_predictions} ({total_correct/total_predictions*100:.1f}%)")
        
        current_date += timedelta(days=1)
    
    # === REPORT ===
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    
    if total_predictions == 0:
        print("No predictions were made!")
        return
    
    overall_acc = total_correct / total_predictions * 100
    print(f"\nOverall: {total_correct}/{total_predictions} ({overall_acc:.1f}%)")
    
    print("\nBy Confidence Tier:")
    for tier in sorted(by_confidence_tier.keys(), reverse=True):
        d = by_confidence_tier[tier]
        acc = d['correct'] / d['total'] * 100 if d['total'] > 0 else 0
        print(f"  {tier}%: {d['correct']}/{d['total']} ({acc:.1f}%)")
    
    print("\nTop Factor Correlations:")
    factor_diffs = {}
    for fname in factor_values_correct:
        if fname in factor_values_incorrect and len(factor_values_correct[fname]) > 5:
            avg_c = sum(factor_values_correct[fname]) / len(factor_values_correct[fname])
            avg_i = sum(factor_values_incorrect[fname]) / len(factor_values_incorrect[fname])
            factor_diffs[fname] = {'avg_correct': avg_c, 'avg_incorrect': avg_i, 'diff': abs(avg_c - avg_i)}
    
    sorted_factors = sorted(factor_diffs.items(), key=lambda x: x[1]['diff'], reverse=True)
    for fname, d in sorted_factors[:15]:
        print(f"  {fname}: correct={d['avg_correct']:.4f}, incorrect={d['avg_incorrect']:.4f}, diff={d['diff']:.4f}")
    
    print("\nDaily Performance:")
    for day in daily_results:
        print(f"  {day['date']}: {day['correct']}/{day['total']} ({day['accuracy']}%)")
    
    results_data = {
        'backtest_period': f"{start_date} to {end_date}",
        'overall': {'total_predictions': total_predictions, 'correct': total_correct, 'accuracy': round(overall_acc, 1)},
        'by_confidence_tier': {k: {'correct': v['correct'], 'total': v['total'],
            'accuracy': round(v['correct']/v['total']*100, 1) if v['total'] > 0 else 0}
            for k, v in by_confidence_tier.items()},
        'factor_analysis': {k: v for k, v in sorted_factors[:20]},
        'daily_results': daily_results,
        'all_predictions': all_predictions,
        'generated_at': datetime.now().isoformat()
    }
    
    with open('backtest_v2_results.json', 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to backtest_v2_results.json")
    print("Done!")


if __name__ == "__main__":
    run_backtest()
