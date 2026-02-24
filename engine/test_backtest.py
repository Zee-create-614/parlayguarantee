"""
Quick test version of the NBA backtesting system to validate functionality
Tests just a few recent dates to ensure everything works before full backtest
"""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from datetime import date, timedelta
from backtest import ParlayBacktester, print_summary

def main():
    print("🧪 Testing NBA Backtest System")
    print("=" * 50)
    
    # Test with actual historical dates from 2024-25 NBA season
    start_date = date(2024, 12, 1)  # Early December 2024
    end_date = date(2024, 12, 5)    # 5 days total
    
    print(f"📅 Testing period: {start_date} to {end_date}")
    print("⏱️  This should take ~2-3 minutes\n")
    
    # Initialize backtester
    backtester = ParlayBacktester(start_date, end_date)
    
    try:
        # Run quick backtest
        overall_results = backtester.run_full_backtest(save_intermediate=False)
        
        # Save test results
        backtester.save_results("test_backtest_results.json")
        
        # Print summary
        if overall_results:
            print_summary(overall_results)
            print(f"\n✅ Test successful! Analyzed {len(backtester.results)} nights")
            print("🚀 Ready to run full backtest with: python backtest.py")
        else:
            print("❌ Test failed - no results generated")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()