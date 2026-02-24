import json, os

base = r'C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine'

# Check the bets structure in scored file
f = os.path.join(base, 'all_parlays_2026-02-20_scored.json')
data = json.load(open(f))

print("=== BETS STRUCTURE ===")
bets = data.get('bets', [])
print(f"Total bets: {len(bets)}")
if bets:
    print(f"First bet keys: {list(bets[0].keys())}")
    # Show first few
    for b in bets[:3]:
        print(json.dumps(b, indent=2)[:600])
        print("---")

print("\n=== SCORING SUMMARY ===")
ss = data.get('scoring_summary', {})
print(json.dumps(ss, indent=2)[:2000])

print("\n=== SUMMARY ===")
s = data.get('summary', {})
print(json.dumps(s, indent=2)[:2000])

# Now check dk_parlays files for actual parlay leg data
for dt in ['2026-02-22', '2026-02-23']:
    dk = os.path.join(base, f'picks_{dt}', 'dk_parlays.json')
    if os.path.exists(dk):
        d = json.load(open(dk))
        print(f"\n=== dk_parlays {dt} ===")
        if isinstance(d, list):
            print(f"  {len(d)} parlays")
            if d:
                print(f"  First: {json.dumps(d[0], indent=2)[:600]}")
        elif isinstance(d, dict):
            print(f"  Keys: {list(d.keys())}")
            for k,v in d.items():
                if isinstance(v, list) and v:
                    print(f"  {k}: {len(v)} items")
                    print(f"    First: {json.dumps(v[0], indent=2)[:400]}")
