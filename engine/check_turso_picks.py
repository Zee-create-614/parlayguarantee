import requests, json

url = "https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io"
token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA"

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Turso HTTP API (v2 pipeline)
resp = requests.post(f"{url}/v2/pipeline", headers=headers, json={
    "requests": [
        {"type": "execute", "stmt": {"sql": "SELECT home, away, pick, spread_str, cover_prob, enhanced_prob, sport FROM daily_picks WHERE pick_date='2026-02-22' ORDER BY sport, home"}},
        {"type": "close"}
    ]
})

data = resp.json()
if "results" not in data:
    print("Error:", json.dumps(data, indent=2))
    exit()

result = data["results"][0]
if result.get("type") == "error":
    print("SQL error:", result["error"])
    exit()

rows = result["response"]["result"]["rows"]
cols = [c["name"] for c in result["response"]["result"]["cols"]]
print(f"Total picks: {len(rows)}\n")

for row in rows:
    vals = [c.get("value", "") for c in row]
    home, away, pick, spread, cp, ep, sport = vals
    marker = ""
    for v in [home, away, pick]:
        if v and ("houston" in v.lower() or "kansas" in v.lower()):
            marker = " <-- !!!"
    print(f"[{sport}] {str(away):35s} @ {str(home):35s} | Pick: {str(pick):35s} | Spread: {spread} | CP: {cp}{marker}")
