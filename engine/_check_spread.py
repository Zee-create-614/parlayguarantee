import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from consensus_fetcher import fetch_consensus_games
from datetime import date
g = fetch_consensus_games(date(2026, 2, 21))
print(f"Games: {len(g)}")
print(f"Game 0 spread: {g[0].get('spread')}")
print(f"Game 0 total: {g[0].get('total')}")
print(f"Game 0 home_odds: {g[0].get('home_odds')}")
print(f"Game 0 keys: {list(g[0].keys())}")
