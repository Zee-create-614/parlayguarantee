import json

with open("mgm_fixtures.json") as f:
    d = json.load(f)

fix = d["fixtures"]
print(f"Total fixtures: {len(fix)}")

f0 = fix[0]
print(f"Keys: {list(f0.keys())}")
print(f"Name: {f0.get('name')}")
print(f"Start: {f0.get('startDate')}")

for p in f0.get("participants", []):
    nm = p.get("name")
    if isinstance(nm, dict):
        nm = nm.get("value", "")
    print(f"  Participant: {nm} role={p.get('venueRole', '?')}")

for g in f0.get("games", [])[:5]:
    gn = g.get("name", {})
    if isinstance(gn, dict):
        gn = gn.get("value", "")
    print(f"\n  Game: {gn}")
    for r in g.get("results", [])[:3]:
        rn = r.get("name", {})
        if isinstance(rn, dict):
            rn = rn.get("value", "")
        print(f"    Result: {rn} americanOdds={r.get('americanOdds')} handicap={r.get('handicap')}")
