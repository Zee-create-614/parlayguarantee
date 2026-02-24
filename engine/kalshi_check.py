import requests, json

base = "https://api.elections.kalshi.com/trade-api/v2"

# Try different series tickers for NBA games
for series in ['KXNBAG', 'KXNBA-GAME', 'NBAGAME', 'NBA']:
    r = requests.get(f"{base}/events", params={'limit': 5, 'status': 'open', 'series_ticker': series, 'with_nested_markets': 'true'}, timeout=15)
    data = r.json()
    events = data.get('events', [])
    print(f"{series}: {len(events)} events")
    for e in events[:2]:
        print(f"  {e['event_ticker']}: {e.get('title','')[:80]}")

# Also try searching by category
print("\n--- Category search ---")
r = requests.get(f"{base}/events", params={'limit': 50, 'status': 'open', 'category': 'Sports', 'with_nested_markets': 'true'}, timeout=15)
data = r.json()
events = data.get('events', [])
print(f"Sports events: {len(events)}")
for e in events[:20]:
    ticker = e['event_ticker']
    title = e.get('title', '')[:80]
    n_markets = len(e.get('markets', []))
    print(f"  {ticker} ({n_markets} mkts): {title}")

# Check if any have today's date or game-level resolution
print("\n--- Looking for game-level markets ---")
for e in events:
    title = (e.get('title', '') + ' ' + e.get('sub_title', '')).lower()
    if any(kw in title for kw in ['tonight', 'game', 'beat', 'vs', 'win today', 'feb 23', 'february 23']):
        print(f"  GAME MATCH: {e['event_ticker']}: {e.get('title','')[:100]}")
        for m in e.get('markets', [])[:5]:
            print(f"    {m['ticker']}: yes_bid={m.get('yes_bid')}, title={m.get('title','')[:80]}")
