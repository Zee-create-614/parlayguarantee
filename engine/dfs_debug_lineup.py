"""
Debug the _fill_lineup method to see exactly where it fails
"""

from typing import List, Optional
from dfs_engine import DFSEngine, Player, Lineup

def debug_fill_lineup(sorted_players: List[Player], positions: List[str], 
                     salary_cap: int, platform: str, strategy: str) -> Optional[Lineup]:
    """Debug version of _fill_lineup with detailed logging"""
    print(f"\nDEBUG: _fill_lineup for {platform}")
    print(f"  Required positions: {positions}")
    print(f"  Salary cap: ${salary_cap:,}")
    print(f"  Available players: {len(sorted_players)}")
    
    lineup_players = []
    used_positions = []
    total_salary = 0
    
    # Track position eligibility
    position_groups = {
        'PG': ['PG'],
        'SG': ['SG'], 
        'SF': ['SF'],
        'PF': ['PF'],
        'C': ['C'],
        'G': ['PG', 'SG'],  # DK only
        'F': ['SF', 'PF'],  # DK only  
        'UTIL': ['PG', 'SG', 'SF', 'PF', 'C']  # DK only
    }
    
    print(f"  Position groups: {position_groups}")
    
    for i, pos_needed in enumerate(positions):
        print(f"\n  Step {i+1}: Looking for {pos_needed}")
        
        eligible_players = [
            p for p in sorted_players 
            if p not in lineup_players and 
            p.position in position_groups.get(pos_needed, [pos_needed])
        ]
        
        print(f"    Eligible players: {len(eligible_players)}")
        
        if eligible_players:
            print(f"    Top 3 eligible:")
            for j, player in enumerate(eligible_players[:3], 1):
                player_salary = player.salary_dk if platform == 'draftkings' else player.salary_fd
                proj = player.projected_dk if platform == 'draftkings' else player.projected_fd
                remaining_cap = salary_cap - total_salary
                affordable = "YES" if player_salary <= remaining_cap else "NO"
                print(f"      {j}. {player.name[:20]:20} {player.position} ${player_salary:,} ({proj:.1f}pts) Affordable: {affordable}")
        
        # Find best affordable player for this position
        selected = None
        for player in eligible_players:
            player_salary = player.salary_dk if platform == 'draftkings' else player.salary_fd
            
            if total_salary + player_salary <= salary_cap:
                selected = player
                break
        
        if selected:
            player_salary = selected.salary_dk if platform == 'draftkings' else selected.salary_fd
            proj = selected.projected_dk if platform == 'draftkings' else selected.projected_fd
            
            lineup_players.append(selected)
            used_positions.append(pos_needed)
            total_salary += player_salary
            
            print(f"    SELECTED: {selected.name} ${player_salary:,} ({proj:.1f}pts)")
            print(f"    Running total: ${total_salary:,} / ${salary_cap:,}")
        else:
            print(f"    FAILED: No affordable player found for {pos_needed}")
            if eligible_players:
                cheapest = min(eligible_players, key=lambda p: p.salary_dk if platform == 'draftkings' else p.salary_fd)
                cheapest_salary = cheapest.salary_dk if platform == 'draftkings' else cheapest.salary_fd
                print(f"    Cheapest available: {cheapest.name} ${cheapest_salary:,}")
                print(f"    Current salary: ${total_salary:,}, Need: ${cheapest_salary:,}, Cap: ${salary_cap:,}")
            return None  # Can't complete lineup
    
    # Check if we have a complete lineup
    print(f"\n  FINAL CHECK:")
    print(f"    Players selected: {len(lineup_players)} / {len(positions)} required")
    print(f"    Total salary: ${total_salary:,} / ${salary_cap:,}")
    
    if len(lineup_players) != len(positions):
        print(f"    FAILED: Incomplete lineup")
        return None
    
    # Calculate total projected points
    if platform == 'draftkings':
        total_proj = sum(p.projected_dk for p in lineup_players)
    else:
        total_proj = sum(p.projected_fd for p in lineup_players)
    
    print(f"    SUCCESS: Complete lineup with {total_proj:.1f} projected points")
    
    return Lineup(
        platform=platform,
        players=lineup_players,
        total_salary=total_salary,
        projected_points=total_proj,
        strategy=strategy
    )


if __name__ == "__main__":
    # Import mock data
    from dfs_test_mock import create_mock_players
    
    print("DEBUGGING LINEUP GENERATION")
    print("="*50)
    
    players = create_mock_players()
    engine = DFSEngine()
    
    # Test DraftKings
    print("\nTesting DraftKings:")
    dk_config = engine.PLATFORMS['draftkings']
    sorted_players = sorted(players, key=lambda p: p.projected_dk, reverse=True)
    
    lineup = debug_fill_lineup(
        sorted_players, 
        dk_config['positions'], 
        dk_config['salary_cap'], 
        'draftkings', 
        'debug'
    )
    
    # Test FanDuel
    print("\nTesting FanDuel:")
    fd_config = engine.PLATFORMS['fanduel']
    sorted_players = sorted(players, key=lambda p: p.projected_fd, reverse=True)
    
    lineup = debug_fill_lineup(
        sorted_players, 
        fd_config['positions'], 
        fd_config['salary_cap'], 
        'fanduel', 
        'debug'
    )