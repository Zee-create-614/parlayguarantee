"""
DFS Simple Test Script - Debug lineup generation step by step
Tests lineup generation for ONE night (Dec 15, 2024) with detailed logging
"""

import sys
import logging
from datetime import datetime
from typing import Dict, List

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dfs_simple_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import our DFS engine
from dfs_engine import DFSEngine, Player

def main():
    """Test DFS engine for single night with detailed debugging"""
    print("DFS SINGLE NIGHT TEST - Dec 15, 2024")
    print("="*80)
    
    try:
        # Initialize engine
        engine = DFSEngine()
        
        # Test date
        test_date = "2024-12-15"
        print(f"Test date: {test_date}")
        
        # Get player pool
        print(f"\nBuilding player pool...")
        players = engine.get_player_pool(test_date)
        
        print(f"Total players in pool: {len(players)}")
        
        if not players:
            print("ERROR: No players available")
            return
        
        # Show position breakdown
        position_counts = {}
        for player in players:
            pos = player.position
            if pos not in position_counts:
                position_counts[pos] = 0
            position_counts[pos] += 1
        
        print("\nPosition breakdown:")
        for pos, count in position_counts.items():
            print(f"  {pos}: {count} players")
        
        # Test DraftKings lineup generation
        print(f"\nTesting DraftKings lineup generation:")
        dk_lineup = engine.generate_lineup_greedy(players, 'draftkings')
        
        if dk_lineup:
            print(f"SUCCESS: Generated DK lineup")
            print(f"  Projected points: {dk_lineup.projected_points:.1f}")
            print(f"  Total salary: ${dk_lineup.total_salary:,}")
            print(f"  Strategy: {dk_lineup.strategy}")
            print("  Players:")
            for player in dk_lineup.players:
                print(f"    {player.position} {player.name[:25]:25} ${player.salary_dk:,} ({player.projected_dk:.1f} pts)")
        else:
            print("FAILED: Could not generate DK lineup")
        
        # Test FanDuel lineup generation
        print(f"\nTesting FanDuel lineup generation:")
        fd_lineup = engine.generate_lineup_greedy(players, 'fanduel')
        
        if fd_lineup:
            print(f"SUCCESS: Generated FD lineup")
            print(f"  Projected points: {fd_lineup.projected_points:.1f}")
            print(f"  Total salary: ${fd_lineup.total_salary:,}")
            print(f"  Strategy: {fd_lineup.strategy}")
            print("  Players:")
            for player in fd_lineup.players:
                print(f"    {player.position} {player.name[:25]:25} ${player.salary_fd:,} ({player.projected_fd:.1f} pts)")
        else:
            print("FAILED: Could not generate FD lineup")
        
        # Test all 5 lineups like backtest
        print(f"\nTesting full lineup generation (like backtest):")
        lineups = engine.generate_lineups(test_date)
        
        for platform, platform_lineups in lineups.items():
            print(f"\n{platform.upper()} Results:")
            print(f"  Generated {len(platform_lineups)} lineups")
            
            for i, lineup in enumerate(platform_lineups, 1):
                print(f"    Lineup {i}: {lineup.projected_points:.1f} pts, ${lineup.total_salary:,} ({lineup.strategy})")
        
        print("\nTest completed!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()