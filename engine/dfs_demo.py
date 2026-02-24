"""
Quick demo of the DFS engine with a single date
"""

import json
import logging
from datetime import datetime
from dfs_backtest import DFSBacktester

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def demo_single_date():
    """Demo the system with a single date"""
    backtester = DFSBacktester()
    
    # Test a single date
    test_date = "2024-12-01"
    logger.info(f"Running demo backtest for {test_date}")
    
    result = backtester.backtest_single_date(test_date)
    
    if result:
        print(f"\n{'='*60}")
        print(f"DFS ENGINE DEMO RESULTS - {test_date}")
        print(f"{'='*60}")
        
        print(f"Games found: {result['games_count']}")
        print(f"Players found: {result['players_count']}")
        
        for platform in ['draftkings', 'fanduel']:
            platform_results = result['results'][platform]
            print(f"\n{platform.upper()} RESULTS:")
            print("-" * 40)
            
            print(f"Lineups generated: {len(platform_results['lineups'])}")
            print(f"Best actual score: {platform_results['best_score']:.1f}")
            print(f"ITM threshold: {backtester.ITM_THRESHOLDS[platform]}")
            print(f"ITM lineups: {platform_results['itm_count']}")
            
            print("\nLineurs:")
            for i, lineup in enumerate(platform_results['lineups'], 1):
                print(f"  {i}. {lineup['strategy']}: "
                      f"{lineup['projected_points']:.1f} proj → "
                      f"{lineup['actual_points']:.1f} actual "
                      f"(${lineup['total_salary']:,})")
        
        # Save demo result
        with open('dfs_demo_result.json', 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nDemo results saved to dfs_demo_result.json")
        
    else:
        print("Demo failed - no data available")

if __name__ == "__main__":
    demo_single_date()