"""
VALUE ENGINE DEMO - Test the new value-based picks system
Creates mock game data to demonstrate the value scoring improvements
"""

import json
import logging
from datetime import datetime, date
from tier_engine import TierEngine

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def create_mock_game_data():
    """Create mock NBA game data for testing value engine"""
    
    # Mock game data with the Cavs @ Hornets example from the request
    mock_games = [
        {
            'game_id': 'game_001',
            'home_team': 'Charlotte Hornets',
            'away_team': 'Cleveland Cavaliers',
            'game_date': '2026-02-20',
            'game_time': '7:00 pm ET',
            'game_status': '7:00 pm ET',
            'spread': 6.3,  # Hornets getting 6.3 points at home
            'original_win_prob': 0.677,  # Cavs 67.7% win prob according to old engine
        },
        {
            'game_id': 'game_002', 
            'home_team': 'Miami Heat',
            'away_team': 'Boston Celtics',
            'game_date': '2026-02-20',
            'game_time': '7:30 pm ET',
            'game_status': '7:30 pm ET',
            'spread': -3.5,  # Heat laying 3.5 at home (pick'em game)
            'original_win_prob': 0.58,
        },
        {
            'game_id': 'game_003',
            'home_team': 'Detroit Pistons', 
            'away_team': 'Oklahoma City Thunder',
            'game_date': '2026-02-20',
            'game_time': '8:00 pm ET', 
            'game_status': '8:00 pm ET',
            'spread': 17.3,  # Thunder laying HUGE 17.3 points on road (trap game!)
            'original_win_prob': 0.95,  # Old engine: Thunder 95% (stacked favorite)
        },
        {
            'game_id': 'game_004',
            'home_team': 'Portland Trail Blazers',
            'away_team': 'Los Angeles Lakers',
            'game_date': '2026-02-20',
            'game_time': '10:30 pm ET',
            'game_status': '10:30 pm ET', 
            'spread': 8.5,  # Blazers getting 8.5 at home (value dog)
            'original_win_prob': 0.72,  # Lakers 72%
        },
        {
            'game_id': 'game_005',
            'home_team': 'Golden State Warriors',
            'away_team': 'Phoenix Suns',
            'game_date': '2026-02-20',
            'game_time': '10:00 pm ET',
            'game_status': '10:00 pm ET',
            'spread': -2.5,  # Warriors slight home favorite
            'original_win_prob': 0.61,
        },
    ]
    
    return mock_games

def mock_calculate_win_probability(home_team: str, away_team: str):
    """Mock the win probability calculation using our test data"""
    
    # Use our predefined probabilities for demo
    prob_map = {
        ('Charlotte Hornets', 'Cleveland Cavaliers'): ('Cleveland Cavaliers', 0.677),
        ('Miami Heat', 'Boston Celtics'): ('Miami Heat', 0.58),
        ('Detroit Pistons', 'Oklahoma City Thunder'): ('Oklahoma City Thunder', 0.95), 
        ('Portland Trail Blazers', 'Los Angeles Lakers'): ('Los Angeles Lakers', 0.72),
        ('Golden State Warriors', 'Phoenix Suns'): ('Golden State Warriors', 0.61),
    }
    
    return prob_map.get((home_team, away_team), (home_team, 0.55))

def test_value_engine():
    """Test the enhanced value engine with mock data"""
    
    print("TESTING VALUE ENGINE UPGRADES")
    print("="*60)
    
    # Create engine and mock its data fetching
    engine = TierEngine()
    
    # Create mock games
    mock_games = create_mock_game_data()
    
    # Simulate the analyzed games process
    analyzed_games = []
    for game in mock_games:
        # Use mock win probability
        winner, prob = mock_calculate_win_probability(game['home_team'], game['away_team'])
        
        # Create analyzed game
        analyzed_game = {
            'home': game['home_team'],
            'away': game['away_team'], 
            'pick': winner,
            'win_prob': prob,
            'game_date': game['game_date'],
            'game_time': game['game_time'],
            'game_id': game['game_id'],
            'game_status': game['game_status'],
            'original_prob': prob,
            'spread': game['spread'],
        }
        
        # Apply VALUE SCORING
        value_score = engine.calculate_value_score(analyzed_game)
        analyzed_game['value_score'] = value_score
        
        # Assign confidence tier
        pick_label = engine._assign_pick_confidence_tier(analyzed_game)
        analyzed_game['pick_label'] = pick_label
        
        analyzed_games.append(analyzed_game)
    
    # Find upset candidates
    upset_candidates = engine.find_upset_candidates(analyzed_games)
    
    # Sort by VALUE SCORE (not win probability!)
    analyzed_games.sort(key=lambda x: x.get('value_score', x['win_prob']), reverse=True)
    
    print("\nGAME ANALYSIS - OLD vs NEW ENGINE:")
    print("="*60)
    
    for i, game in enumerate(analyzed_games):
        print(f"\n#{i+1} VALUE PICK: {game['away']} @ {game['home']}")
        print(f"   Pick: {game['pick']}")
        print(f"   Old Engine: {game['win_prob']:.1%} win prob (would rank by this)")
        print(f"   NEW Value Score: {game['value_score']:.3f}")
        print(f"   Edge vs Market: {game.get('edge_vs_market', 0):+.1%}")
        print(f"   Label: {game['pick_label']}")
        print(f"   Spread: {game['spread']:+.1f}")
        
        if game.get('upset_score', 0) > 0:
            reasons = game.get('upset_reasons', [])
            print(f"   UPSET REASONS: {', '.join(reasons)}")
    
    print("\nUPSET CANDIDATES FOUND:")
    print("="*40)
    for upset in upset_candidates:
        print(f"{upset['away']} @ {upset['home']}")
        print(f"   Score: {upset['upset_score']:.2f}")
        print(f"   Reasons: {', '.join(upset['upset_reasons'])}")
        print()
    
    # Demo the specific Cavs @ Hornets analysis
    print("\nCAVS @ HORNETS SPECIFIC ANALYSIS:")
    print("="*50)
    cavs_hornets_analysis = engine.analyze_specific_game("Hornets", "Cavaliers", analyzed_games)
    
    if 'error' not in cavs_hornets_analysis:
        print(f"Game: {cavs_hornets_analysis['game']}")
        print(f"Old Engine Pick: {cavs_hornets_analysis['basic_pick']} ({cavs_hornets_analysis['win_probability']:.1%})")
        print(f"NEW Value Score: {cavs_hornets_analysis['value_score']:.3f}")
        print(f"Edge vs Market: {cavs_hornets_analysis['edge_vs_market']:+.1%}")
        print(f"Confidence Tier: {cavs_hornets_analysis['pick_label']}")
        print("\nDetailed Analysis:")
        for line in cavs_hornets_analysis['analysis']:
            print(f"   {line}")
    
    # Generate some picks to show diversification
    print(f"\nSAMPLE PICKS (using VALUE SCORING):")
    print("="*50)
    
    # Single picks  
    single_picks = engine.generate_single_picks(analyzed_games, 3)
    print("SINGLE PICKS:")
    for pick in single_picks:
        game = pick['games'][0]
        print(f"  {pick['pick_number']}. {game['away']} @ {game['home']}")
        print(f"     Pick: {game['pick']} | Value: {pick['value_score']:.3f} | {pick['pick_label']}")
    
    # 3-leg parlay (should show diversification)
    parlay_picks = engine.generate_parlay_picks(analyzed_games, 3, 2)  
    print(f"\n3-LEG PARLAYS (DIVERSIFIED):")
    for pick in parlay_picks:
        print(f"  Parlay #{pick['pick_number']}:")
        labels = []
        for game in pick['games']:
            print(f"    - {game['away']} @ {game['home']} | {game['pick']} | {game.get('pick_label', 'N/A')}")
            labels.append(game.get('pick_label', '📊'))
        print(f"    Mix: {' + '.join(labels)} | Combined Value: {pick.get('combined_value_score', 0):.3f}")
    
    print(f"\nVALUE ENGINE UPGRADE COMPLETE!")
    print("Key Improvements:")
    print("   - VALUE SCORING instead of just win probability")
    print("   - EDGE VS MARKET detection") 
    print("   - UPSET CANDIDATE identification")
    print("   - PICK DIVERSIFICATION (no more stacked favorites)")
    print("   - CONFIDENCE TIERS (LOCK/VALUE/UPSET/LEAN)")
    print("   - IMPROVED spread cover probability with normal distribution")

if __name__ == "__main__":
    test_value_engine()