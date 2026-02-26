import requests, json, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from autopilot import ODDS_API_KEY
url = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/'
params = {'apiKey': ODDS_API_KEY, 'daysFrom': 2, 'dateFormat': 'iso'}
resp = requests.get(url, params=params, timeout=30)
data = resp.json()
count = 0
for g in data:
    if g.get('completed') and count < 10:
        print(g['away_team'], '@', g['home_team'])
        count += 1
