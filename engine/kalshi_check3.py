import requests, json

base = "https://api.elections.kalshi.com/trade-api/v2"

# Search markets directly for NBA game-level
for query in ['NBA', 'basketball', 'nba game']:
    r = requests.get(f"{base}/markets", params={
        'limit': 50, 'status': 'active'
    }, timeout=15)
    data = r.json()
    markets = data.get('markets', [])
    nba_mkts = [m for m in markets if 'NBA' in m.get('ticker','').upper() or 'basketball' in m.get('title','').lower() or 'nba' in m.get('title','').lower()]
    print(f"Search '{query}': {len(nba_mkts)} NBA markets out of {len(markets)} total")
    for m in nba_mkts[:5]:
        print(f"  {m['ticker']}: last={m.get('last_price')} | {m.get('title','')[:80]}")
    break  # markets endpoint doesn't take query param

# Try specific series tickers that might be game-level
print("\n--- Trying game-level series ---")
for series in ['KXNBAGAME', 'KXNBAML', 'KXNBASPREAD', 'KXNBAOU', 'KXNBAW', 'KXNBA-25FEB23']:
    r = requests.get(f"{base}/events", params={'limit': 5, 'status': 'open', 'series_ticker': series, 'with_nested_markets': 'true'}, timeout=15)
    data = r.json()
    events = data.get('events', [])
    if events:
        print(f"  {series}: {len(events)} events!")
        for e in events[:2]:
            print(f"    {e['event_ticker']}: {e.get('title','')[:80]}")

# Try fetching all markets with KXNBA prefix
print("\n--- Markets with KXNBA prefix ---")
r = requests.get(f"{base}/markets", params={'limit': 200, 'ticker': 'KXNBA', 'status': 'active'}, timeout=15)
data = r.json()
markets = data.get('markets', [])
print(f"Total KXNBA markets: {len(markets)}")
# Show unique event tickers
event_tickers = set()
for m in markets:
    et = m.get('event_ticker', '')
    event_tickers.add(et)
    if 'game' in m.get('title','').lower() or 'win' in m.get('title','').lower() or 'beat' in m.get('title','').lower():
        print(f"  GAME? {m['ticker']}: {m.get('title','')[:80]}")
print(f"Unique event tickers: {sorted(event_tickers)[:20]}")

# Scrape kalshi.com/sports to see what they actually show
print("\n--- Checking kalshi.com/sports/nba ---")
try:
    r = requests.get("https://kalshi.com/sports/nba", timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
    # Look for API calls in the page
    if 'KXNBA' in r.text:
        import re
        tickers = re.findall(r'KXNBA[A-Z0-9\-]+', r.text)
        unique = sorted(set(tickers))[:20]
        print(f"  Found tickers on page: {unique}")
except Exception as e:
    print(f"  Error: {e}")
