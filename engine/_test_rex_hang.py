import logging, json, time, sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from ncaab_engine import NCAABEngine
e = NCAABEngine()

# Load cached consensus
with open('consensus_ncaab_2026-02-24.json') as f:
    data = json.load(f)
    games = data['games'] if isinstance(data, dict) else data

from ncaab_data_fetcher import NCAABDataFetcher
fetcher = NCAABDataFetcher()
rankings = fetcher.fetch_espn_rankings()
rank_map = {r['team'].lower(): r['rank'] for r in rankings}

logger.info(f"Testing {len(games)} games one by one...")

for i, game in enumerate(games[:3]):
    away = game.get('away_team', '?')
    home = game.get('home_team', '?')
    logger.info(f"Game {i+1}: {away} @ {home}")
    t = time.time()
    try:
        pred = e._analyze_game(game, rank_map, None)
        logger.info(f"  Done in {time.time()-t:.1f}s - winner: {pred.get('predicted_winner', '?') if pred else 'None'}")
    except Exception as ex:
        logger.error(f"  Failed in {time.time()-t:.1f}s: {ex}")

logger.info("Test complete")
