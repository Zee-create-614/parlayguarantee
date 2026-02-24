import json, os, requests
from datetime import datetime, timezone
from mega_run_feb21 import extract_picks, american_to_prob, devig, prob_to_american

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
r = requests.get(f"https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/",
    params={"apiKey": API_KEY, "regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"})
raw = r.json()

picks, _ = extract_picks(raw, "NCAAB")
for p in picks:
    if "Montana" in p["home"] or "Montana" in p["away"] or "Idaho S" in p["home"]:
        print(f"{p['away']} @ {p['home']}")
        print(f"  ML: {p['ml_pick']} ({p['ml_prob']:.1%})")
        print(f"  Spread: {p['spread_pick']} {p['pick_spread']:+.1f} (cover: {p['cover_prob']:.1%})")
        print(f"  spread_line (home): {p['spread_line']}")
        print()
