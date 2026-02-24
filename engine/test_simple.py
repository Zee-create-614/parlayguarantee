"""
Simple test script for Engine v2 (no emojis for Windows compatibility)
"""

import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from team_locations import calculate_distance
        print("  Team locations: OK")
        
        from odds_fetcher import OddsFetcher
        print("  Odds fetcher: OK")
        
        from self_learner import SelfLearner  
        print("  Self learner: OK")
        
        # This might fail due to missing dependencies
        try:
            from engine_v2 import NBAPredictor
            print("  Main engine: OK")
            return True
        except ImportError as e:
            print(f"  Main engine: FAILED - {e}")
            print("  Run: pip install -r requirements_v2.txt")
            return False
            
    except Exception as e:
        print(f"Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality"""
    print("\nTesting basic functionality...")
    
    try:
        # Test team locations
        from team_locations import calculate_distance, is_division_rival
        
        distance = calculate_distance('Los Angeles Lakers', 'Boston Celtics')
        print(f"  LAL to BOS distance: {distance:.1f} miles")
        
        rivals = is_division_rival('Los Angeles Lakers', 'LA Clippers')
        print(f"  LAL vs LAC rivals: {rivals}")
        
        # Test self learner
        from self_learner import SelfLearner
        learner = SelfLearner()
        weights = learner.load_weights()
        print(f"  Loaded {len(weights)} factor weights")
        
        # Test odds fetcher
        from odds_fetcher import OddsFetcher
        fetcher = OddsFetcher()
        prob = fetcher.convert_american_to_probability(-110)
        print(f"  -110 odds = {prob:.3f} probability")
        
        print("  Basic functionality: OK")
        return True
        
    except Exception as e:
        print(f"  Basic functionality error: {e}")
        return False

def main():
    """Run tests"""
    print("ParlayGuarantee Engine v2 - Quick Test")
    print("=" * 40)
    
    success = True
    
    if not test_imports():
        success = False
        
    if not test_basic_functionality():
        success = False
    
    print("\n" + "=" * 40)
    
    if success:
        print("Tests passed! Engine v2 components are working.")
        print("\nTo run the full engine:")
        print("  python engine_v2.py --product all --date 2026-02-17")
    else:
        print("Some tests failed. Check dependencies and setup.")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)