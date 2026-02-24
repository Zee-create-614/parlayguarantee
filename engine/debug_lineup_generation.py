"""
Debug script to identify lineup generation issues
"""

import json
from datetime import datetime
from dfs_backtest_v2 import DFSBacktesterV2
from dfs_engine import DFSEngine

def debug_lineup_generation():
    print("DEBUGGING LINEUP GENERATION...")
    
    # Load cache
    with open('dfs_cache.json', 'r') as f:
        cache = json.load(f)
    
    # Initialize backtester
    backtester = DFSBacktesterV2()
    engine = DFSEngine()
    
    # Test with first available date
    test_date = '2024-12-01'
    print(f"\nTesting date: {test_date}")
    
    # Step 1: Check projections
    print("\n1. Checking projections...")
    projections = backtester.get_player_projections_from_cache(test_date)
    print(f"   Projections generated: {len(projections)}")
    
    if projections:
        sample_projection = list(projections.items())[0]
        print(f"   Sample projection: Player {sample_projection[0]} -> DK: {sample_projection[1][0]:.2f}, FD: {sample_projection[1][1]:.2f}")
    
    # Step 2: Check player pool creation
    print("\n2. Checking player pool...")
    players = backtester.create_player_pool_from_cache(test_date)
    print(f"   Players in pool: {len(players)}")
    
    if players:
        sample_player = players[0]
        print(f"   Sample player: {sample_player.name} ({sample_player.position})")
        print(f"      DK: ${sample_player.salary_dk}, {sample_player.projected_dk:.2f} pts")
        print(f"      FD: ${sample_player.salary_fd}, {sample_player.projected_fd:.2f} pts")
    
    # Step 3: Test lineup generation
    print("\n3. Testing lineup generation...")
    
    if not players:
        print("   ERROR: No players available for lineup generation")
        return
    
    # Test DraftKings lineup generation
    print("\n   Testing DraftKings lineup generation...")
    try:
        dk_lineup = engine.generate_lineup_greedy(players, 'draftkings')
        if dk_lineup:
            print(f"   SUCCESS: DK lineup generated: {len(dk_lineup.players)} players, ${dk_lineup.total_salary:,}, {dk_lineup.projected_points:.2f} pts")
        else:
            print("   ERROR: DK lineup generation failed")
            
            # Debug lineup generation process
            print("\n   Debugging DK lineup generation...")
            config = engine.PLATFORMS['draftkings']
            positions = config['positions']
            salary_cap = config['salary_cap']
            
            print(f"      Required positions: {positions}")
            print(f"      Salary cap: ${salary_cap:,}")
            
            # Check position availability
            position_counts = {}
            for player in players:
                pos = player.position
                if pos not in position_counts:
                    position_counts[pos] = 0
                position_counts[pos] += 1
            
            print(f"      Position availability: {position_counts}")
            
            # Check salary ranges
            min_salary = min(p.salary_dk for p in players) if players else 0
            max_salary = max(p.salary_dk for p in players) if players else 0
            print(f"      Salary range: ${min_salary:,} - ${max_salary:,}")
            
    except Exception as e:
        print(f"   ERROR: DK lineup generation error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test FanDuel lineup generation  
    print("\n   Testing FanDuel lineup generation...")
    try:
        fd_lineup = engine.generate_lineup_greedy(players, 'fanduel')
        if fd_lineup:
            print(f"   SUCCESS: FD lineup generated: {len(fd_lineup.players)} players, ${fd_lineup.total_salary:,}, {fd_lineup.projected_points:.2f} pts")
        else:
            print("   ERROR: FD lineup generation failed")
    except Exception as e:
        print(f"   ERROR: FD lineup generation error: {e}")

if __name__ == "__main__":
    debug_lineup_generation()