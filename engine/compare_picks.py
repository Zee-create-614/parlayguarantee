"""
Compare picks: Pure Model vs Upset-Adjusted, plus O/U
Fresh odds pull at runtime.
"""
import sys, json, requests, os
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Load the analyzed games (has both original and upset-flipped picks)
DIR = os.path.dirname(__file__)
with open(os.path.join(DIR, "analyzed_games.json")) as f:
    analyzed = json.load(f)

# Also fetch fresh odds for O/U comparison
print("Fetching fresh NBA odds...")
r = requests.get("https://api.the-odds-api.com/v4/sports/basketball_nba/odds/",
    params={"apiKey": API_KEY, "regions": "us", "markets": "h2h,spreads,totals", "dateFormat": "iso"}, timeout=20)
r.raise_for_status()
all_games = r.json()
remaining = r.headers.get("x-requests-remaining", "?")
print(f"API calls remaining: {remaining}")

# Filter to tonight's games
UTC_START = datetime(2026, 2, 20, 23, 0, tzinfo=timezone.utc)
UTC_END = datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc)
tonight = [g for g in all_games if UTC_START <= datetime.fromisoformat(g["commence_time"].replace("Z","+00:00")) <= UTC_END]
print(f"Tonight's games: {len(tonight)}")

# Build O/U data
def get_ou_data(bms):
    lines = []
    over_prices = []
    under_prices = []
    for bm in bms:
        for m in bm.get("markets", []):
            if m["key"] == "totals":
                for o in m["outcomes"]:
                    if o["name"] == "Over":
                        lines.append(o.get("point", 0))
                        over_prices.append(o.get("price", -110))
                    elif o["name"] == "Under":
                        under_prices.append(o.get("price", -110))
    if not lines:
        return None
    avg_line = sum(lines) / len(lines)
    avg_over = sum(over_prices) / len(over_prices) if over_prices else -110
    avg_under = sum(under_prices) / len(under_prices) if under_prices else -110
    return {"line": round(avg_line, 1), "avg_over": round(avg_over), "avg_under": round(avg_under)}

def get_spread(bms, team):
    pts = [o.get("point",0) for bm in bms for m in bm.get("markets",[]) if m["key"]=="spreads" for o in m["outcomes"] if o["name"]==team]
    return round(sum(pts)/len(pts), 1) if pts else None

print("\n" + "=" * 80)
print("TONIGHT'S NBA PICKS — DUAL VIEW (Fresh Odds)")
print("=" * 80)

# Sort analyzed by original_prob descending (pure model confidence)
print("\n--- PURE MODEL (no upset flips) ---")
print(f"{'#':<3} {'Game':<25} {'Pick':<22} {'Win%':<8} {'Spread':<8}")
print("-" * 70)
model_picks = []
for g in analyzed:
    orig_pick = g.get("original_pick", g["pick"])
    orig_prob = g.get("original_prob", g["win_prob"])
    if g.get("upset_flip"):
        # Flip back to original
        model_picks.append({"home": g["home"], "away": g["away"], "pick": orig_pick, "prob": orig_prob, "spread": g["spread"]})
    else:
        model_picks.append({"home": g["home"], "away": g["away"], "pick": g["pick"], "prob": g["win_prob"], "spread": g["spread"]})

model_picks.sort(key=lambda x: x["prob"], reverse=True)
for i, p in enumerate(model_picks, 1):
    matchup = f"{p['away'][:3].upper()} @ {p['home'][:3].upper()}"
    short_pick = p["pick"].split()[-1]
    marker = "60%+" if p["prob"] >= 0.60 else ""
    print(f"{i:<3} {matchup:<25} {short_pick:<22} {p['prob']:.1%}   {p['spread']:+.1f}  {marker}")

print("\n--- UPSET-ADJUSTED (with composite flips) ---")
print(f"{'#':<3} {'Game':<25} {'Pick':<22} {'Win%':<8} {'Spread':<8} {'Upset':<6} {'Flip?'}")
print("-" * 85)
upset_picks = sorted(analyzed, key=lambda x: x["win_prob"], reverse=True)
for i, g in enumerate(upset_picks, 1):
    matchup = f"{g['away'][:3].upper()} @ {g['home'][:3].upper()}"
    short_pick = g["pick"].split()[-1]
    flipped = "FLIP" if g.get("upset_flip") else ""
    marker = "60%+" if g["win_prob"] >= 0.60 else ""
    print(f"{i:<3} {matchup:<25} {short_pick:<22} {g['win_prob']:.1%}   {g['spread']:+.1f}  {g.get('upset_score',0):.3f}  {flipped}  {marker}")

print("\n--- OVER/UNDERS (fresh from Odds API) ---")
print(f"{'Game':<30} {'Total':<8} {'Over':<8} {'Under':<8} {'Spread':<8}")
print("-" * 70)
for g in tonight:
    h, a = g["home_team"], g["away_team"]
    bms = g.get("bookmakers", [])
    ou = get_ou_data(bms)
    sp = get_spread(bms, h)
    matchup = f"{a[:3].upper()} @ {h[:3].upper()}"
    if ou:
        print(f"{matchup:<30} {ou['line']:<8} {ou['avg_over']:<8} {ou['avg_under']:<8} {sp if sp else 'N/A'}")
    else:
        print(f"{matchup:<30} {'N/A':<8}")

# Show what changed from earlier
print("\n--- KEY DIFFERENCES (Model vs Upset) ---")
for g in analyzed:
    if g.get("upset_flip"):
        orig = g["original_pick"].split()[-1]
        flipped = g["pick"].split()[-1]
        matchup = f"{g['away'][:3].upper()} @ {g['home'][:3].upper()}"
        print(f"  {matchup}: Model says {orig} ({g['original_prob']:.1%}) -> Upset flips to {flipped} ({g['win_prob']:.1%})")
        print(f"    Upset score: {g['upset_score']:.3f} | Reasons: {', '.join(g.get('upset_reasons',[]))}")
