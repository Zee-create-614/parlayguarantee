import requests, json

r = requests.get('https://site.api.espn.com/apis/v2/sports/basketball/nba/standings', timeout=10)
data = r.json()

children = data.get('children', [])
print(f'Conferences: {len(children)}')

for conf in children:
    conf_name = conf.get('name', '?')
    standings = conf.get('standings', {})
    entries = standings.get('entries', [])
    print(f'\n{conf_name}: {len(entries)} teams')
    
    for e in entries[:3]:
        team = e.get('team', {})
        team_name = team.get('displayName', '?')
        stats = {s['name']: s.get('value', s.get('displayValue', '?')) for s in e.get('stats', [])}
        wins = stats.get('wins', '?')
        losses = stats.get('losses', '?')
        wpct = stats.get('winPercent', stats.get('winPct', '?'))
        ppg = stats.get('pointsFor', stats.get('avgPointsFor', '?'))
        papg = stats.get('pointsAgainst', stats.get('avgPointsAgainst', '?'))
        print(f'  {team_name}: {wins}W-{losses}L ({wpct}) PPG={ppg} PAPG={papg}')
        if team_name == '?':
            print(f'    ALL STATS: {json.dumps(stats, indent=4)[:500]}')
        # Print first team's full stat list for debugging
    
    if entries:
        e0 = entries[0]
        team = e0.get('team', {})
        print(f'\n  SAMPLE full stats for {team.get("displayName","?")}:')
        for s in e0.get('stats', []):
            print(f'    {s.get("name","?")}: {s.get("value","?")} ({s.get("displayValue","?")})')
