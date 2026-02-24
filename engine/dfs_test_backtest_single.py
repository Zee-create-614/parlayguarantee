"""
Test backtest for a single night using the fixed engine
"""

import logging
from dfs_engine import DFSEngine
from dfs_test_mock import create_mock_players

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_backtest_single_night():
    """Test the backtest process for one night with mock data"""
    print("DFS BACKTEST SINGLE NIGHT TEST")
    print("="*50)
    
    # Create engine and mock players
    engine = DFSEngine()
    players = create_mock_players()
    
    print(f"Created {len(players)} mock players")
    
    # Test generate_lineups method (like backtest uses)
    target_date = "2024-12-15"
    
    # Override the get_player_pool method to use our mock data
    original_method = engine.get_player_pool
    engine.get_player_pool = lambda date: players
    
    try:
        # Generate lineups like the backtest does
        lineups = engine.generate_lineups(target_date)
        
        print("\nLINEUP GENERATION RESULTS:")
        print("-" * 50)
        
        for platform, platform_lineups in lineups.items():
            print(f"\n{platform.upper()} LINEUPS:")
            print(f"  Generated: {len(platform_lineups)} lineups")
            
            if platform_lineups:
                print("  SUCCESS! Lineup details:")
                for i, lineup in enumerate(platform_lineups, 1):
                    print(f"    {i}. {lineup.strategy}: {lineup.projected_points:.1f} pts, ${lineup.total_salary:,}")
            else:
                print("  FAILED: No lineups generated")
        
        # Calculate summary like backtest
        total_dk_lineups = len(lineups.get('draftkings', []))
        total_fd_lineups = len(lineups.get('fanduel', []))
        
        print(f"\nSUMMARY:")
        print(f"  DraftKings: {total_dk_lineups} lineups")
        print(f"  FanDuel: {total_fd_lineups} lineups") 
        print(f"  Total: {total_dk_lineups + total_fd_lineups} lineups")
        
        if total_dk_lineups > 0 and total_fd_lineups > 0:
            print("  STATUS: SUCCESS - Both platforms generating lineups!")
            return True
        else:
            print("  STATUS: FAILED - Not all platforms working")
            return False
            
    finally:
        # Restore original method
        engine.get_player_pool = original_method

if __name__ == "__main__":
    success = test_backtest_single_night()
    if success:
        print("\nSingle night backtest test PASSED")
    else:
        print("\nSingle night backtest test FAILED")