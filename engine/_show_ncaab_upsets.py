import json
d = json.load(open('picks_2026-02-21/ncaab_ml_spread.json'))
flips = []
for p in d['picks']:
    uc = p.get('upset_composite', 0)
    if uc > 0:  # Only show actual upsets (model picks the dog)
        flips.append(p)

print(f"{len(flips)} NCAAB upset picks out of {len(d['picks'])} games:\n")
flips.sort(key=lambda x: x['upset_composite'], reverse=True)
for p in flips[:20]:
    uc = p['upset_composite']
    # pick_spread is from picked team's perspective; fall back to computing it
    pick_spread = p.get('pick_spread')
    if pick_spread is None:
        sl = p.get('spread_line', 0)
        pick_spread = sl if p['ml_side'] == 'home' else -sl
    print(f"  {p['ml_pick']} ({pick_spread:+.1f}) [{uc:.0%}] | {p['away']} @ {p['home']}")
