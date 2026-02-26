import json

with open(r'C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-25\ncaab_picks.json') as f:
    data = json.load(f)

picks = sorted(data['picks'], key=lambda x: x.get('cover_prob', 0), reverse=True)

def fmt(p):
    prob = int(p.get('cover_prob', 0) * 100)
    return f"{p['pick']} {p['spread_str']} ({prob}%)"

parlays = [
    ("3-LEG PARLAY", picks[:3]),
    ("4-LEG PARLAY", picks[:4]),
    ("5-LEG PARLAY #1", picks[:5]),
    ("5-LEG PARLAY #2", picks[2:7]),
    ("14-LEG PARLAY (FULL SEND)", picks[:14]),
]

for name, legs in parlays:
    combo = 1
    for p in legs:
        combo *= p.get('cover_prob', 0.5)
    print(f"\n{'=' * 50}")
    print(f"{name} | Combined: {combo*100:.1f}%")
    print('=' * 50)
    for i, p in enumerate(legs, 1):
        print(f"  {i}. {fmt(p)}")
