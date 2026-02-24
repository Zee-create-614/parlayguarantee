import requests, json
url = 'https://site.api.espn.com/apis/v2/sports/basketball/nba/standings'
r = requests.get(url, timeout=15)
data = r.json()
entry = data['children'][0]['standings']['entries'][0]
team = entry['team']['displayName']
print(f'Team: {team}')
print('Stats:')
for s in entry.get('stats', []):
    name = s.get('name', '?')
    val = s.get('value', '?')
    dv = s.get('displayValue', '?')
    print(f'  {name} = {val} (display: {dv})')
