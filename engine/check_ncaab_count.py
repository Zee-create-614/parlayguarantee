import sys, requests
from datetime import datetime, timedelta
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

url = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds'
params = {'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1', 'regions': 'us', 'markets': 'totals'}
r = requests.get(url, params=params, timeout=30)
games = r.json()

times = Counter()
for g in games:
    ct = g.get('commence_time', '')
    utc = datetime.fromisoformat(ct.replace('Z', '+00:00'))
    est = utc + timedelta(hours=-5)
    times[est.strftime('%Y-%m-%d %H:00')] += 1

for t, c in sorted(times.items()):
    print(f"{t} EST: {c} games")

# ESPN check
url2 = 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260221&limit=300'
r2 = requests.get(url2, timeout=15)
espn_games = r2.json().get('events', [])
print(f"\nESPN scheduled: {len(espn_games)} games")

# Show some Odds API games NOT on ESPN
espn_teams = set()
for e in espn_games:
    for c in e['competitions'][0]['competitors']:
        espn_teams.add(c['team']['displayName'])

print(f"\nOdds API games with teams NOT on ESPN schedule:")
count = 0
for g in games:
    home = g['home_team']
    away = g['away_team']
    # Check if either team is in ESPN
    h_found = any(home in t or t in home for t in espn_teams)
    a_found = any(away in t or t in away for t in espn_teams)
    if not h_found and not a_found:
        ct = g.get('commence_time', '')
        utc = datetime.fromisoformat(ct.replace('Z', '+00:00'))
        est = utc + timedelta(hours=-5)
        print(f"  {away} @ {home} — {est.strftime('%I:%M %p')} EST")
        count += 1
        if count >= 10:
            print(f"  ... and more ({148 - 17} extra)")
            break
