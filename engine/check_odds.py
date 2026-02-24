import requests, json

r = requests.get('https://api.the-odds-api.com/v4/sports/basketball_nba/odds/', params={
    'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1',
    'regions': 'us',
    'markets': 'h2h,spreads,totals',
    'oddsFormat': 'american'
}, timeout=15)
data = r.json()
print(f'Games: {len(data)}')
for g in data:
    print(f"  {g['away_team']} @ {g['home_team']} - {g['commence_time']}")
