#!/usr/bin/env python3
"""
Quick test of the DFS backtest script with a single date
"""

import json
import time
from datetime import datetime
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3

print("Testing NBA API and DFS scoring logic...")
print("=" * 50)

def test_api_call():
    """Test basic API connectivity"""
    try:
        print("Testing scoreboardv2 for 2024-12-01...")
        sb = scoreboardv2.ScoreboardV2(game_date='2024-12-01')
        data = sb.get_normalized_dict()
        games = data.get('GameHeader', [])
        print(f"Found {len(games)} games")
        
        if games:
            game_id = games[0]['GAME_ID']
            print(f"Testing boxscoretraditionalv3 for game: {game_id}")
            
            time.sleep(2)  # Rate limiting
            bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
            box_data = bs.get_dict()
            
            # Check structure
            box_score = box_data.get('boxScoreTraditional', {})
            home_team = box_score.get('homeTeam', {})
            away_team = box_score.get('awayTeam', {})
            
            print(f"Home team: {home_team.get('teamName', 'Unknown')}")
            print(f"Away team: {away_team.get('teamName', 'Unknown')}")
            
            # Get a few players
            home_players = home_team.get('players', [])[:3]
            for i, player in enumerate(home_players, 1):
                name = f"{player.get('firstName', '')} {player.get('familyName', '')}".strip()
                stats = player.get('statistics', {})
                
                pts = stats.get('points', 0) or 0
                reb = stats.get('reboundsTotal', 0) or 0
                ast = stats.get('assists', 0) or 0
                
                # Calculate DK score
                tpm = stats.get('threePointersMade', 0) or 0
                stl = stats.get('steals', 0) or 0
                blk = stats.get('blocks', 0) or 0
                to = stats.get('turnovers', 0) or 0
                
                dk_score = (pts + tpm*0.5 + reb*1.25 + ast*1.5 + 
                           stl*2 + blk*2 + to*(-0.5))
                
                # Check for bonuses
                dd_categories = [pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10]
                dd_count = sum(dd_categories)
                
                if dd_count >= 2:
                    dk_score += 1.5  # Double-double bonus
                if dd_count >= 3:
                    dk_score += 3.0  # Triple-double bonus
                
                print(f"Player {i}: {name}")
                print(f"  Stats: {pts}pts, {tpm}x3pm, {reb}reb, {ast}ast, {stl}stl, {blk}blk, {to}to")
                print(f"  DK Score: {dk_score:.1f}")
                print(f"  Position: {player.get('position', 'Unknown')}")
                print()
                
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_api_call()
    print(f"Test {'PASSED' if success else 'FAILED'}")