"""Full pipeline test: consensus scrape → NCAAB engine → picks output"""
import sys, time, traceback
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('_pipeline_test.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from datetime import date
import json

target = date(2026, 2, 21)

try:
    # Step 1: Get consensus data
    logger.info("=== STEP 1: Consensus Fetch ===")
    t0 = time.time()
    from consensus_fetcher import fetch_consensus_games
    games = fetch_consensus_games(target_date=target, sport="ncaab", use_playwright=True)
    logger.info(f"Got {len(games)} consensus games in {time.time()-t0:.1f}s")

    if not games:
        logger.error("No games! Exiting.")
        sys.exit(1)

    # Step 2: Run NCAAB engine
    logger.info("=== STEP 2: NCAAB Engine ===")
    t1 = time.time()
    from ncaab_engine import NCAABEngine
    engine = NCAABEngine()
    
    # Limit to games that actually have odds (skip games with no spread/total)
    games_with_odds = [g for g in games if g.get('spread') is not None or g.get('total') is not None]
    logger.info(f"Games with odds: {len(games_with_odds)} / {len(games)}")
    
    predictions = engine.predict_games(target)
    logger.info(f"Generated {len(predictions)} predictions in {time.time()-t1:.1f}s")

    # Step 3: Save picks
    output_path = f"ncaab_picks_{target}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, indent=2, default=str)
    logger.info(f"Saved to {output_path}")

    # Top 10 picks
    logger.info("=== TOP 10 PICKS ===")
    for i, p in enumerate(predictions[:10], 1):
        away = p.get('away_team', '?')
        home = p.get('home_team', '?')
        winner = p.get('predicted_winner', '?')
        conf = p.get('confidence', 0)
        spread = p.get('spread', '?')
        books = p.get('available_books', [])
        logger.info(f"  #{i}: {away} @ {home} | PICK: {winner} ({conf:.1%}) spread={spread} books={books}")

    logger.info(f"=== DONE in {time.time()-t0:.1f}s total ===")

except Exception as e:
    logger.error(f"FATAL: {e}")
    traceback.print_exc()
    with open('_pipeline_error.txt', 'w', encoding='utf-8') as f:
        traceback.print_exc(file=f)
    sys.exit(1)
