"""Score picks properly using JSON data + ESPN scores. 
Categories: COVERED SPREAD | WON ML ONLY | LOST"""
import json, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load picks
with open(r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-21\ncaab_ml_spread.json") as f:
    ncaab = json.load(f)
with open(r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-21\nba_ml_spread.json") as f:
    nba = json.load(f)

# Load ESPN NCAAB scores
with open(r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\espn_scores_20260221.json") as f:
    espn = json.load(f)

# Build NCAAB score lookup - normalize names
ncaab_scores = {}
for g in espn:
    if g.get("f"):
        ncaab_scores[g["h"].lower()] = g
        ncaab_scores[g["a"].lower()] = g
        # Also index by last word (mascot)
        for team in [g["h"], g["a"]]:
            words = team.lower().split()
            if len(words) > 1:
                ncaab_scores[words[-1]] = g

# Fetch NBA scores
url = "https://api.the-odds-api.com/v4/sports/basketball_nba/scores/"
params = {"apiKey": "f3c9f91dc369f56dea1b523d3071e1f1", "daysFrom": 2, "dateFormat": "iso"}
r = requests.get(url, params=params, timeout=15)
nba_scores = {}
for g in r.json():
    if g.get("completed"):
        sc = {s["name"]: int(s["score"]) for s in g.get("scores", [])}
        home = g["home_team"]
        away = g["away_team"]
        entry = {"h": home, "a": away, "hs": sc.get(home, 0), "as": sc.get(away, 0)}
        nba_scores[home.lower()] = entry
        nba_scores[away.lower()] = entry

def find_game(home, away, lookup):
    """Find game in score lookup"""
    for key in [home.lower(), away.lower()]:
        if key in lookup:
            return lookup[key]
    # Try last word
    for team in [home, away]:
        last = team.lower().split()[-1]
        if last in lookup:
            return lookup[last]
    # Try partial
    for team in [home, away]:
        for word in team.lower().split():
            if len(word) > 4 and word in lookup:
                return lookup[word]
    return None

def score_pick(pick, lookup):
    """Score a single pick. Returns (ml_result, spread_result, details)"""
    home = pick["home"]
    away = pick["away"]
    ml_pick = pick["ml_pick"]
    spread_pick = pick.get("spread_pick", "")
    spread_line = pick.get("pick_spread", 0)
    ml_prob = pick.get("ml_prob", 0)
    cover_prob = pick.get("cover_prob", 0)
    
    game = find_game(home, away, lookup)
    if not game:
        return None, None, home, away, ml_pick, spread_pick, spread_line, ml_prob, cover_prob, None
    
    hs = game["hs"]
    aws = game["as"]
    h = game["h"]
    a = game["a"]
    home_margin = hs - aws
    
    # Determine if ml_pick is home or away in the ACTUAL game
    ml_is_home = None
    for word in ml_pick.lower().split():
        if len(word) > 3:
            if word in h.lower():
                ml_is_home = True
                break
            elif word in a.lower():
                ml_is_home = False
                break
    
    if ml_is_home is None:
        # Last word match
        ml_last = ml_pick.lower().split()[-1]
        if ml_last in h.lower():
            ml_is_home = True
        elif ml_last in a.lower():
            ml_is_home = False
        else:
            return None, None, home, away, ml_pick, spread_pick, spread_line, ml_prob, cover_prob, f"{a} {aws} @ {h} {hs}"
    
    ml_won = (ml_is_home and hs > aws) or (not ml_is_home and aws > hs)
    
    # Spread: determine if spread_pick is home or away
    sp_is_home = None
    for word in spread_pick.lower().split():
        if len(word) > 3:
            if word in h.lower():
                sp_is_home = True
                break
            elif word in a.lower():
                sp_is_home = False
                break
    if sp_is_home is None:
        sp_last = spread_pick.lower().split()[-1] if spread_pick else ""
        if sp_last in h.lower():
            sp_is_home = True
        elif sp_last in a.lower():
            sp_is_home = False
    
    if sp_is_home is not None:
        sp_margin = home_margin if sp_is_home else -home_margin
        spread_covered = (sp_margin + spread_line) > 0
    else:
        spread_covered = None
    
    score_str = f"{a} {aws} @ {h} {hs}"
    pick_margin = home_margin if ml_is_home else -home_margin
    
    return ml_won, spread_covered, home, away, ml_pick, spread_pick, spread_line, ml_prob, cover_prob, score_str, pick_margin

# Score NBA
print("=" * 90)
print("  PICKS vs ACTUAL RESULTS — February 21, 2026")
print("  Categories: COVERED (won + covered spread) | ML ONLY (won but missed spread) | LOST")
print("=" * 90)

print("\n--- NBA PICKS ---\n")
nba_covered = nba_ml = nba_lost = nba_pending = 0
for p in sorted(nba["picks"], key=lambda x: x.get("ml_prob",0), reverse=True):
    result = score_pick(p, nba_scores)
    if result[0] is None:
        print(f"  {result[7]*100:5.1f}% | {result[4]:30s} | PENDING")
        nba_pending += 1
        continue
    ml_won, sp_covered, home, away, ml_pick, sp_pick, sp_line, ml_prob, cover_prob, score, margin = result
    
    if not ml_won:
        tag = "❌ LOST"
        nba_lost += 1
    elif sp_covered:
        tag = "✅ COVERED"
        nba_covered += 1
    else:
        tag = "🟡 ML ONLY"
        nba_ml += 1
    
    print(f"  {ml_prob*100:5.1f}% | {ml_pick:30s} | {score:50s} | {tag} (margin: {margin:+d}, spread: {sp_pick.split()[-1] if sp_pick else '?'} {sp_line:+.1f})")

nba_played = nba_covered + nba_ml + nba_lost
print(f"\n  NBA: {nba_covered} covered, {nba_ml} ML only, {nba_lost} lost ({nba_pending} pending) | ML: {nba_covered+nba_ml}/{nba_played}")

# Score NCAAB
print("\n\n--- NCAAB PICKS ---\n")
nc_covered = nc_ml = nc_lost = nc_pending = nc_nomatch = 0
results_list = []

for p in ncaab["picks"]:
    result = score_pick(p, ncaab_scores)
    if result[0] is None:
        if result[9] is None:
            nc_pending += 1
            results_list.append(("PENDING", result))
        else:
            nc_nomatch += 1
            results_list.append(("NOMATCH", result))
        continue
    ml_won, sp_covered, home, away, ml_pick, sp_pick, sp_line, ml_prob, cover_prob, score, margin = result
    if not ml_won:
        nc_lost += 1
        results_list.append(("LOST", result))
    elif sp_covered:
        nc_covered += 1
        results_list.append(("COVERED", result))
    else:
        nc_ml += 1
        results_list.append(("ML_ONLY", result))

# Sort by confidence descending
results_list.sort(key=lambda x: x[1][7] if len(x[1]) > 7 else 0, reverse=True)

for cat, result in results_list:
    if cat == "PENDING":
        print(f"  {result[7]*100:5.1f}% | {result[4]:35s} | ⏳ NOT PLAYED YET")
        continue
    if cat == "NOMATCH":
        print(f"  {result[7]*100:5.1f}% | {result[4]:35s} | ⚠️  MATCH ERROR ({result[9]})")
        continue
    
    ml_won, sp_covered, home, away, ml_pick, sp_pick, sp_line, ml_prob, cover_prob, score, margin = result
    
    if cat == "LOST":
        tag = "❌ LOST"
    elif cat == "COVERED":
        tag = "✅ COVERED"
    else:
        tag = "🟡 ML ONLY"
    
    sp_team = sp_pick.split()[-1] if sp_pick else "?"
    print(f"  {ml_prob*100:5.1f}% | {ml_pick:35s} | {score:55s} | {tag} (margin: {margin:+d}, line: {sp_line:+.1f})")

nc_played = nc_covered + nc_ml + nc_lost
print(f"\n{'='*90}")
print(f"  NCAAB TOTALS ({nc_played} scored, {nc_pending} pending, {nc_nomatch} unmatched)")
print(f"  ✅ COVERED SPREAD:  {nc_covered}/{nc_played} ({nc_covered/nc_played*100:.1f}%)" if nc_played else "")
print(f"  🟡 WON ML ONLY:    {nc_ml}/{nc_played} ({nc_ml/nc_played*100:.1f}%)" if nc_played else "")
print(f"  ❌ LOST:            {nc_lost}/{nc_played} ({nc_lost/nc_played*100:.1f}%)" if nc_played else "")
ml_total = nc_covered + nc_ml
print(f"  📊 ML WIN RATE:     {ml_total}/{nc_played} ({ml_total/nc_played*100:.1f}%)" if nc_played else "")
print(f"{'='*90}")

# By confidence tier
print("\n  BY CONFIDENCE TIER:")
tiers = [(90,100,"90%+"),(80,90,"80-90%"),(70,80,"70-80%"),(60,70,"60-70%"),(55,60,"55-60%"),(50,55,"50-55%")]
for lo, hi, label in tiers:
    tier_results = [(c,r) for c,r in results_list if c not in ("PENDING","NOMATCH") and lo <= r[7]*100 < hi]
    if not tier_results:
        continue
    t_covered = sum(1 for c,_ in tier_results if c == "COVERED")
    t_ml = sum(1 for c,_ in tier_results if c == "ML_ONLY")
    t_lost = sum(1 for c,_ in tier_results if c == "LOST")
    t_total = len(tier_results)
    t_wins = t_covered + t_ml
    print(f"  {label:8s}: {t_wins}/{t_total} ML ({t_wins/t_total*100:.0f}%) | {t_covered}/{t_total} covered ({t_covered/t_total*100:.0f}%) | {t_ml} ML only | {t_lost} lost")
