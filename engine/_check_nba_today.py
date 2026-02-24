import requests, json
from datetime import datetime, timezone, timedelta

key = 'f3c9f91dc369f56dea1b523d3071e1f1'
url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/odds/?apiKey={key}&regions=us&markets=spreads,h2h&oddsFormat=american&dateFormat=iso'
r = requests.get(url)
games = r.json()

EST = timezone(timedelta(hours=-5))
today = datetime.now(EST).strftime('%Y-%m-%d')

print(f"Total games from Odds API: {len(games)}")
print(f"Today: {today}\n")

for g in games:
    ct = g['commence_time']
    dt = datetime.fromisoformat(ct.replace('Z','+00:00')).astimezone(EST)
    game_date = dt.strftime('%Y-%m-%d')
    game_time = dt.strftime('%I:%M %p EST')
    print(f"{g['away_team']} @ {g['home_team']} | {game_time} | date={game_date}")

print(f"\nRemaining requests: {r.headers.get('x-requests-remaining','?')}")
