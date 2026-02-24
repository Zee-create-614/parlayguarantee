import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

url = 'https://api.the-odds-api.com/v4/sports/basketball_nba/odds'
params = {
    'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1',
    'regions': 'us',
    'markets': 'h2h',
    'oddsFormat': 'american'
}
r = requests.get(url, params=params)
remaining = r.headers.get('x-requests-remaining', '?')
print(f"Status: {r.status_code}, Remaining: {remaining}")
data = r.json()
print(f"Games: {len(data)}")
for g in data:
    home = g['home_team']
    away = g['away_team']
    time = g['commence_time']
    # Extract h2h odds
    odds_str = ""
    for bm in g.get('bookmakers', [])[:1]:
        for mkt in bm.get('markets', []):
            if mkt['key'] == 'h2h':
                for outcome in mkt['outcomes']:
                    odds_str += f" {outcome['name']}:{outcome['price']}"
    print(f"  {away} @ {home} | {time} |{odds_str}")
