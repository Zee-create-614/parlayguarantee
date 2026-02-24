import requests, sys
sys.stdout.reconfigure(encoding='utf-8')
API_KEY = 'f3c9f91dc369f56dea1b523d3071e1f1'
url = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/'
params = {'apiKey': API_KEY, 'regions': 'us', 'markets': 'totals', 'oddsFormat': 'american', 'dateFormat': 'iso'}
r = requests.get(url, params=params)
data = r.json()
today_games = [g for g in data if g['commence_time'][:10] in ('2026-02-22','2026-02-23')]
print(f'Total games from API: {len(data)}, today/tonight: {len(today_games)}')
for g in sorted(today_games, key=lambda x: x['commence_time']):
    has_totals = any(b.get('markets') for b in g.get('bookmakers', []))
    print(f"  {g['away_team']} @ {g['home_team']} - {g['commence_time'][:16]} - totals: {has_totals}")
print(f"\nRemaining requests: {r.headers.get('x-requests-remaining')}")
