import requests, json
r = requests.get('https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds',
    params={'apiKey':'f3c9f91dc369f56dea1b523d3071e1f1','regions':'us',
            'markets':'spreads,h2h','oddsFormat':'american'}, timeout=30)
print(f"Remaining: {r.headers.get('x-requests-remaining','?')}")
games = r.json()
for g in games[:5]:
    home = g['home_team']
    away = g['away_team']
    print(f"\n{away} @ {home}")
    for bm in g.get('bookmakers', [])[:1]:
        print(f"  Book: {bm['title']}")
        for mkt in bm.get('markets', []):
            for o in mkt['outcomes']:
                pt = o.get('point', '')
                pr = o.get('price', '')
                print(f"    {mkt['key']}: {o['name']} {pt} ({pr})")
