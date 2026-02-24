import requests, json
key = 'f3c9f91dc369f56dea1b523d3071e1f1'
r = requests.get('https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/', params={'apiKey': key, 'regions': 'us', 'markets': 'h2h,spreads', 'oddsFormat': 'american'})
data = r.json()
for ev in data:
    h, a = ev.get('home_team',''), ev.get('away_team','')
    if 'Montana' in h or 'Montana' in a or 'Idaho' in h or 'Idaho' in a or 'Alabama' in h or 'Weber' in h or 'Weber' in a:
        print(f"\nHOME: {h}  |  AWAY: {a}")
        for bm in ev.get('bookmakers', [])[:3]:
            for mkt in bm['markets']:
                if mkt['key'] == 'spreads':
                    print(f"  {bm['key']}:")
                    for oc in mkt['outcomes']:
                        print(f"    {oc['name']}: point={oc.get('point')} price={oc.get('price')}")
print(f"\nRemaining: {r.headers.get('x-requests-remaining')}")
