"""
Updated Run Engine for ParlayGuarantee Tier System
Uses the new tier_engine.py to generate picks organized by tier
Updated: 2026-02-19 for new tier system (single, 2leg, 3leg, 4leg, 5leg, 6leg, 7leg)
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

try:
    from tier_engine_v2 import run_tier_engine, print_report
    USE_V2 = True
except ImportError:
    USE_V2 = False

from tier_engine import TierEngine
# DISABLED: Polymarket/prediction markets auto-integration (Josh directive 2026-02-23)
# from market_booster import apply_market_boosting
from dfs_fast import DFSFastEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('tier_engine_run.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Exception raised when global script timeout is reached"""
    pass


def timeout_handler(signum, frame):
    """Signal handler for global timeout"""
    raise TimeoutException("Script timeout reached (5 minutes)")


def main():
    """Main entry point for tier-based picks generation"""
    parser = argparse.ArgumentParser(description='ParlayGuarantee Tier Engine - New System')
    parser.add_argument('--date',
                      help='Target date (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--output',
                      default='picks_output.json',
                      help='Output file path')
    parser.add_argument('--check',
                      help='Check results mode: provide picks file path (not implemented)')
    parser.add_argument('--debug',
                      action='store_true',
                      help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Set up global timeout (5 minutes)
    if os.name != 'nt':  # Unix/Linux/Mac
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(300)  # 5 minutes = 300 seconds
    
    try:
        if args.check:
            print("Results checking mode not yet implemented for tier system")
            sys.exit(1)
        
        # Parse date
        if args.date:
            try:
                target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
            except ValueError:
                logger.error("Invalid date format. Use YYYY-MM-DD")
                print("ERROR: Invalid date format. Use YYYY-MM-DD")
                sys.exit(1)
        else:
            target_date = date.today()
        
        # Run tier engine
        logger.info("Starting ParlayGuarantee Tier Engine")
        logger.info(f"Date: {target_date}")
        
        if USE_V2:
            logger.info("Using Tier Engine v2 (Odds API powered)")
            results = run_tier_engine(str(target_date))
            
            # Save output
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, default=str)
            
            print_report(results)
            print(f"\nSaved to {args.output}")
        else:
            logger.info("Falling back to Tier Engine v1")
            engine = TierEngine()
            odds_api_key = "f3c9f91dc369f56dea1b523d3071e1f1"
            results = engine.run(target_date, args.output, odds_api_key)
        
        if results:
            # Generate DFS lineups after tier picks
            logger.info("Generating DFS lineups...")
            try:
                dfs_engine = DFSFastEngine()
                dfs_results = dfs_engine.generate(target_date)
                if dfs_results:
                    # Save DFS output
                    dfs_output = {
                        'date': target_date.isoformat(),
                        'generated_at': datetime.now().isoformat(),
                        'lineups': dfs_results,
                    }
                    with open('dfs_output.json', 'w', encoding='utf-8') as f:
                        json.dump(dfs_output, f, indent=2)
                    logger.info(f"DFS lineups generated: {len(dfs_results.get('draftkings', []))} DK lineups, {len(dfs_results.get('fanduel', []))} FD lineups")
                else:
                    logger.warning("No DFS lineups generated")
            except Exception as e:
                logger.error(f"DFS generation failed: {str(e)}")
            
            # Check if any games were found
            total_games = results.get('total_games', 0)
            
            if total_games == 0:
                logger.warning("No games found - tier output with no_games flag")
                print(f"\nWARNING: No games available for {target_date}")
                print(f"Output saved to: {args.output}")
                print("Empty picks ready for deployment")
            else:
                # Count total picks across all tiers
                total_picks = sum(
                    tier.get('total_picks', 0) 
                    for tier in results.get('tiers', {}).values()
                )
                
                print(f"\nSUCCESS! Generated picks for tier system")
                print(f"Output saved to: {args.output}")
                print("Ready for deployment to the website!")
                
                # Print detailed summary
                print(f"\nSummary:")
                print(f"  • Total games: {total_games}")
                print(f"  • Total picks: {total_picks}")
                print(f"  • Tiers generated: {len(results.get('tiers', {}))}")
                
                tiers = results.get('tiers', {})
                for tier_id in ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg']:
                    if tier_id in tiers:
                        tier_data = tiers[tier_id]
                        pick_count = tier_data.get('total_picks', 0)
                        tier_name = tier_data.get('tier_name', tier_id)
                        print(f"    - {tier_name}: {pick_count} picks")
                
                # Show generation time
                metadata = results.get('_metadata', {})
                duration = metadata.get('generation_duration_seconds', 0)
                print(f"  • Generation time: {duration:.2f} seconds")
            
            # Notify users via email after picks are generated
            notify_picks(args.output, total_games)
        else:
            # No results at all - create fallback output
            logger.warning("Tier engine returned no results - creating fallback")
            fallback_output = {
                'no_games': True,
                'message': 'No games available',
                'date': target_date.isoformat(),
                'generated_at': datetime.now().isoformat(),
                'tiers': {}
            }
            
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(fallback_output, f, indent=2, ensure_ascii=False)
            
            print("\nWARNING: No games available - fallback output created")
            print(f"Output saved to: {args.output}")
    
    except TimeoutException:
        logger.error("Script timeout reached (5 minutes) - exiting gracefully")
        print("\nTIMEOUT: Script timeout reached - creating emergency output")
        
        # Create emergency output
        emergency_output = {
            'error': 'timeout',
            'no_games': True,
            'message': 'Script timeout - no picks generated',
            'date': target_date.isoformat() if 'target_date' in locals() else date.today().isoformat(),
            'generated_at': datetime.now().isoformat(),
            'tiers': {}
        }
        
        output_file = args.output if 'args' in locals() else 'picks_output.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(emergency_output, f, indent=2, ensure_ascii=False)
        
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\nERROR: Tier engine failed: {str(e)}")
        print("Check the logs above for details")
        
        # Create error output
        error_output = {
            'error': str(e),
            'no_games': True,
            'message': 'Engine error - no picks generated',
            'date': target_date.isoformat() if 'target_date' in locals() else date.today().isoformat(),
            'generated_at': datetime.now().isoformat(),
            'tiers': {}
        }
        
        output_file = args.output if 'args' in locals() else 'picks_output.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(error_output, f, indent=2, ensure_ascii=False)
        
        sys.exit(1)
    
    finally:
        # Cancel timeout if we're done
        if os.name != 'nt':
            signal.alarm(0)


def notify_picks(output_file: str, game_count: int):
    """POST to the notify-picks endpoint to send email notifications after picks generation."""
    engine_secret = os.environ.get('ENGINE_SECRET', '')
    if not engine_secret:
        logger.warning("ENGINE_SECRET not set, skipping email notifications")
        return

    url = 'https://parlayguarantee.com/api/notify-picks'
    try:
        resp = requests.post(url, json={'gameCount': game_count}, headers={
            'x-engine-secret': engine_secret,
            'Content-Type': 'application/json',
        }, timeout=30)
        logger.info(f"Notify-picks response ({resp.status_code}): {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to call notify-picks endpoint: {e}")


if __name__ == "__main__":
    main()