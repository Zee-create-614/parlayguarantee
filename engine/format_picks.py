import json, os

base = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-21"

all_picks = []

# NBA
with open(os.path.join(base, "nba_ml_spread.json")) as f:
    data = json.load(f)
for p in data["picks"]:
    ml_pick = p["ml_pick"]
    spread_pick = p["spread_pick"]
    cover_prob = p.get("cover_prob", 0.5)
    all_picks.append({
        "sport": "NBA",
        "away": p["away"],
        "home": p["home"],
        "ml_pick": ml_pick,
        "spread_pick": spread_pick,
        "ml_prob": p["ml_prob"],
        "cover_prob": cover_prob,
        "spread_line": p["spread_line"],
        "spread_side": p["spread_side"],
        "time": p["commence_time"],
    })

# NCAAB
with open(os.path.join(base, "ncaab_ml_spread.json")) as f:
    data = json.load(f)
for p in data["picks"]:
    ml_pick = p["ml_pick"]
    spread_pick = p["spread_pick"]
    cover_prob = p.get("cover_prob", 0.5)
    all_picks.append({
        "sport": "NCAAB",
        "away": p["away"],
        "home": p["home"],
        "ml_pick": ml_pick,
        "spread_pick": spread_pick,
        "ml_prob": p["ml_prob"],
        "cover_prob": cover_prob,
        "spread_line": p["spread_line"],
        "spread_side": p["spread_side"],
        "time": p["commence_time"],
    })

def format_section(picks, sport_label, emoji):
    lines = []
    # Sort by ML confidence
    sorted_picks = sorted(picks, key=lambda x: x["ml_prob"], reverse=True)
    for i, p in enumerate(sorted_picks, 1):
        ml_pct = f"{p['ml_prob']*100:.1f}%"
        cover_pct = f"{p['cover_prob']*100:.1f}%"
        
        # Icon logic:
        # ✅✅ = ML win confident AND spread cover confident (>55%)
        # ✅❌ = ML win confident but spread cover weak (<=55%)
        spread_confident = p["cover_prob"] > 0.55
        icon = "✅✅" if spread_confident else "✅❌"
        
        # Show who we pick for ML and who covers spread
        ml_team = p["ml_pick"]
        spread_team = p["spread_pick"]
        
        # Spread display
        abs_line = abs(p["spread_line"])
        if p["spread_side"] == "home":
            spread_str = f"{p['home']} {p['spread_line']:+.1f}"
        else:
            spread_str = f"{p['away']} {-p['spread_line']:+.1f}" if p['spread_line'] < 0 else f"{p['away']} {p['spread_line']:+.1f}"
        
        lines.append(
            f"{i}. {icon} {ml_team} (ML {ml_pct}) | Cover: {spread_team} {cover_pct} | {p['away']} @ {p['home']}"
        )
    return lines

nba = [p for p in all_picks if p["sport"] == "NBA"]
ncaab = [p for p in all_picks if p["sport"] == "NCAAB"]

nba_covers = sum(1 for p in nba if p["cover_prob"] > 0.55)
ncaab_covers = sum(1 for p in ncaab if p["cover_prob"] > 0.55)

output = f"🏀 ALL PICKS — Feb 21, 2026\n"
output += f"✅✅ = Covers Spread (>55%) | ✅❌ = ML Only (spread risky)\n"
output += f"{'='*55}\n"

output += f"\n🏀 NBA ({len(nba)} picks, {nba_covers} spread covers)\n"
for line in format_section(nba, "NBA", "🏀"):
    output += line + "\n"

output += f"\n🏀 NCAAB ({len(ncaab)} picks, {ncaab_covers} spread covers)\n"
for line in format_section(ncaab, "NCAAB", "🏀"):
    output += line + "\n"

print(output)
