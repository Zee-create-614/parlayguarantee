import requests
ELEVEN_KEY = "sk_3bd03ab4e8df0cb2609ff7d1c58b7167a108d24566c432c9"

# Search shared voice library for "all-rounder"
resp = requests.get(
    "https://api.elevenlabs.io/v1/shared-voices",
    headers={"xi-api-key": ELEVEN_KEY},
    params={"search": "all-rounder", "page_size": 5}
)
print(f"Status: {resp.status_code}")
data = resp.json()
for v in data.get("voices", []):
    print(f"  {v['name']} | {v['voice_id']} | {v.get('category','')} | {v.get('description','')[:80]}")

# Also try "allrounder"
resp2 = requests.get(
    "https://api.elevenlabs.io/v1/shared-voices",
    headers={"xi-api-key": ELEVEN_KEY},
    params={"search": "allrounder", "page_size": 5}
)
for v in resp2.json().get("voices", []):
    print(f"  {v['name']} | {v['voice_id']} | {v.get('category','')} | {v.get('description','')[:80]}")
