"""
Detailed debug of lineup generation process
"""

import json
from datetime import datetime
from dfs_backtest_v2 import DFSBacktesterV2
from dfs_engine import DFSEngine

def debug_detailed_lineup():
    print("DETAILED LINEUP GENERATION DEBUG...")
    
    # Load backtester and engine
    backtester = DFSBacktesterV2()
    engine = DFSEngine()
    
    # Get players for test date
    test_date = '2024-12-01'
    players = backtester.create_player_pool_from_cache(test_date)
    
    print(f"\nTesting with {len(players)} players on {test_date}")
    
    if not players:
        print("No players available!")
        return
    
    # Test DraftKings lineup generation step by step
    print("\n=== DRAFTKINGS LINEUP GENERATION ===")
    
    config = engine.PLATFORMS['draftkings']
    positions = config['positions']
    salary_cap = config['salary_cap']
    
    print(f"Required positions: {positions}")
    print(f"Salary cap: ${salary_cap:,}")
    
    # Sort players by projected points (descending)
    sorted_players = sorted(players, key=lambda p: p.projected_dk, reverse=True)
    print(f"Top 5 players by projection:")
    for i, p in enumerate(sorted_players[:5]):
        try:
            name = p.name.encode('ascii', 'ignore').decode('ascii')
        except:
            name = "Player_" + p.id
        print(f"  {i+1}. {name} ({p.position}): {p.projected_dk:.2f} pts, ${p.salary_dk:,}")
    
    # Position eligibility mapping
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
    
    # Manual lineup construction
    lineup_players = []
    total_salary = 0
    
    print(f"\nStarting lineup construction...")
    
    for i, pos_needed in enumerate(positions):
        print(f"\n--- Position {i+1}: {pos_needed} ---")
        
        # Find eligible players
        eligible_positions = position_groups.get(pos_needed, [pos_needed])
        print(f"Eligible positions: {eligible_positions}")
        
        eligible_players = [
            p for p in sorted_players 
            if p not in lineup_players and 
            p.position in eligible_positions
        ]
        
        print(f"Eligible players: {len(eligible_players)}")
        if eligible_players:
            print(f"Top 3 eligible players:")
            for j, p in enumerate(eligible_players[:3]):
                try:
                    name = p.name.encode('ascii', 'ignore').decode('ascii')
                except:
                    name = "Player_" + p.id
                can_afford = (total_salary + p.salary_dk <= salary_cap)
                print(f"  {j+1}. {name} ({p.position}): {p.projected_dk:.2f} pts, ${p.salary_dk:,} {'YES' if can_afford else 'NO - Too expensive'}")
        
        # Find best affordable player
        selected_player = None
        for player in eligible_players:
            if total_salary + player.salary_dk <= salary_cap:
                selected_player = player
                break
        
        if selected_player:
            lineup_players.append(selected_player)
            total_salary += selected_player.salary_dk
            try:
                name = selected_player.name.encode('ascii', 'ignore').decode('ascii')
            except:
                name = "Player_" + selected_player.id
            print(f"SELECTED: {name} ({selected_player.position})")
            print(f"Running total: {len(lineup_players)} players, ${total_salary:,}")
        else:
            print(f"NO AFFORDABLE PLAYER FOUND!")
            print(f"Current salary: ${total_salary:,}, Cap: ${salary_cap:,}")
            if eligible_players:
                cheapest = min(eligible_players, key=lambda p: p.salary_dk)
                try:
                    name = cheapest.name.encode('ascii', 'ignore').decode('ascii')
                except:
                    name = "Player_" + cheapest.id
                print(f"Cheapest eligible: {name} (${cheapest.salary_dk:,})")
                print(f"Would need: ${total_salary + cheapest.salary_dk:,}")
            break
    
    print(f"\nFINAL RESULT:")
    if len(lineup_players) == len(positions):
        total_proj = sum(p.projected_dk for p in lineup_players)
        print(f"SUCCESS: Complete lineup with {len(lineup_players)} players")
        print(f"Total salary: ${total_salary:,}")
        print(f"Total projection: {total_proj:.2f} points")
        print(f"Lineup:")
        for i, p in enumerate(lineup_players):
            try:
                name = p.name.encode('ascii', 'ignore').decode('ascii')
            except:
                name = "Player_" + p.id
            print(f"  {positions[i]}: {name} ({p.position}) - {p.projected_dk:.2f} pts, ${p.salary_dk:,}")
    else:
        print(f"FAILED: Only filled {len(lineup_players)}/{len(positions)} positions")

if __name__ == "__main__":
    debug_detailed_lineup()