import json, os, glob

# Find the latest picks directory
dirs = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "picks_2026-02-21*")))
if not dirs:
    print("No picks dirs found")
    exit()
d = dirs[-1]
print(f"Checking: {d}\n")

f = os.path.join(d, "ncaab_ml_spread.json")
with open(f) as fh:
    data = json.load(fh)

for p in data["picks"]:
    if "Montana" in p.get("home","") or "Montana" in p.get("away","") or "Idaho S" in p.get("home","") or "Weber" in p.get("home","") or "Alabama S" in p.get("home","") or "Alabama S" in p.get("away",""):
        print(f"{p['away']} @ {p['home']}")
        print(f"  ML: {p['ml_pick']} ({p['ml_prob']:.1%})")
        print(f"  spread_pick: {p['spread_pick']}, spread_line(home): {p['spread_line']}, pick_spread: {p['pick_spread']}")
        print(f"  cover_prob: {p['cover_prob']:.1%}")
        print(f"  DISPLAY WOULD BE: {p['spread_pick']} {p['pick_spread']:+.1f} ({p['cover_prob']:.0%})")
        print()
