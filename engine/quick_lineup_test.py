"""
Quick test to generate a single lineup with our fixes
"""

from dfs_backtest_v2 import DFSBacktesterV2  
from dfs_engine import DFSEngine
from better_positions import assign_realistic_position

def quick_lineup_test():
    print("QUICK LINEUP TEST...")
    
    # Initialize
    backtester = DFSBacktesterV2()
    engine = DFSEngine()
    
    # Test date
    test_date = '2024-12-01'
    
    # Get fresh player pool (this should use our new salary estimation)
    print(f"Getting fresh player pool for {test_date}...")
    
    # First get projections 
    projections = backtester.get_player_projections_from_cache(test_date)
    print(f"Projections for {len(projections)} players")
    
    # Get actual players who played
    actual_stats = backtester.get_actual_stats_from_cache(test_date)
    print(f"Actual stats for {len(actual_stats)} players")
    
    # Get games for this date
    games = backtester.cache['game_schedules'].get(test_date, [])
    print(f"Games found: {len(games)}")
    
    # Manually create players with correct salary estimation
    players = []
    
    for game in games:
        game_id = game['game_id']
        box_score = backtester.cache['box_scores'].get(game_id, {})
        
        for player_data in box_score.get('players', []):  # Use all players per game
            player_id = str(player_data['PLAYER_ID'])
            
            if player_id in projections:
                dk_proj, fd_proj = projections[player_id]
                
                if dk_proj > 0 and fd_proj > 0:
                    # Use our improved position assignment
                    position = assign_realistic_position(player_data['PLAYER_NAME'])
                    
                    # Use our improved salary estimation
                    dk_salary = engine.estimate_salary(dk_proj, fd_proj, 'draftkings')
                    fd_salary = engine.estimate_salary(dk_proj, fd_proj, 'fanduel')
                    
                    from dfs_engine import Player
                    player = Player(
                        id=player_id,
                        name=player_data['PLAYER_NAME'],
                        position=position,
                        team='UNK',
                        salary_dk=dk_salary,
                        salary_fd=fd_salary,
                        projected_dk=dk_proj,
                        projected_fd=fd_proj,
                        value_dk=dk_proj / (dk_salary / 1000) if dk_salary > 0 else 0,
                        value_fd=fd_proj / (fd_salary / 1000) if fd_salary > 0 else 0,
                        recent_games=[]
                    )
                    
                    players.append(player)
                    
                    if len(players) >= 200:  # Test with more players
                        break
        
        if len(players) >= 200:
            break
    
    print(f"Created {len(players)} players for testing")
    
    # Check position distribution
    position_counts = {}
    for player in players:
        pos = player.position
        position_counts[pos] = position_counts.get(pos, 0) + 1
    
    print(f"Position distribution: {position_counts}")
    
    if players:
        # Show sample players with new salary estimation
        print("\nSample players with corrected salaries:")
        for i, p in enumerate(sorted(players, key=lambda x: x.projected_dk, reverse=True)[:5]):
            try:
                name = p.name.encode('ascii', 'ignore').decode('ascii')
            except:
                name = "Player_" + p.id
            print(f"  {i+1}. {name} ({p.position}): DK {p.projected_dk:.1f} pts -> ${p.salary_dk:,}")
        
        # Test DraftKings lineup generation with detailed debug
        print("\nTesting DraftKings lineup generation...")
        
        # Manual debug of lineup generation
        config = engine.PLATFORMS['draftkings']
        positions = config['positions']
        salary_cap = config['salary_cap']
        
        print(f"Required positions: {positions}")
        print(f"Salary cap: ${salary_cap:,}")
        
        # Sort players
        sorted_players = sorted(players, key=lambda p: p.projected_dk, reverse=True)
        
        # Manual lineup construction with debug
        lineup_players = []
        total_salary = 0
        
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
        
        success = True
        for i, pos_needed in enumerate(positions):
            eligible_positions = position_groups.get(pos_needed, [pos_needed])
            eligible_players = [
                p for p in sorted_players 
                if p not in lineup_players and 
                p.position in eligible_positions
            ]
            
            print(f"Position {i+1} ({pos_needed}): {len(eligible_players)} eligible players")
            
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
                print(f"  Selected: {name} ({selected_player.position}) ${selected_player.salary_dk:,}")
                print(f"  Running total: ${total_salary:,}")
            else:
                print(f"  FAILED: No affordable player for {pos_needed}")
                print(f"  Current salary: ${total_salary:,}, Cap: ${salary_cap:,}, Remaining: ${salary_cap - total_salary:,}")
                if eligible_players:
                    cheapest = min(eligible_players, key=lambda p: p.salary_dk)
                    try:
                        name = cheapest.name.encode('ascii', 'ignore').decode('ascii')
                    except:
                        name = "Player_" + cheapest.id
                    print(f"  Cheapest eligible: {name} (${cheapest.salary_dk:,})")
                success = False
                break
        
        if success:
            print(f"\nSUCCESS: Generated complete lineup!")
            print(f"Total players: {len(lineup_players)}")
            print(f"Total salary: ${total_salary:,}")
            total_proj = sum(p.projected_dk for p in lineup_players)
            print(f"Total projected: {total_proj:.1f} points")
        else:
            print(f"\nFAILED: Could not complete lineup")
        
        # Also test the actual engine method
        dk_lineup = engine.generate_lineup_greedy(players, 'draftkings')
        
        if dk_lineup:
            print(f"SUCCESS! Generated DK lineup:")
            print(f"  Players: {len(dk_lineup.players)}")
            print(f"  Total salary: ${dk_lineup.total_salary:,}")
            print(f"  Projected points: {dk_lineup.projected_points:.1f}")
            print("  Lineup:")
            for i, p in enumerate(dk_lineup.players):
                try:
                    name = p.name.encode('ascii', 'ignore').decode('ascii')
                except:
                    name = "Player_" + p.id
                print(f"    {i+1}. {name} ({p.position}): {p.projected_dk:.1f} pts, ${p.salary_dk:,}")
        else:
            print("FAILED: Could not generate DK lineup")
        
        # Test FanDuel lineup generation
        print("\nTesting FanDuel lineup generation...")
        fd_lineup = engine.generate_lineup_greedy(players, 'fanduel')
        
        if fd_lineup:
            print(f"SUCCESS! Generated FD lineup:")
            print(f"  Players: {len(fd_lineup.players)}")  
            print(f"  Total salary: ${fd_lineup.total_salary:,}")
            print(f"  Projected points: {fd_lineup.projected_points:.1f}")
        else:
            print("FAILED: Could not generate FD lineup")
    
    else:
        print("ERROR: No valid players created")

if __name__ == "__main__":
    quick_lineup_test()