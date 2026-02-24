import requests, json

base = "https://api.elections.kalshi.com/trade-api/v2"

# Try markets endpoint directly with NBA search
r = requests.get(f"{base}/markets", params={'limit': 50, 'status': 'active', 'ticker': 'KXNBA'}, timeout=15)
data = r.json()
markets = data.get('markets', [])
print(f"KXNBA markets: {len(markets)}")
for m in markets[:5]:
    print(f"  {m['ticker']}: yes_bid={m.get('yes_bid')}, last={m.get('last_price')} | {m.get('title','')[:80]}")

# Try the sports events endpoint  
print("\n--- All events with cursor ---")
cursor = ""
nba_found = []
for page in range(5):
    params = {'limit': 200, 'status': 'open'}
    if cursor:
        params['cursor'] = cursor
    r = requests.get(f"{base}/events", params=params, timeout=15)
    data = r.json()
    events = data.get('events', [])
    cursor = data.get('cursor', '')
    for e in events:
        t = (e.get('event_ticker','') + e.get('title','')).upper()
        if any(kw in t for kw in ['NBA', 'BASKETBALL', 'NCAAB', 'NCAA', 'NHL', 'HOCKEY', 'UFC', 'MMA']):
            nba_found.append(e)
    if not cursor:
        break

print(f"Found {len(nba_found)} sports-related events across all pages")
for e in nba_found[:10]:
    print(f"  {e['event_ticker']}: {e.get('title','')[:100]}")
    for m in e.get('markets', [])[:3]:
        print(f"    {m.get('ticker','')}: last={m.get('last_price')} yes_bid={m.get('yes_bid')}")
