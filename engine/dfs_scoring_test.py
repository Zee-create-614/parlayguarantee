"""
DFS Scoring Test - Verify scoring with a known game example
This will test the DraftKings scoring calculation on real NBA data
"""

import time
import pandas as pd
from nba_api.stats.endpoints import boxscoretraditionalv3

def calculate_dk_score(player_stats):
    """
    Calculate DraftKings fantasy points using correct column names
    DK formula: PTS×1 + 3PM×0.5 + REB×1.25 + AST×1.5 + STL×2 + BLK×2 + TO×(-0.5) + DD(1.5) + TD(3)
    """
    pts = player_stats.get('points', 0) or 0
    fg3m = player_stats.get('threePointersMade', 0) or 0
    reb = player_stats.get('reboundsTotal', 0) or 0
    ast = player_stats.get('assists', 0) or 0
    stl = player_stats.get('steals', 0) or 0
    blk = player_stats.get('blocks', 0) or 0
    tov = player_stats.get('turnovers', 0) or 0
    
    # Basic scoring
    score = (pts * 1.0 + 
             fg3m * 0.5 + 
             reb * 1.25 + 
             ast * 1.5 + 
             stl * 2.0 + 
             blk * 2.0 + 
             tov * (-0.5))
    
    # Double-double bonus (10+ in at least 2 categories)
    double_stats = [pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10]
    if sum(double_stats) >= 2:
        score += 1.5
        
        # Triple-double bonus (10+ in at least 3 categories)
        if sum(double_stats) >= 3:
            score += 3.0
    
    return score

def test_scoring():
    """Test scoring with game 0022400305 from Dec 1, 2024"""
    print("=== DFS Scoring Test ===")
    print("Testing with game 0022400305 from December 1, 2024")
    print()
    
    try:
        # Get box score for the specific game
        print("Fetching box score...")
        boxscore = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id='0022400305')
        time.sleep(2)  # Rate limit
        
        df = boxscore.get_data_frames()[0]  # Player stats
        
        print(f"Found {len(df)} players in the game")
        print()
        print("Column names available:")
        for i, col in enumerate(df.columns):
            print(f"  {i+1:2d}. {col}")
        print()
        
        # Show first player's complete data
        if len(df) > 0:
            first_player = df.iloc[0]
            print("First player's complete data:")
            for col, val in first_player.items():
                print(f"  {col}: {val}")
            print()
        
        # Find high-scoring players to test
        print("Top performers by points scored:")
        top_players = df.nlargest(5, 'points')
        
        for idx, player in top_players.iterrows():
            name = f"{player['firstName']} {player['familyName']}"
            pts = player.get('points', 0) or 0
            fg3m = player.get('threePointersMade', 0) or 0
            reb = player.get('reboundsTotal', 0) or 0
            ast = player.get('assists', 0) or 0
            stl = player.get('steals', 0) or 0
            blk = player.get('blocks', 0) or 0
            tov = player.get('turnovers', 0) or 0
            mins = player.get('minutes', 0) or 0
            
            # Calculate DK score
            dk_score = calculate_dk_score(player)
            
            print(f"{name}: PTS={pts}, 3PM={fg3m}, REB={reb}, AST={ast}, STL={stl}, BLK={blk}, TO={tov} (Min={mins}) -> DK Score = {dk_score:.1f}")
        
        print()
        print("=== Score Analysis ===")
        print("Expected: Star players (30+ pts) should score 40-60 DK points")
        print("Expected: Role players (10-20 pts) should score 20-35 DK points")
        print("Expected: Bench players (<10 pts) should score 5-20 DK points")
        
        # Calculate average scores
        all_scores = [calculate_dk_score(df.iloc[i]) for i in range(len(df))]
        valid_scores = [score for score in all_scores if score > 0]
        
        if valid_scores:
            print(f"Average DK score across all players: {sum(valid_scores)/len(valid_scores):.1f}")
            print(f"Highest individual DK score: {max(valid_scores):.1f}")
            print(f"Players with 35+ DK points: {sum(1 for score in valid_scores if score >= 35)}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Check NBA API connection")
        print("2. Verify game ID is correct")
        print("3. Check column name mapping")
        return False

if __name__ == "__main__":
    test_scoring()