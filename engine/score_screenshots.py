"""Score the exact picks Josh sent via screenshot against actual results.
Categories: COVERED SPREAD | WON ML ONLY | LOST"""
import json, requests, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ODDS_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# The picks from Josh's 3 screenshots (extracted from images)
# Format: (pick_team, opponent, home_team, away_team, confidence, spread_line)
# spread_line is the line the picked team needs to cover (negative = favorite)

nba_picks = [
    # From screenshot: 6 NBA picks
    ("San Antonio Spurs", "Sacramento Kings", "San Antonio Spurs", "Sacramento Kings", 91.4, -16.5),
    ("Detroit Pistons", "Chicago Bulls", "Chicago Bulls", "Detroit Pistons", 81.8, None),
    ("Miami Heat", "Memphis Grizzlies", "Miami Heat", "Memphis Grizzlies", 60.0, None),
    ("Philadelphia 76ers", "New Orleans Pelicans", "New Orleans Pelicans", "Philadelphia 76ers", 59.4, None),
    ("New York Knicks", "Houston Rockets", "New York Knicks", "Houston Rockets", 59.4, None),
    ("Phoenix Suns", "Orlando Magic", "Phoenix Suns", "Orlando Magic", 53.1, None),
]

# Actual NBA scores (from Odds API)
nba_scores = {
    "Philadelphia 76ers @ New Orleans Pelicans": {"home": "New Orleans Pelicans", "away": "Philadelphia 76ers", "hs": 126, "as": 111},
    "Detroit Pistons @ Chicago Bulls": {"home": "Chicago Bulls", "away": "Detroit Pistons", "hs": 110, "as": 126},
    "Memphis Grizzlies @ Miami Heat": {"home": "Miami Heat", "away": "Memphis Grizzlies", "hs": 136, "as": 120},
    "Sacramento Kings @ San Antonio Spurs": {"home": "San Antonio Spurs", "away": "Sacramento Kings", "hs": 139, "as": 122},
    "Houston Rockets @ New York Knicks": {"home": "New York Knicks", "away": "Houston Rockets", "hs": 108, "as": 106},
    "Orlando Magic @ Phoenix Suns": {"home": "Phoenix Suns", "away": "Orlando Magic", "hs": 113, "as": 110},
}

# Load NCAAB picks from the JSON (matches what screenshots show)
with open(r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-21\ncaab_ml_spread.json") as f:
    ncaab_data = json.load(f)

# Load ESPN scores
with open(r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\espn_scores_20260221.json") as f:
    espn_raw = json.load(f)

# Build score lookup by team name
scores = {}
for g in espn_raw:
    if g.get("f"):
        scores[g["h"]] = g
        scores[g["a"]] = g

# Also fetch fresh NBA scores
def get_nba_scores():
    url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/scores/"
    params = {"apiKey": ODDS_KEY, "daysFrom": 2, "dateFormat": "iso"}
    r = requests.get(url, params=params, timeout=15)
    result = {}
    for g in r.json():
        if g.get("completed"):
            sc = {s["name"]: int(s["score"]) for s in g.get("scores", [])}
            home = g["home_team"]
            away = g["away_team"]
            result[home] = {"h": home, "a": away, "hs": sc.get(home, 0), "as": sc.get(away, 0)}
            result[away] = result[home]
    return result

nba_score_lookup = get_nba_scores()

def classify_pick(pick_team, home, away, spread_line, score_data):
    """Returns (category, score_str, margin_detail)"""
    if not score_data:
        return "NO RESULT", "—", ""
    
    hs = score_data["hs"]
    aws = score_data["as"]
    h = score_data["h"]
    a = score_data["a"]
    
    actual_winner = h if hs > aws else a
    margin = abs(hs - aws)
    score_str = f"{a} {aws} @ {h} {hs}"
    
    # Did our pick win ML?
    ml_won = (pick_team == actual_winner) or actual_winner.startswith(pick_team.split()[0])
    
    # Fuzzy match
    if not ml_won:
        # Try last word match
        pick_words = pick_team.lower().split()
        winner_words = actual_winner.lower().split()
        if pick_words[-1] == winner_words[-1]:
            ml_won = True
    
    if not ml_won:
        return "LOST", score_str, f"Winner: {actual_winner} by {margin}"
    
    # Check spread coverage
    if spread_line is not None:
        # pick_team's perspective margin
        if pick_team == h or any(w in h.lower() for w in pick_team.lower().split()[-1:]):
            pick_margin = hs - aws  # home margin
        else:
            pick_margin = aws - hs  # away margin
        
        covered = pick_margin + spread_line > 0 if spread_line > 0 else pick_margin > abs(spread_line)
        # Simpler: if favorite (negative spread), they need to win by more than spread
        # if dog (positive spread), they just need to lose by less than spread or win
        
        # Let's do it properly:
        # spread_line from the JSON: positive means dog getting points, negative means favorite giving points
        # Actually from the data, spread_pick is the team, pick_spread is the line
        # If pick is on home and spread is -10, home needs to win by >10
        # If pick is on away and spread is +5, away can lose by up to 5
        
        # Since we confirmed ML won, check if they covered
        if pick_margin > abs(spread_line) if spread_line < 0 else True:
            return "COVERED ✅", score_str, f"Won by {pick_margin}, line {spread_line}"
        else:
            return "WON ML ONLY 🟡", score_str, f"Won by {pick_margin}, needed {abs(spread_line)}"
    else:
        return "WON ML ✅", score_str, ""

# Now score everything using the JSON data which matches screenshots
print("=" * 80)
print("  JOSH'S PICKS vs ACTUAL RESULTS — February 21, 2026")
print("=" * 80)

# NBA
print("\n🏀 NBA PICKS (6)")
print("-" * 80)

nba_results = {"COVERED": 0, "ML_ONLY": 0, "LOST": 0}

for pick_team, opp, home, away, conf, spread in nba_picks:
    game = nba_score_lookup.get(home) or nba_score_lookup.get(away)
    if game:
        hs = game["hs"]
        aws = game["as"]
        h = game["h"]
        a = game["a"]
        actual_winner = h if hs > aws else a
        pick_margin = (hs - aws) if pick_team in h or h.startswith(pick_team.split()[0]) else (aws - hs)
        ml_won = pick_team in actual_winner or actual_winner.startswith(pick_team.split()[0])
        
        if not ml_won:
            status = "❌ LOST"
            nba_results["LOST"] += 1
        else:
            status = "✅ WON"
            nba_results["COVERED"] += 1
        
        print(f"  {conf:5.1f}% | {pick_team:30s} | {a} {aws} @ {h} {hs} | {status} (margin: {pick_margin:+d})")
    else:
        print(f"  {conf:5.1f}% | {pick_team:30s} | NO RESULT YET")

print(f"\n  NBA: {nba_results['COVERED']} WON, {nba_results['LOST']} LOST")

# NCAAB - use JSON data
print("\n\n🏀 NCAAB PICKS (from screenshots, sorted by confidence)")
print("-" * 80)

ncaab_picks = ncaab_data.get("picks", [])
ncaab_picks.sort(key=lambda x: x.get("ml_prob", 0), reverse=True)

covered = 0
ml_only = 0
lost = 0
no_result = 0

for p in ncaab_picks:
    home = p["home"]
    away = p["away"]
    ml_pick = p["ml_pick"]
    spread_pick = p.get("spread_pick", "")
    spread_line = p.get("pick_spread", 0)
    conf = p.get("ml_prob", 0) * 100
    cover_prob = p.get("cover_prob", 0) * 100
    
    # Find score
    game = scores.get(home) or scores.get(away)
    
    # Try fuzzy match
    if not game:
        for key in scores:
            if home.split()[0] in key or (len(home.split()) > 1 and home.split()[-1] in key):
                game = scores[key]
                break
    if not game:
        for key in scores:
            if away.split()[0] in key or (len(away.split()) > 1 and away.split()[-1] in key):
                game = scores[key]
                break
    
    if not game:
        no_result += 1
        print(f"  {conf:5.1f}% | {ml_pick:35s} | ⏳ NOT PLAYED YET")
        continue
    
    hs = game["hs"]
    aws = game["as"]
    h = game["h"]
    a = game["a"]
    actual_winner = h if hs > aws else a
    home_margin = hs - aws
    
    # Did ML pick win?
    ml_won = False
    pick_is_home = False
    
    # Match pick to home/away
    ml_lower = ml_pick.lower()
    h_lower = h.lower()
    a_lower = a.lower()
    
    if ml_lower in h_lower or h_lower in ml_lower:
        pick_is_home = True
        ml_won = hs > aws
    elif ml_lower in a_lower or a_lower in ml_lower:
        pick_is_home = False
        ml_won = aws > hs
    else:
        # Fuzzy: last word
        ml_last = ml_lower.split()[-1]
        if ml_last in h_lower:
            pick_is_home = True
            ml_won = hs > aws
        elif ml_last in a_lower:
            pick_is_home = False
            ml_won = aws > hs
        else:
            # Try first significant word
            for w in ml_lower.split():
                if len(w) > 3:
                    if w in h_lower:
                        pick_is_home = True
                        ml_won = hs > aws
                        break
                    elif w in a_lower:
                        pick_is_home = False
                        ml_won = aws > hs
                        break
    
    pick_margin = home_margin if pick_is_home else -home_margin
    
    # Spread check: spread_pick team + spread_line
    spread_is_home = False
    sp_lower = spread_pick.lower()
    if sp_lower in h_lower or h_lower in sp_lower:
        spread_is_home = True
    elif sp_lower in a_lower or a_lower in sp_lower:
        spread_is_home = False
    else:
        sp_last = sp_lower.split()[-1] if sp_lower else ""
        if sp_last in h_lower:
            spread_is_home = True
        elif sp_last in a_lower:
            spread_is_home = False
    
    spread_margin = home_margin if spread_is_home else -home_margin
    spread_covered = (spread_margin + spread_line) > 0
    
    if not ml_won:
        status = "❌ LOST"
        lost += 1
    elif spread_covered:
        status = "✅ COVERED"
        covered += 1
    else:
        status = "🟡 ML ONLY"
        ml_only += 1
    
    score_str = f"{a} {aws} @ {h} {hs}"
    spread_detail = f"(spread: {spread_pick.split()[-1]} {spread_line:+.1f}, margin: {spread_margin:+d})"
    print(f"  {conf:5.1f}% | {ml_pick:35s} | {score_str:55s} | {status} {spread_detail}")

total_played = covered + ml_only + lost
print(f"\n{'=' * 80}")
print(f"  NCAAB TOTALS ({total_played} games played, {no_result} pending)")
print(f"  ✅ COVERED SPREAD:  {covered}/{total_played} ({covered/total_played*100:.1f}%)" if total_played else "")
print(f"  🟡 WON ML ONLY:    {ml_only}/{total_played} ({ml_only/total_played*100:.1f}%)" if total_played else "")
print(f"  ❌ LOST:            {lost}/{total_played} ({lost/total_played*100:.1f}%)" if total_played else "")
print(f"  ML WIN RATE:        {covered+ml_only}/{total_played} ({(covered+ml_only)/total_played*100:.1f}%)" if total_played else "")
print(f"{'=' * 80}")
