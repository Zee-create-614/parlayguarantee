import requests, json

url = 'https://api.the-odds-api.com/v4/sports/basketball_nba/scores/'
params = {'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1', 'daysFrom': 2, 'dateFormat': 'iso'}
r = requests.get(url, params=params, timeout=15)
games = r.json()
print(f"Remaining requests: {r.headers.get('x-requests-remaining','?')}")
for g in games:
    if g.get('completed'):
        scores = {s['name']: int(s['score']) for s in g.get('scores', [])}
        home = g['home_team']
        away = g['away_team']
        hs = scores.get(home, '?')
        aws = scores.get(away, '?')
        margin = hs - aws if isinstance(hs, int) and isinstance(aws, int) else '?'
        print(f"{away} {aws} @ {home} {hs}  (margin: {margin})")
