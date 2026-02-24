import requests, json

key = "f3c9f91dc369f56dea1b523d3071e1f1"
url = "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds"
params = {"apiKey": key, "regions": "us", "markets": "totals", "date": "2026-02-19T12:00:00Z"}
resp = requests.get(url, params=params, timeout=15)
print(f"Status: {resp.status_code}")
print(f"Remaining: {resp.headers.get('x-requests-remaining', '?')}")
print(f"Used: {resp.headers.get('x-requests-used', '?')}")
if resp.status_code == 200:
    data = resp.json()
    print(json.dumps(data, indent=2)[:2000])
else:
    print(resp.text[:1000])
