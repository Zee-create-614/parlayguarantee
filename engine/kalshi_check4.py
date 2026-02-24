import requests, json

base = "https://api.elections.kalshi.com/trade-api/v2"

# Get ALL game-level events
for series in ['KXNBAGAME', 'KXNBASPREAD', 'KXNBAOU']:
    r = requests.get(f"{base}/events", params={
        'limit': 50, 'status': 'open', 'series_ticker': series, 'with_nested_markets': 'true'
    }, timeout=15)
    data = r.json()
    events = data.get('events', [])
    print(f"\n=== {series}: {len(events)} events ===")
    for e in events:
        ticker = e['event_ticker']
        title = e.get('title', '')
        markets = e.get('markets', [])
        print(f"\n  {ticker}: {title}")
        for m in markets[:5]:
            yes_bid = m.get('yes_bid', 0)
            yes_ask = m.get('yes_ask', 0)
            last = m.get('last_price', 0)
            vol = m.get('volume', 0)
            mtitle = m.get('title', '')[:80]
            print(f"    {m['ticker']}: yes_bid={yes_bid} yes_ask={yes_ask} last={last} vol={vol} | {mtitle}")
