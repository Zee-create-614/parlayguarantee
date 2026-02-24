import requests
from datetime import date, timedelta
d = date.today() - timedelta(days=1)
url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d.strftime('%Y%m%d')}"
r = requests.get(url, timeout=15).json()
ev = r['events'][0]
comp = ev['competitions'][0]
print('odds:', comp.get('odds', 'NONE'))
home = [c for c in comp['competitors'] if c['homeAway']=='home'][0]
away = [c for c in comp['competitors'] if c['homeAway']=='away'][0]
print(f"{away['team']['displayName']} @ {home['team']['displayName']}: {away['score']}-{home['score']}")
