"""Run full pipeline, save to ncaab_picks_{date}.json"""
import sys, time, traceback, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('pipeline_run.log', encoding='utf-8')]
)

from datetime import date
target = date(2026, 2, 21)

try:
    from consensus_fetcher import fetch_consensus_games
    from ncaab_engine import NCAABEngine

    games = fetch_consensus_games(target_date=target, sport="ncaab", use_cache=False)
    with open('_pipeline_status.txt', 'w') as f:
        f.write(f"consensus:{len(games)}\n")

    engine = NCAABEngine()
    predictions = engine.predict_games(target)

    with open(f"ncaab_picks_{target}.json", 'w', encoding='utf-8') as f:
        json.dump(predictions, f, indent=2, default=str)

    has_spread = sum(1 for p in predictions if p.get('spread') is not None)
    with open('_pipeline_status.txt', 'w') as f:
        f.write(f"done:{len(predictions)} spreads:{has_spread}\n")

except Exception as e:
    with open('_pipeline_status.txt', 'w') as f:
        f.write(f"error:{e}\n")
    traceback.print_exc(file=open('_pipeline_error.txt', 'w'))
