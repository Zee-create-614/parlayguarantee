"""
Test Tier Engine with Mock Data
Tests the new tier system logic without depending on external APIs
"""

import json
import logging
from datetime import datetime, date
from tier_engine import TierEngine

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def create_mock_games():
    """Create mock NBA games for testing"""
    mock_games = [
        {
            'home': 'Boston Celtics',
            'away': 'Los Angeles Lakers',
            'pick': 'Boston Celtics',
            'win_prob': 0.72,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 20:00',
            'game_id': 'mock_001',
            'game_status': '8:00 pm ET'
        },
        {
            'home': 'Golden State Warriors',
            'away': 'Miami Heat',
            'pick': 'Golden State Warriors',
            'win_prob': 0.68,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 22:30',
            'game_id': 'mock_002',
            'game_status': '10:30 pm ET'
        },
        {
            'home': 'Denver Nuggets',
            'away': 'Philadelphia 76ers',
            'pick': 'Denver Nuggets',
            'win_prob': 0.65,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 21:00',
            'game_id': 'mock_003',
            'game_status': '9:00 pm ET'
        },
        {
            'home': 'Phoenix Suns',
            'away': 'Chicago Bulls',
            'pick': 'Phoenix Suns',
            'win_prob': 0.61,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 21:00',
            'game_id': 'mock_004',
            'game_status': '9:00 pm ET'
        },
        {
            'home': 'Milwaukee Bucks',
            'away': 'Atlanta Hawks',
            'pick': 'Milwaukee Bucks',
            'win_prob': 0.59,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 20:00',
            'game_id': 'mock_005',
            'game_status': '8:00 pm ET'
        },
        {
            'home': 'Dallas Mavericks',
            'away': 'Portland Trail Blazers',
            'pick': 'Dallas Mavericks',
            'win_prob': 0.57,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 20:30',
            'game_id': 'mock_006',
            'game_status': '8:30 pm ET'
        },
        {
            'home': 'Utah Jazz',
            'away': 'Orlando Magic',
            'pick': 'Utah Jazz',
            'win_prob': 0.54,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 21:00',
            'game_id': 'mock_007',
            'game_status': '9:00 pm ET'
        },
        {
            'home': 'Sacramento Kings',
            'away': 'Detroit Pistons',
            'pick': 'Sacramento Kings',
            'win_prob': 0.51,
            'game_date': '2026-02-19',
            'game_time': '2026-02-19 22:00',
            'game_id': 'mock_008',
            'game_status': '10:00 pm ET'
        },
    ]
    
    return mock_games

class MockTierEngine(TierEngine):
    """Mock version of TierEngine that uses test data"""
    
    def fetch_and_analyze_games(self, target_date: date):
        """Override to return mock games"""
        logger.info(f"Using mock games for {target_date}")
        return create_mock_games()

def test_tier_engine():
    """Test the tier engine with mock data"""
    print("Testing Tier Engine with Mock Data")
    print("="*50)
    
    # Create mock engine
    engine = MockTierEngine()
    
    # Test date
    target_date = date(2026, 2, 19)
    
    # Run tier engine
    results = engine.generate_tier_picks(target_date)
    
    # Display results
    print(f"\nResults for {target_date}")
    print(f"Total games: {results['total_games']}")
    
    if results.get('no_games'):
        print("WARNING: No games available")
        return
    
    print(f"\nTiers generated:")
    for tier_id in ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg']:
        if tier_id in results['tiers']:
            tier_data = results['tiers'][tier_id]
            pick_count = tier_data['total_picks']
            tier_name = tier_data['tier_name']
            print(f"  • {tier_name}: {pick_count} picks")
            
            # Show first pick from each tier
            if tier_data['picks']:
                first_pick = tier_data['picks'][0]
                games_summary = []
                for game in first_pick['games']:
                    games_summary.append(f"{game['away']} @ {game['home']} ({game['pick']})")
                
                combined_prob = first_pick['combined_prob']
                payout = first_pick['implied_payout']
                print(f"    Example: {' + '.join(games_summary)}")
                print(f"             Combined probability: {combined_prob:.3f} ({payout})")
    
    # Save test results
    output_file = "test_tier_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nTest results saved to: {output_file}")
    
    # Verify no duplicate games in parlays
    print("\nChecking for duplicate games in parlays...")
    duplicates_found = False
    
    for tier_id, tier_data in results['tiers'].items():
        if tier_data['legs'] > 1:  # Only check parlays
            for pick in tier_data['picks']:
                game_ids = [game['game_id'] for game in pick['games']]
                if len(game_ids) != len(set(game_ids)):
                    print(f"ERROR: Duplicates found in {tier_id} pick #{pick['pick_number']}")
                    duplicates_found = True
    
    if not duplicates_found:
        print("SUCCESS: No duplicate games found in parlays")
    
    print("\nTest completed!")

if __name__ == "__main__":
    test_tier_engine()