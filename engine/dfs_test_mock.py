"""
DFS Mock Test Script - Test lineup generation with mock data (no API calls)
"""

import logging
from typing import Dict, List

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our DFS engine
from dfs_engine import DFSEngine, Player

def create_mock_players() -> List[Player]:
    """Create mock players for testing without API calls"""
    from dfs_engine import DFSEngine
    
    mock_players = []
    engine = DFSEngine()  # Use engine's salary estimation
    
    # Create players for each position with realistic projections
    positions_data = {
        'PG': [
            ('Luka Doncic', 55.0, 52.0),
            ('Trae Young', 48.0, 45.0), 
            ('Chris Paul', 32.0, 30.0),
            ('Russell Westbrook', 38.0, 36.0),
            ('Tyrese Haliburton', 42.0, 40.0),
            ('De\'Aaron Fox', 40.0, 38.0),
            ('Damian Lillard', 45.0, 42.0),
            ('Ja Morant', 47.0, 44.0),
            ('Marcus Smart', 25.0, 24.0),
            ('Terry Rozier', 28.0, 26.0),
            ('Ricky Rubio', 18.0, 17.0),
            ('Monte Morris', 15.0, 14.0),
            ('Ish Smith', 12.0, 11.0),
            ('Frank Ntilikina', 8.0, 7.0)
        ],
        'SG': [
            ('Devin Booker', 48.0, 45.0),
            ('Donovan Mitchell', 42.0, 40.0),
            ('Bradley Beal', 40.0, 38.0),
            ('CJ McCollum', 35.0, 33.0),
            ('Tyler Herro', 32.0, 30.0),
            ('Jalen Green', 30.0, 28.0),
            ('Anfernee Simons', 33.0, 31.0),
            ('Jordan Poole', 28.0, 26.0),
            ('Austin Reaves', 25.0, 24.0),
            ('Malik Beasley', 22.0, 21.0),
            ('Gary Trent Jr', 18.0, 17.0),
            ('Shake Milton', 15.0, 14.0),
            ('Kentavious Caldwell-Pope', 12.0, 11.0),
            ('Danny Green', 8.0, 7.0)
        ],
        'SF': [
            ('LeBron James', 52.0, 49.0),
            ('Kevin Durant', 50.0, 47.0),
            ('Jayson Tatum', 48.0, 45.0),
            ('Jimmy Butler', 42.0, 40.0),
            ('Kawhi Leonard', 45.0, 42.0),
            ('Paul George', 40.0, 38.0),
            ('Scottie Barnes', 35.0, 33.0),
            ('Franz Wagner', 32.0, 30.0),
            ('Mikal Bridges', 30.0, 28.0),
            ('Harrison Barnes', 25.0, 24.0),
            ('Otto Porter Jr', 18.0, 17.0),
            ('Torrey Craig', 15.0, 14.0),
            ('TJ Warren', 12.0, 11.0),
            ('Matt Ryan', 8.0, 7.0)
        ],
        'PF': [
            ('Giannis Antetokounmpo', 58.0, 55.0),
            ('Jayson Tatum', 48.0, 45.0),
            ('Pascal Siakam', 40.0, 38.0),
            ('Julius Randle', 38.0, 36.0),
            ('Paolo Banchero', 35.0, 33.0),
            ('Tobias Harris', 30.0, 28.0),
            ('John Collins', 32.0, 30.0),
            ('Jerami Grant', 28.0, 26.0),
            ('Bobby Portis', 25.0, 24.0),
            ('PJ Washington', 22.0, 21.0),
            ('Blake Griffin', 18.0, 17.0),
            ('Thaddeus Young', 15.0, 14.0),
            ('JaVale McGee', 12.0, 11.0),
            ('Juan Toscano-Anderson', 8.0, 7.0)
        ],
        'C': [
            ('Nikola Jokic', 60.0, 57.0),
            ('Joel Embiid', 55.0, 52.0),
            ('Anthony Davis', 50.0, 47.0),
            ('Domantas Sabonis', 45.0, 42.0),
            ('Bam Adebayo', 40.0, 38.0),
            ('Alperen Sengun', 38.0, 36.0),
            ('Myles Turner', 35.0, 33.0),
            ('Robert Williams', 30.0, 28.0),
            ('Mason Plumlee', 25.0, 24.0),
            ('Daniel Gafford', 22.0, 21.0),
            ('Dwight Howard', 18.0, 17.0),
            ('Andre Drummond', 15.0, 14.0),
            ('Thomas Bryant', 12.0, 11.0),
            ('Bismack Biyombo', 8.0, 7.0)
        ]
    }
    
    player_id = 1
    for position, player_data in positions_data.items():
        for name, dk_proj, fd_proj in player_data:
            # Use engine's salary estimation method
            dk_salary = engine.estimate_salary(dk_proj, fd_proj, 'draftkings')
            fd_salary = engine.estimate_salary(dk_proj, fd_proj, 'fanduel')
            
            player = Player(
                id=str(player_id),
                name=name,
                position=position,
                team='MOCK',
                salary_dk=dk_salary,
                salary_fd=fd_salary,
                projected_dk=dk_proj,
                projected_fd=fd_proj,
                value_dk=dk_proj / (dk_salary / 1000) if dk_salary > 0 else 0,
                value_fd=fd_proj / (fd_salary / 1000) if fd_salary > 0 else 0,
                recent_games=[]
            )
            
            mock_players.append(player)
            player_id += 1
    
    return mock_players

def test_lineup_generation():
    """Test lineup generation with mock data"""
    print("DFS MOCK TEST - Testing lineup generation with realistic data")
    print("="*70)
    
    # Create mock players
    players = create_mock_players()
    print(f"Created {len(players)} mock players")
    
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
    
    # Initialize engine
    engine = DFSEngine()
    
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
    
    # Test multiple strategies
    print(f"\nTesting all strategies:")
    
    strategies = [
        ('greedy', engine.generate_lineup_greedy),
        ('value', engine.generate_lineup_value),
    ]
    
    for platform in ['draftkings', 'fanduel']:
        print(f"\n{platform.upper()} strategies:")
        
        for strategy_name, strategy_func in strategies:
            lineup = strategy_func(players, platform)
            if lineup:
                print(f"  {strategy_name}: {lineup.projected_points:.1f} pts, ${lineup.total_salary:,}")
            else:
                print(f"  {strategy_name}: FAILED")
        
        # Test mixed strategies
        for i in range(3):
            mixed_lineup = engine.generate_lineup_mixed(players, platform, f"Mixed {i+1}")
            if mixed_lineup:
                print(f"  mixed_{i+1}: {mixed_lineup.projected_points:.1f} pts, ${mixed_lineup.total_salary:,}")
            else:
                print(f"  mixed_{i+1}: FAILED")
    
    print("\nMock test completed!")

if __name__ == "__main__":
    test_lineup_generation()