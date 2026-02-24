"""Test engine with just 5 games to find the hang"""
import sys, time, traceback
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger()

from datetime import date
from consensus_fetcher import fetch_consensus_games

# Get games
games = fetch_consensus_games(target_date=date(2026, 2, 21), sport="ncaab")
logger.info(f"Got {len(games)} games, testing first 5")

# Manually run engine steps
from ncaab_engine import NCAABEngine
engine = NCAABEngine()

logger.info("Fetching rankings...")
rankings = engine.fetcher.fetch_espn_rankings()
rank_map = {r['team'].lower(): r['rank'] for r in rankings}
logger.info(f"Rankings: {len(rankings)} teams")

for i, game in enumerate(games[:5]):
    logger.info(f"\n--- Game {i+1}: {game['away_team']} @ {game['home_team']} ---")
    t0 = time.time()
    try:
        pred = engine._analyze_game(game, rank_map, None)
        if pred:
            logger.info(f"  PICK: {pred['predicted_winner']} ({pred['confidence']:.1%}) in {time.time()-t0:.1f}s")
        else:
            logger.info(f"  No prediction in {time.time()-t0:.1f}s")
    except Exception as e:
        logger.error(f"  ERROR: {e}")
        traceback.print_exc()

logger.info("\nDone!")
