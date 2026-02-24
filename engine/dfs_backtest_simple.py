"""
Simple DFS Backtest - End-to-end working backtest
Tests 10 dates with simple greedy lineup construction
"""

import time
import json
import pandas as pd
from datetime import datetime
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3, leaguegamelog
from typing import Dict, List, Tuple
import os

# Test dates (10 dates from Dec 2024 to Jan 2025)
TEST_DATES = [
    "2024-12-01", "2024-12-05", "2024-12-10", "2024-12-15", "2024-12-20", 
    "2024-12-25", "2024-12-30", "2025-01-05", "2025-01-10", "2025-01-15"
]

# Position mappings from NBA API to DFS platforms
POSITION_MAP = {
    'G': ['PG', 'SG'],
    'F': ['SF', 'PF'], 
    'C': ['C', 'PF'],
    'G-F': ['PG', 'SG', 'SF', 'PF'],
    'F-G': ['PG', 'SG', 'SF', 'PF'],
    'F-C': ['SF', 'PF', 'C'],
    'C-F': ['PF', 'C'],
    '': ['PG', 'SG', 'SF', 'PF', 'C']  # Default if position missing
}

# DraftKings lineup requirements: 8 players, $50K
DK_POSITIONS = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']
DK_SALARY_CAP = 50000

# FanDuel lineup requirements: 9 players, $60K  
FD_POSITIONS = ['PG', 'PG', 'SG', 'SG', 'SF', 'SF', 'PF', 'PF', 'C']
FD_SALARY_CAP = 60000

def calculate_dk_score(player_stats):
    """Calculate DraftKings fantasy points"""
    pts = player_stats.get('points', 0) or 0
    fg3m = player_stats.get('threePointersMade', 0) or 0
    reb = player_stats.get('reboundsTotal', 0) or 0
    ast = player_stats.get('assists', 0) or 0
    stl = player_stats.get('steals', 0) or 0
    blk = player_stats.get('blocks', 0) or 0
    tov = player_stats.get('turnovers', 0) or 0
    
    score = (pts * 1.0 + fg3m * 0.5 + reb * 1.25 + ast * 1.5 + 
             stl * 2.0 + blk * 2.0 + tov * (-0.5))
    
    # Bonuses
    double_stats = [pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10]
    if sum(double_stats) >= 2:
        score += 1.5
        if sum(double_stats) >= 3:
            score += 3.0
    
    return score

def calculate_fd_score(player_stats):
    """Calculate FanDuel fantasy points"""
    pts = player_stats.get('points', 0) or 0
    reb = player_stats.get('reboundsTotal', 0) or 0
    ast = player_stats.get('assists', 0) or 0
    stl = player_stats.get('steals', 0) or 0
    blk = player_stats.get('blocks', 0) or 0
    tov = player_stats.get('turnovers', 0) or 0
    
    return (pts * 1.0 + reb * 1.2 + ast * 1.5 + 
            stl * 3.0 + blk * 3.0 + tov * (-1.0))

def get_player_season_cache():
    """Get or create season-long player cache"""
    cache_file = 'player_season_cache.json'
    
    if os.path.exists(cache_file):
        print("Loading cached season data...")
        with open(cache_file, 'r') as f:
            return json.load(f)
    
    print("Building season cache... This may take a few minutes.")
    try:
        # Get all player game logs for 2024-25 season
        gamelog = leaguegamelog.LeagueGameLog(
            season='2024-25', 
            player_or_team_abbreviation='P'
        )
        time.sleep(2)
        
        df = gamelog.get_data_frames()[0]
        cache = {}
        
        # Process each game log entry using correct column names
        for _, game in df.iterrows():
            player_id = str(game['PLAYER_ID'])
            game_date = game['GAME_DATE']
            
            if player_id not in cache:
                cache[player_id] = {
                    'name': game['PLAYER_NAME'],
                    'games': []
                }
            
            # Store game stats with DK/FD scores using correct column names
            game_stats = {
                'date': game_date,
                'points': game.get('PTS', 0) or 0,
                'threePointersMade': game.get('FG3M', 0) or 0,
                'reboundsTotal': game.get('REB', 0) or 0,
                'assists': game.get('AST', 0) or 0,
                'steals': game.get('STL', 0) or 0,
                'blocks': game.get('BLK', 0) or 0,
                'turnovers': game.get('TOV', 0) or 0,
            }
            game_stats['dk_score'] = calculate_dk_score(game_stats)
            game_stats['fd_score'] = calculate_fd_score(game_stats)
            
            cache[player_id]['games'].append(game_stats)
        
        # Save cache
        with open(cache_file, 'w') as f:
            json.dump(cache, f)
        
        print(f"Cached {len(cache)} players")
        return cache
        
    except Exception as e:
        print(f"Error building cache: {e}")
        return {}

def get_games_for_date(date_str):
    """Get games for a specific date"""
    try:
        scoreboard = scoreboardv2.ScoreboardV2(game_date=date_str)
        time.sleep(2)
        games = scoreboard.get_data_frames()[0]
        return games['GAME_ID'].tolist() if not games.empty else []
    except Exception as e:
        print(f"Error getting games for {date_str}: {e}")
        return []

def get_boxscore_stats(game_id):
    """Get player stats for a game"""
    try:
        boxscore = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        time.sleep(2)
        return boxscore.get_data_frames()[0]
    except Exception as e:
        print(f"Error getting boxscore for {game_id}: {e}")
        return pd.DataFrame()

def get_player_projections(player_id, test_date, season_cache):
    """Get projections for a player based on games before test_date"""
    if player_id not in season_cache:
        return 0, 0
    
    games = season_cache[player_id]['games']
    prior_games = [g for g in games if g['date'] < test_date]
    
    if not prior_games:
        return 0, 0
    
    # Average of last 10 games (or all if fewer)
    recent_games = prior_games[-10:]
    avg_dk = sum(g['dk_score'] for g in recent_games) / len(recent_games)
    avg_fd = sum(g['fd_score'] for g in recent_games) / len(recent_games)
    
    return avg_dk, avg_fd

def estimate_salary(avg_score, platform='DK'):
    """Estimate salary based on average score"""
    salary = avg_score * 200 + 3000
    if platform == 'DK':
        return max(3500, min(12000, int(salary)))
    else:  # FD
        return max(4000, min(12000, int(salary)))

def build_lineup_greedy(players, positions, salary_cap, platform='DK'):
    """Build lineup using greedy approach"""
    lineup = []
    total_salary = 0
    used_players = set()
    
    # Sort players by value (proj_score / salary)
    value_key = 'dk_value' if platform == 'DK' else 'fd_value'
    players_sorted = sorted([p for p in players if p[value_key] > 0], 
                          key=lambda x: x[value_key], reverse=True)
    
    for pos in positions:
        best_player = None
        
        if pos == 'G':  # DK flex guard
            eligible = [p for p in players_sorted 
                       if p['id'] not in used_players 
                       and any(dp in POSITION_MAP.get(p['position'], []) for dp in ['PG', 'SG'])
                       and total_salary + p[f'{platform.lower()}_salary'] <= salary_cap]
        elif pos == 'F':  # DK flex forward
            eligible = [p for p in players_sorted 
                       if p['id'] not in used_players 
                       and any(dp in POSITION_MAP.get(p['position'], []) for dp in ['SF', 'PF'])
                       and total_salary + p[f'{platform.lower()}_salary'] <= salary_cap]
        elif pos == 'UTIL':  # DK utility (any position)
            eligible = [p for p in players_sorted 
                       if p['id'] not in used_players
                       and total_salary + p[f'{platform.lower()}_salary'] <= salary_cap]
        else:  # Specific position
            eligible = [p for p in players_sorted 
                       if p['id'] not in used_players 
                       and pos in POSITION_MAP.get(p['position'], [])
                       and total_salary + p[f'{platform.lower()}_salary'] <= salary_cap]
        
        if eligible:
            best_player = eligible[0]
            lineup.append(best_player)
            total_salary += best_player[f'{platform.lower()}_salary']
            used_players.add(best_player['id'])
    
    return lineup, total_salary

def score_lineup(lineup, actual_stats, platform='DK'):
    """Score a lineup using actual player performances"""
    total_score = 0
    
    for player in lineup:
        player_actual = next((p for p in actual_stats if str(p.get('personId', '')) == player['id']), None)
        if player_actual:
            if platform == 'DK':
                total_score += calculate_dk_score(player_actual)
            else:
                total_score += calculate_fd_score(player_actual)
    
    return total_score

def backtest_date(date_str, season_cache):
    """Backtest a single date"""
    print(f"\nBacktesting {date_str}...")
    
    # Get games for this date
    game_ids = get_games_for_date(date_str)
    if not game_ids:
        print(f"  No games found for {date_str}")
        return None
    
    print(f"  Found {len(game_ids)} games")
    
    # Get all player stats for the day
    all_players = []
    actual_stats = []
    
    for game_id in game_ids:
        boxscore = get_boxscore_stats(game_id)
        if not boxscore.empty:
            for _, player in boxscore.iterrows():
                # Skip players with no minutes
                if not player.get('minutes') or player['minutes'] == '0:00':
                    continue
                    
                player_id = str(player['personId'])
                
                # Get projections
                proj_dk, proj_fd = get_player_projections(player_id, date_str, season_cache)
                
                if proj_dk > 5:  # Only include players with some projection
                    # Estimate salaries
                    sal_dk = estimate_salary(proj_dk, 'DK')
                    sal_fd = estimate_salary(proj_fd, 'FD')
                    
                    player_data = {
                        'id': player_id,
                        'name': f"{player['firstName']} {player['familyName']}",
                        'position': player.get('position', ''),
                        'dk_projection': proj_dk,
                        'fd_projection': proj_fd,
                        'dk_salary': sal_dk,
                        'fd_salary': sal_fd,
                        'dk_value': proj_dk / (sal_dk / 1000) if sal_dk > 0 else 0,
                        'fd_value': proj_fd / (sal_fd / 1000) if sal_fd > 0 else 0
                    }
                    
                    all_players.append(player_data)
                    actual_stats.append(player.to_dict())
    
    if len(all_players) < 15:
        print(f"  Not enough players ({len(all_players)}) for meaningful lineups")
        return None
    
    print(f"  Processing {len(all_players)} players")
    
    # Build lineups
    dk_lineups = []
    fd_lineups = []
    
    # Build 5 DK lineups
    for i in range(5):
        lineup, salary = build_lineup_greedy(all_players, DK_POSITIONS, DK_SALARY_CAP, 'DK')
        if len(lineup) == 8:
            actual_score = score_lineup(lineup, actual_stats, 'DK')
            dk_lineups.append({
                'lineup': lineup,
                'salary': salary,
                'actual_score': actual_score,
                'strategy': f'Greedy {i+1}'
            })
        # Remove top player to get different lineup next time
        if all_players:
            all_players.pop(0)
    
    # Reset players for FD
    all_players = []
    for game_id in game_ids:
        boxscore = get_boxscore_stats(game_id)
        if not boxscore.empty:
            for _, player in boxscore.iterrows():
                if not player.get('minutes') or player['minutes'] == '0:00':
                    continue
                    
                player_id = str(player['personId'])
                proj_dk, proj_fd = get_player_projections(player_id, date_str, season_cache)
                
                if proj_fd > 5:
                    sal_dk = estimate_salary(proj_dk, 'DK')
                    sal_fd = estimate_salary(proj_fd, 'FD')
                    
                    player_data = {
                        'id': player_id,
                        'name': f"{player['firstName']} {player['familyName']}",
                        'position': player.get('position', ''),
                        'dk_projection': proj_dk,
                        'fd_projection': proj_fd,
                        'dk_salary': sal_dk,
                        'fd_salary': sal_fd,
                        'dk_value': proj_dk / (sal_dk / 1000) if sal_dk > 0 else 0,
                        'fd_value': proj_fd / (sal_fd / 1000) if sal_fd > 0 else 0
                    }
                    all_players.append(player_data)
    
    # Build 5 FD lineups
    for i in range(5):
        lineup, salary = build_lineup_greedy(all_players, FD_POSITIONS, FD_SALARY_CAP, 'FD')
        if len(lineup) == 9:
            actual_score = score_lineup(lineup, actual_stats, 'FD')
            fd_lineups.append({
                'lineup': lineup,
                'salary': salary,
                'actual_score': actual_score,
                'strategy': f'Greedy {i+1}'
            })
        if all_players:
            all_players.pop(0)
    
    # Print top actual performers for verification
    top_performers = sorted(actual_stats, key=lambda x: calculate_dk_score(x), reverse=True)[:5]
    print(f"  Top 5 DK performers:")
    for player in top_performers:
        name = f"{player.get('firstName', '')} {player.get('familyName', '')}"
        dk_score = calculate_dk_score(player)
        print(f"    {name}: {dk_score:.1f} DK points")
    
    # Check for ITM lineups
    dk_itm = [lu for lu in dk_lineups if lu['actual_score'] >= 280]
    fd_itm = [lu for lu in fd_lineups if lu['actual_score'] >= 300]
    
    print(f"  DK lineups: {len(dk_lineups)} built, {len(dk_itm)} ITM")
    print(f"  FD lineups: {len(fd_lineups)} built, {len(fd_itm)} ITM")
    
    best_dk = max(dk_lineups, key=lambda x: x['actual_score'])['actual_score'] if dk_lineups else 0
    best_fd = max(fd_lineups, key=lambda x: x['actual_score'])['actual_score'] if fd_lineups else 0
    
    print(f"  Best scores: DK {best_dk:.1f}, FD {best_fd:.1f}")
    
    return {
        'date': date_str,
        'dk_lineups': dk_lineups,
        'fd_lineups': fd_lineups,
        'dk_itm_count': len(dk_itm),
        'fd_itm_count': len(fd_itm),
        'best_dk': best_dk,
        'best_fd': best_fd
    }

def main():
    """Run the simple DFS backtest"""
    print("=== Simple DFS Backtest ===")
    print(f"Testing {len(TEST_DATES)} dates: {TEST_DATES[0]} to {TEST_DATES[-1]}")
    print()
    
    # Load season cache
    season_cache = get_player_season_cache()
    if not season_cache:
        print("Failed to load season data. Exiting.")
        return
    
    results = []
    
    # Test each date
    for date_str in TEST_DATES:
        result = backtest_date(date_str, season_cache)
        if result:
            results.append(result)
    
    # Calculate summary stats
    if results:
        dk_nights_tested = len(results)
        dk_itm_nights = sum(1 for r in results if r['dk_itm_count'] > 0)
        dk_itm_rate = dk_itm_nights / dk_nights_tested if dk_nights_tested > 0 else 0
        dk_avg_best = sum(r['best_dk'] for r in results) / len(results)
        dk_best_single = max(r['best_dk'] for r in results)
        
        fd_nights_tested = len(results)
        fd_itm_nights = sum(1 for r in results if r['fd_itm_count'] > 0)
        fd_itm_rate = fd_itm_nights / fd_nights_tested if fd_nights_tested > 0 else 0
        fd_avg_best = sum(r['best_fd'] for r in results) / len(results)
        fd_best_single = max(r['best_fd'] for r in results)
        
        summary = {
            'draftkings': {
                'nights_tested': dk_nights_tested,
                'itm_nights': dk_itm_nights,
                'itm_rate': f"{dk_itm_rate*100:.1f}%",
                'avg_best_score': f"{dk_avg_best:.1f}",
                'best_single_score': f"{dk_best_single:.1f}",
                'itm_threshold': '280+'
            },
            'fanduel': {
                'nights_tested': fd_nights_tested,
                'itm_nights': fd_itm_nights,
                'itm_rate': f"{fd_itm_rate*100:.1f}%",
                'avg_best_score': f"{fd_avg_best:.1f}",
                'best_single_score': f"{fd_best_single:.1f}",
                'itm_threshold': '300+'
            },
            'detailed_results': results
        }
        
        # Save results
        output_file = 'dfs_backtest_results_v3.json'
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n=== FINAL RESULTS ===")
        print(f"DraftKings: {dk_itm_nights}/{dk_nights_tested} nights ITM ({dk_itm_rate*100:.1f}%)")
        print(f"  Average best score: {dk_avg_best:.1f}")
        print(f"  Best single score: {dk_best_single:.1f}")
        print(f"FanDuel: {fd_itm_nights}/{fd_nights_tested} nights ITM ({fd_itm_rate*100:.1f}%)")
        print(f"  Average best score: {fd_avg_best:.1f}")
        print(f"  Best single score: {fd_best_single:.1f}")
        print(f"\nResults saved to {output_file}")
    
    else:
        print("No successful backtests completed.")

if __name__ == "__main__":
    main()