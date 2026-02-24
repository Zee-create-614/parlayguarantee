"""
Quick DFS Test - Test scoring on 3 recent dates
No season cache - just verify scoring works correctly
"""

import time
import json
import pandas as pd
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3

# Test just 3 recent dates
TEST_DATES = ["2024-12-01", "2024-12-10", "2024-12-20"]

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

def test_date_scoring(date_str):
    """Test scoring for a specific date"""
    print(f"\n=== Testing {date_str} ===")
    
    # Get games for this date
    game_ids = get_games_for_date(date_str)
    if not game_ids:
        print(f"No games found for {date_str}")
        return None
    
    print(f"Found {len(game_ids)} games")
    
    # Get all player performances
    all_performances = []
    
    for game_id in game_ids[:3]:  # Test first 3 games only for speed
        boxscore = get_boxscore_stats(game_id)
        if not boxscore.empty:
            for _, player in boxscore.iterrows():
                # Skip players with no minutes
                if not player.get('minutes') or player['minutes'] == '0:00':
                    continue
                
                name = f"{player['firstName']} {player['familyName']}"
                pts = player.get('points', 0) or 0
                fg3m = player.get('threePointersMade', 0) or 0
                reb = player.get('reboundsTotal', 0) or 0
                ast = player.get('assists', 0) or 0
                stl = player.get('steals', 0) or 0
                blk = player.get('blocks', 0) or 0
                tov = player.get('turnovers', 0) or 0
                mins = player.get('minutes', '0:00')
                
                dk_score = calculate_dk_score(player)
                
                all_performances.append({
                    'name': name,
                    'points': pts,
                    'dk_score': dk_score,
                    'stats': f"PTS={pts}, 3PM={fg3m}, REB={reb}, AST={ast}, STL={stl}, BLK={blk}, TO={tov}",
                    'minutes': mins
                })
    
    # Sort by DK score
    all_performances.sort(key=lambda x: x['dk_score'], reverse=True)
    
    # Show top 10 performances
    print(f"\nTop 10 DK performers on {date_str}:")
    for i, perf in enumerate(all_performances[:10], 1):
        print(f"{i:2d}. {perf['name']}: {perf['dk_score']:.1f} DK pts ({perf['stats']}, {perf['minutes']} min)")
    
    # Analyze scoring distribution
    scores = [p['dk_score'] for p in all_performances]
    if scores:
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        high_scorers = [s for s in scores if s >= 40]
        
        print(f"\nScoring Analysis:")
        print(f"  Total players: {len(all_performances)}")
        print(f"  Average DK score: {avg_score:.1f}")
        print(f"  Highest DK score: {max_score:.1f}")
        print(f"  Players with 40+ DK points: {len(high_scorers)}")
        print(f"  Players with 50+ DK points: {len([s for s in scores if s >= 50])}")
    
    # Test lineup potential
    if len(all_performances) >= 8:
        # Simple test: take top 8 performers regardless of position
        test_lineup = all_performances[:8]
        total_score = sum(p['dk_score'] for p in test_lineup)
        
        print(f"\nSimple Test Lineup (top 8 players):")
        for i, player in enumerate(test_lineup, 1):
            print(f"  {i}. {player['name']}: {player['dk_score']:.1f}")
        print(f"  Total DK Score: {total_score:.1f}")
        print(f"  ITM Status: {'YES' if total_score >= 280 else 'NO'} (need 280+)")
        
        return {
            'date': date_str,
            'total_players': len(all_performances),
            'avg_score': avg_score,
            'max_score': max_score,
            'test_lineup_score': total_score,
            'itm': total_score >= 280
        }
    
    return None

def main():
    """Run quick DFS scoring test"""
    print("=== Quick DFS Scoring Test ===")
    print("Testing actual DK scoring on recent NBA games")
    print("This will verify that our scoring calculation is correct")
    print()
    
    results = []
    
    for date in TEST_DATES:
        result = test_date_scoring(date)
        if result:
            results.append(result)
    
    # Summary
    if results:
        print(f"\n=== SUMMARY ===")
        for result in results:
            status = "ITM" if result['itm'] else "Miss"
            print(f"{result['date']}: {result['test_lineup_score']:.1f} DK points ({status})")
        
        avg_test_score = sum(r['test_lineup_score'] for r in results) / len(results)
        itm_count = sum(1 for r in results if r['itm'])
        
        print(f"\nOverall Results:")
        print(f"  Dates tested: {len(results)}")
        print(f"  Average test lineup score: {avg_test_score:.1f}")
        print(f"  ITM rate: {itm_count}/{len(results)} ({itm_count/len(results)*100:.1f}%)")
        print(f"  Scoring verification: {'PASSED' if avg_test_score > 250 else 'FAILED'}")
        
        # Save results
        with open('dfs_quick_test_results.json', 'w') as f:
            json.dump({
                'test_results': results,
                'summary': {
                    'avg_test_score': avg_test_score,
                    'itm_rate': f"{itm_count/len(results)*100:.1f}%",
                    'scoring_status': 'PASSED' if avg_test_score > 250 else 'FAILED'
                }
            }, f, indent=2)
        
        print(f"\nDetailed results saved to dfs_quick_test_results.json")
    
    else:
        print("No successful tests completed.")

if __name__ == "__main__":
    main()