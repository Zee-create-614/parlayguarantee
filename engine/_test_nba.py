import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
from consensus_fetcher import fetch_consensus_games
from datetime import date

g = fetch_consensus_games(date(2026, 2, 21), sport='nba', use_cache=False, use_playwright=False)
print(f"\nNBA TOTAL: {len(g)} games")
for x in g:
    books = '/'.join(x.get('available_books', []))
    away = x.get('away_team', '?')
    home = x.get('home_team', '?')
    spread = x.get('spread')
    ml_a = x.get('away_odds')
    ml_h = x.get('home_odds')
    print(f"  {away} @ {home} | spread={spread} ML={ml_a}/{ml_h} [{books}]")
