import json, os

base = r'C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine'

# Check bets in scored file
f = os.path.join(base, 'all_parlays_2026-02-20_scored.json')
data = json.load(open(f))

bets = data.get('bets', {})
print(f"Bets type: {type(bets)}")
if isinstance(bets, dict):
    for k in list(bets.keys())[:5]:
        print(f"\n--- Bet type: {k} ---")
        v = bets[k]
        if isinstance(v, list):
            print(f"  {len(v)} parlays")
            for p in v[:2]:
                print(json.dumps(p, indent=2)[:500])
        elif isinstance(v, dict):
            for kk in list(v.keys())[:3]:
                print(f"  {kk}: {json.dumps(v[kk])[:300]}")

# DK parlays
for dt in ['2026-02-22', '2026-02-23']:
    dk = os.path.join(base, f'picks_{dt}', 'dk_parlays.json')
    if os.path.exists(dk):
        d = json.load(open(dk))
        print(f"\n=== dk_parlays {dt} ===")
        print(f"Type: {type(d)}, keys: {list(d.keys()) if isinstance(d, dict) else 'list'}")
        if isinstance(d, dict):
            for k in list(d.keys())[:3]:
                v = d[k]
                if isinstance(v, list) and v:
                    print(f"  {k}: {len(v)} items")
                    print(f"    {json.dumps(v[0])[:400]}")
                else:
                    print(f"  {k}: {str(v)[:200]}")
