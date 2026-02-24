"""
Test the actual engine methods directly
"""

import logging
logging.basicConfig(level=logging.DEBUG)

from dfs_engine import DFSEngine
from dfs_test_mock import create_mock_players

def test_engine_methods():
    print("Testing actual DFS engine methods...")
    
    # Create mock players
    players = create_mock_players()
    engine = DFSEngine()
    
    print(f"Created {len(players)} mock players")
    
    # Show salary distribution
    dk_salaries = [p.salary_dk for p in players]
    fd_salaries = [p.salary_fd for p in players]
    
    print(f"\nSalary ranges:")
    print(f"  DK: ${min(dk_salaries):,} - ${max(dk_salaries):,}, avg: ${sum(dk_salaries) // len(dk_salaries):,}")
    print(f"  FD: ${min(fd_salaries):,} - ${max(fd_salaries):,}, avg: ${sum(fd_salaries) // len(fd_salaries):,}")
    
    # Test DraftKings
    print("\n" + "="*50)
    print("TESTING DRAFTKINGS")
    print("="*50)
    
    dk_lineup = engine.generate_lineup_greedy(players, 'draftkings')
    
    if dk_lineup:
        print("SUCCESS! Generated DraftKings lineup:")
        print(f"  Projected points: {dk_lineup.projected_points:.1f}")
        print(f"  Total salary: ${dk_lineup.total_salary:,} / $50,000")
        print(f"  Strategy: {dk_lineup.strategy}")
        print("  Players:")
        for player in dk_lineup.players:
            print(f"    {player.position:4} {player.name[:25]:25} ${player.salary_dk:,} ({player.projected_dk:.1f} pts)")
    else:
        print("FAILED to generate DraftKings lineup")
    
    # Test FanDuel  
    print("\n" + "="*50)
    print("TESTING FANDUEL")
    print("="*50)
    
    fd_lineup = engine.generate_lineup_greedy(players, 'fanduel')
    
    if fd_lineup:
        print("SUCCESS! Generated FanDuel lineup:")
        print(f"  Projected points: {fd_lineup.projected_points:.1f}")
        print(f"  Total salary: ${fd_lineup.total_salary:,} / $60,000")
        print(f"  Strategy: {fd_lineup.strategy}")
        print("  Players:")
        for player in fd_lineup.players:
            print(f"    {player.position:4} {player.name[:25]:25} ${player.salary_fd:,} ({player.projected_fd:.1f} pts)")
    else:
        print("FAILED to generate FanDuel lineup")
    
    # Test value strategy
    print("\n" + "="*50)
    print("TESTING VALUE STRATEGIES")
    print("="*50)
    
    dk_value = engine.generate_lineup_value(players, 'draftkings')
    fd_value = engine.generate_lineup_value(players, 'fanduel')
    
    print(f"DK Value Strategy: {'SUCCESS' if dk_value else 'FAILED'}")
    if dk_value:
        print(f"  {dk_value.projected_points:.1f} pts, ${dk_value.total_salary:,}")
        
    print(f"FD Value Strategy: {'SUCCESS' if fd_value else 'FAILED'}")
    if fd_value:
        print(f"  {fd_value.projected_points:.1f} pts, ${fd_value.total_salary:,}")

if __name__ == "__main__":
    test_engine_methods()