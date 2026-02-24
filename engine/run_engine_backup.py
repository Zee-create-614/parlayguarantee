"""
Main orchestrator for ParlayGuarantee Engine
Coordinates data fetching, analysis, parlay generation, and output
Updated for 4-product system: parlay-consistent, parlay-moonshot, straight-weekday, straight-weekend
"""
import logging
import sys
import os
import argparse
import json
import requests
import signal
from datetime import datetime, date
from pathlib import Path

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from product_engine import ProductEngine
# from market_booster import apply_market_boosting  # DISABLED: polymarket dependency removed for A/B test
from config import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('engine.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Exception raised when global script timeout is reached"""
    pass


def timeout_handler(signum, frame):
    """Signal handler for global timeout"""
    raise TimeoutException("Script timeout reached (5 minutes)")


# Legacy engine class - kept for compatibility but now uses ProductEngine
class ParlayGuaranteeEngine:
    """Legacy engine wrapper - now uses ProductEngine for 4-product system"""
    
    def __init__(self, sport: str = 'NBA'):
        self.sport = sport
        self.product_engine = ProductEngine()
        logger.info("ParlayGuarantee Engine initialized with new 4-product system")
    
    def run(self, output_file: str = "picks_output.json") -> bool:
        """Legacy interface - generates all products"""
        try:
            results = self.product_engine.run('all', date.today(), output_file)
            return bool(results)
        except Exception as e:
            logger.error(f"Legacy engine run failed: {str(e)}")
            return False


def main():
    """Main entry point with new product system"""
    parser = argparse.ArgumentParser(description='ParlayGuarantee Engine - 4 Product System')
    parser.add_argument('--product',
                      choices=['parlay-consistent', 'parlay-moonshot', 'straight-weekday', 'straight-weekend', 'all'],
                      default='all',
                      help='Product to generate picks for')
    parser.add_argument('--date',
                      help='Target date (YYYY-MM-DD). For parlays: game date. For straights: start of period.')
    parser.add_argument('--output',
                      default='picks_output.json',
                      help='Output file path')
    parser.add_argument('--check',
                      help='Check results mode: provide picks file path')
    
    args = parser.parse_args()
    
    # Set up global timeout (5 minutes)
    if os.name != 'nt':  # Unix/Linux/Mac
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(300)  # 5 minutes = 300 seconds
    
    try:
        if args.check:
            # Results checking mode (legacy)
            print("Results checking mode not yet implemented for new product system")
            sys.exit(1)
        
        # Parse date
        if args.date:
            try:
                target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
            except ValueError:
                logger.error("Invalid date format. Use YYYY-MM-DD")
                print("❌ Invalid date format. Use YYYY-MM-DD")
                sys.exit(1)
        else:
            target_date = date.today()
        
        # Run product engine
        logger.info("🚀 Starting ParlayGuarantee Engine - 4 Product System")
        logger.info(f"Product: {args.product}")
        logger.info(f"Date: {target_date}")
        
        engine = ProductEngine()
        
        # Use a temporary file for initial engine output to avoid double-saving
        temp_output = f"{args.output}.temp"
        results = engine.run(args.product, target_date, temp_output)
        
        if results:
            # Apply market-based confidence boosting
            logger.info("🎯 Applying prediction market confidence boosting...")
            try:
                results = apply_market_boosting(results, sport='NBA')
                logger.info("✅ Market boosting applied successfully")
            except Exception as e:
                logger.warning(f"Market boosting failed, continuing with original picks: {str(e)}")
                # Add error metadata but continue with original results
                results['_market_boost_error'] = {
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
            
            # Save the enhanced results to the final output file
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            # Clean up temporary file
            try:
                os.remove(temp_output)
            except:
                pass
            # Check if any games were found across all products
            total_games = sum(result['summary']['total_games'] 
                            for result in results.values() 
                            if isinstance(result, dict) and 'summary' in result)
            
            if total_games == 0:
                logger.warning("No games found across all products - generating empty picks output")
                # Create output with empty arrays and no_games flag
                empty_output = {}
                for product_id, result in results.items():
                    empty_output[product_id] = {
                        **result,
                        'no_games': True,
                        'picks': []
                    }
                
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(empty_output, f, indent=2, ensure_ascii=False)
                
                print(f"\n⚠️  No games available today - empty picks generated")
                print(f"📁 Output saved to: {args.output}")
                print("🎯 Ready for deployment (no games mode)")
            else:
                print(f"\n✅ Success! Generated picks for {len(results)} product(s)")
                print(f"📁 Output saved to: {args.output}")
                print("🎯 Ready for deployment to the website!")
                
                # Print quick summary
                print(f"\n📊 Summary:")
                for product_id, result in results.items():
                    # Skip metadata entries (they start with _)
                    if product_id.startswith('_'):
                        continue
                        
                    if isinstance(result, dict) and 'product_name' in result and 'summary' in result:
                        product_name = result['product_name']
                        pick_count = result['summary']['total_picks']
                        game_count = result['summary']['total_games']
                        print(f"  • {product_name}: {pick_count} picks from {game_count} games")
                        
                        # Add market boost summary if available
                        boost_summary = result.get('market_boost_summary', {})
                        if boost_summary and boost_summary.get('picks_with_market_data', 0) > 0:
                            boosted = boost_summary.get('picks_boosted', 0)
                            contrarian = boost_summary.get('picks_contrarian', 0)
                            with_data = boost_summary.get('picks_with_market_data', 0)
                            print(f"    📈 Market boost: {boosted} boosted, {contrarian} contrarian, {with_data}/{pick_count} with data")
                
                # --- Notify users via email after picks are generated ---
                notify_picks(args.output)
        else:
            # No results at all - create completely empty output with no_games flag
            logger.warning("Engine returned no results - creating fallback output")
            fallback_output = {
                'no_games': True,
                'message': 'No games available',
                'date': target_date.isoformat(),
                'generated_at': datetime.now().isoformat()
            }
            
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(fallback_output, f, indent=2, ensure_ascii=False)
            
            print("\n⚠️  No games available - fallback output created")
            print(f"📁 Output saved to: {args.output}")
    
    except TimeoutException:
        logger.error("Script timeout reached (5 minutes) - exiting gracefully")
        print("\n⏱️  Script timeout reached - creating emergency output")
        
        # Create emergency output
        emergency_output = {
            'error': 'timeout',
            'no_games': True,
            'message': 'Script timeout - no picks generated',
            'date': target_date.isoformat() if 'target_date' in locals() else date.today().isoformat(),
            'generated_at': datetime.now().isoformat()
        }
        
        output_file = args.output if 'args' in locals() else 'picks_output.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(emergency_output, f, indent=2, ensure_ascii=False)
        
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n❌ Engine failed: {str(e)}")
        print("📋 Check the logs above for details")
        sys.exit(1)
    
    finally:
        # Cancel timeout if we're done
        if os.name != 'nt':
            signal.alarm(0)


def notify_picks(output_file: str):
    """POST to the notify-picks endpoint to send email notifications after picks generation."""
    engine_secret = os.environ.get('ENGINE_SECRET', '')
    if not engine_secret:
        logger.warning("ENGINE_SECRET not set, skipping email notifications")
        return

    # Check that picks output exists and has data
    try:
        with open(output_file, 'r') as f:
            data = json.load(f)
        if not data:
            logger.info("No picks data, skipping notifications")
            return
        # Count games if possible
        game_count = 0
        if isinstance(data, dict):
            for product in data.values():
                if isinstance(product, dict) and 'summary' in product:
                    game_count = max(game_count, product['summary'].get('total_games', 0))
    except Exception as e:
        logger.warning(f"Could not read picks output for notifications: {e}")
        return

    url = 'https://parlayguarantee.com/api/notify-picks'
    try:
        resp = requests.post(url, json={'gameCount': game_count}, headers={
            'x-engine-secret': engine_secret,
            'Content-Type': 'application/json',
        }, timeout=30)
        logger.info(f"📧 Notify-picks response ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to call notify-picks endpoint: {e}")


if __name__ == "__main__":
    main()