import requests
import json
from datetime import date

url = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores'
params = {
    'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1',
    'daysFrom': 3,
    'dateFormat': 'iso'
}

try:
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    events = resp.json()
    print(f'Found {len(events)} events')
    for i, ev in enumerate(events[:3]):
        commence = ev.get('commence_time', '')
        away = ev.get('away_team', '')
        home = ev.get('home_team', '')
        completed = ev.get('completed', False)
        print(f'{i+1}. {commence} - {away} @ {home} - Completed: {completed}')
        
    if events:
        print('\nFirst event details:')
        print(json.dumps(events[0], indent=2))
        
except Exception as e:
    print(f'Error: {e}')