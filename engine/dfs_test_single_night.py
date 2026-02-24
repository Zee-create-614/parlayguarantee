"""
DFS Single Night Test Script - Tests lineup generation for Dec 15, 2024
Prints debug info at each step to isolate where failures occur
"""

import logging
from datetime import datetime
from typing import List
from dfs_engine import DFSEngine, Player

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def debug_single_night_test():
    """Test lineup generation for December 15, 2024 with full debugging"""
    print("DFS SINGLE NIGHT TEST - December 15, 2024")
    print("=" * 60)
    
    # Test date
    test_date = "2024-12-15"
    print(f"Test date: {test_date}")
    
    try:
        # Initialize engine
        print("\nStep 1: Initializing DFS Engine...")
        engine = DFSEngine()
        print("Engine initialized successfully")
        
        # Get player pool
        print(f"\nStep 2: Building player pool for {test_date}...")
        print("This may take a few minutes due to NBA API rate limiting...")
        
        players = engine.get_player_pool(test_date)
        
        print(f"Player pool built: {len(players)} players")
        
        if not players:
            print("ERROR: No players in pool - cannot test lineup generation")
            return False
        
        # Analyze player pool
        print(f"\nStep 3: Analyzing player pool...")
        
        position_counts = {'PG': 0, 'SG': 0, 'SF': 0, 'PF': 0, 'C': 0}
        dk_salaries = []
        fd_salaries = []
        dk_projections = []
        fd_projections = []
        
        for player in players:
            position_counts[player.position] += 1
            dk_salaries.append(player.salary_dk)
            fd_salaries.append(player.salary_fd)
            dk_projections.append(player.projected_dk)
            fd_projections.append(player.projected_fd)
        
        print("Position distribution:")
        for pos, count in position_counts.items():
            print(f"  {pos}: {count} players")
        
        print(f"\nSalary ranges:")
        print(f"  DK: ${min(dk_salaries):,} - ${max(dk_salaries):,}")
        print(f"  FD: ${min(fd_salaries):,} - ${max(fd_salaries):,}")
        
        print(f"\nProjection ranges:")
        print(f"  DK: {min(dk_projections):.1f} - {max(dk_projections):.1f} pts")
        print(f"  FD: {min(fd_projections):.1f} - {max(fd_projections):.1f} pts")
        
        # Test DraftKings lineup generation
        print(f"\nStep 4: Testing DraftKings lineup generation...")
        dk_lineup = engine.generate_lineup_greedy(players, 'draftkings')
        
        if dk_lineup:
            print("SUCCESS: Generated DraftKings lineup")
            print(f"  Projected points: {dk_lineup.projected_points:.1f}")
            print(f"  Total salary: ${dk_lineup.total_salary:,} / $50,000")
            print(f"  Strategy: {dk_lineup.strategy}")
            print("  Players:")
            
            for player in dk_lineup.players:
                print(f"    {player.position:4} {player.name[:30]:30} ${player.salary_dk:,} ({player.projected_dk:.1f} pts)")
            
            dk_success = True
        else:
            print("FAILED: Could not generate DraftKings lineup")
            dk_success = False
        
        # Test FanDuel lineup generation
        print(f"\nStep 5: Testing FanDuel lineup generation...")
        fd_lineup = engine.generate_lineup_greedy(players, 'fanduel')
        
        if fd_lineup:
            print("SUCCESS: Generated FanDuel lineup")
            print(f"  Projected points: {fd_lineup.projected_points:.1f}")
            print(f"  Total salary: ${fd_lineup.total_salary:,} / $60,000")
            print(f"  Strategy: {fd_lineup.strategy}")
            print("  Players:")
            
            for player in fd_lineup.players:
                print(f"    {player.position:4} {player.name[:30]:30} ${player.salary_fd:,} ({player.projected_fd:.1f} pts)")
            
            fd_success = True
        else:
            print("FAILED: Could not generate FanDuel lineup")
            fd_success = False
        
        # Test full lineup generation (5 lineups each)
        print(f"\nStep 6: Testing full lineup generation (5 lineups each platform)...")
        lineups_result = engine.generate_lineups(test_date)
        
        print("Full lineup generation results:")
        for platform, platform_lineups in lineups_result.items():
            print(f"\n{platform.upper()}:")
            print(f"  Generated: {len(platform_lineups)} lineups")
            
            if platform_lineups:
                for i, lineup in enumerate(platform_lineups, 1):
                    print(f"    {i}. {lineup.strategy}: {lineup.projected_points:.1f} pts, ${lineup.total_salary:,}")
            else:
                print("    No lineups generated")
        
        # Summary
        print(f"\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        total_dk_lineups = len(lineups_result.get('draftkings', []))
        total_fd_lineups = len(lineups_result.get('fanduel', []))
        
        print(f"DraftKings: {'SUCCESS' if dk_success else 'FAILED'} - {total_dk_lineups} lineups")
        print(f"FanDuel: {'SUCCESS' if fd_success else 'FAILED'} - {total_fd_lineups} lineups")
        print(f"Total lineups: {total_dk_lineups + total_fd_lineups}")
        
        if dk_success and fd_success and total_dk_lineups > 0 and total_fd_lineups > 0:
            print("OVERALL RESULT: SUCCESS - Lineup generation working!")
            return True
        else:
            print("OVERALL RESULT: FAILED - Issues with lineup generation")
            return False
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """Run the single night test"""
    success = debug_single_night_test()
    
    if success:
        print("\nSingle night test PASSED")
        print("The DFS engine is working correctly!")
    else:
        print("\nSingle night test FAILED")
        print("There are issues with the DFS engine that need to be fixed")

if __name__ == "__main__":
    main()