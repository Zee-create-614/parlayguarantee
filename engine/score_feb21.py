"""Score all 12 parlay sets from Feb 21, 2026 against actual results.
Each file has parlays grouped by leg count. We score the TOP parlay per leg count (highest combined prob)."""
import json, os, sys, requests, re

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-21"
ODDS_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

def fetch_scores():
    scores = {}
    for sport_key in ["basketball_nba", "basketball_ncaab"]:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/"
        params = {"apiKey": ODDS_KEY, "daysFrom": 2, "dateFormat": "iso"}
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            for game in data:
                if game.get("completed"):
                    home = game["home_team"]
                    away = game["away_team"]
                    hs = as_ = None
                    for s in game.get("scores", []):
                        if s["name"] == home: hs = int(s["score"])
                        elif s["name"] == away: as_ = int(s["score"])
                    if hs is not None and as_ is not None:
                        entry = {"home": home, "away": away, "home_score": hs, "away_score": as_,
                                 "total": hs + as_, "winner": home if hs > as_ else away, "margin": hs - as_}
                        scores[home] = entry
                        scores[away] = entry
        except Exception as e:
            print(f"Error fetching {sport_key}: {e}")
    return scores

def check_leg(leg, scores):
    """Returns (hit: bool|None, detail: str)"""
    game_str = leg.get("game", "")
    pick = leg.get("pick", "")
    bet_type = leg.get("type", "").lower()
    
    # Parse teams from "Away @ Home"
    parts = game_str.split(" @ ")
    if len(parts) == 2:
        away, home = parts[0].strip(), parts[1].strip()
    else:
        return None, f"Can't parse: {game_str}"
    
    result = scores.get(home) or scores.get(away)
    if not result:
        return None, f"No result: {game_str}"
    
    actual_margin = result["home_score"] - result["away_score"]  # positive = home won
    
    if "spread" in bet_type:
        # Parse spread from pick like "Team +5.5" or "Team -3.0"
        spread_match = re.search(r'([+-]?\d+\.?\d*)', pick)
        if spread_match:
            spread_val = float(spread_match.group(1))
            # Determine which team the pick is on
            pick_team = re.sub(r'[+-]?\d+\.?\d*', '', pick).strip()
            if pick_team == home or home.startswith(pick_team) or pick_team.startswith(home.split()[-1]):
                # Pick is on home team: home margin + spread > 0 means cover
                covered = actual_margin + spread_val > 0
            else:
                # Pick is on away team: -margin + spread > 0
                covered = -actual_margin + spread_val > 0
            return covered, f"{result['away']} {result['away_score']} @ {result['home']} {result['home_score']}"
        else:
            return None, f"Can't parse spread: {pick}"
    
    elif "ml" in bet_type or "moneyline" in bet_type:
        pick_clean = pick.strip()
        hit = (pick_clean == result["winner"])
        if not hit:
            # Fuzzy match
            hit = result["winner"].startswith(pick_clean.split()[0]) if pick_clean else False
        return hit, f"{result['away']} {result['away_score']} @ {result['home']} {result['home_score']}"
    
    elif "over" in bet_type or "under" in bet_type or "total" in bet_type or "o/u" in bet_type:
        line_match = re.search(r'(\d+\.?\d*)', pick)
        if line_match:
            line = float(line_match.group(1))
            if "over" in pick.lower():
                hit = result["total"] > line
            elif "under" in pick.lower():
                hit = result["total"] < line
            else:
                return None, f"Can't determine O/U: {pick}"
            return hit, f"Total: {result['total']} (line {line})"
        return None, f"Can't parse total: {pick}"
    
    return None, f"Unknown type: {bet_type}"

def score_file(filepath, scores):
    try:
        with open(filepath) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return []
    
    parlays_dict = data.get("parlays", data)
    if isinstance(parlays_dict, list):
        # Flat list of parlays
        all_parlays = parlays_dict
    elif isinstance(parlays_dict, dict):
        # Grouped by leg count
        all_parlays = []
        for size_key in sorted(parlays_dict.keys(), key=lambda x: int(x.split("_")[0]) if x[0].isdigit() else 99):
            group = parlays_dict[size_key]
            if isinstance(group, list) and group:
                # Take top 1 by combined probability
                best = max(group, key=lambda p: p.get("combined_prob", 0))
                best["_size_key"] = size_key
                all_parlays.append(best)
    else:
        return []
    
    results = []
    for parlay in all_parlays:
        legs = parlay.get("legs", [])
        size_key = parlay.get("_size_key", f"{len(legs)}_leg")
        
        leg_results = []
        all_hit = True
        any_unknown = False
        
        for leg in legs:
            if isinstance(leg, str):
                leg_results.append({"pick": leg, "hit": None, "detail": "unparseable"})
                any_unknown = True
                continue
            hit, detail = check_leg(leg, scores)
            leg_results.append({"pick": leg.get("pick","?"), "hit": hit, "detail": detail})
            if hit is None:
                any_unknown = True
            elif not hit:
                all_hit = False
        
        parlay_hit = all_hit and not any_unknown
        results.append({
            "size": size_key,
            "num_legs": len(legs),
            "hit": parlay_hit if not any_unknown else None,
            "combined_prob": parlay.get("combined_prob", 0),
            "legs": leg_results
        })
    return results

def main():
    print("Fetching scores for Feb 21...")
    scores = fetch_scores()
    unique_games = set()
    for v in scores.values():
        unique_games.add(f"{v['away']}@{v['home']}")
    print(f"Found {len(unique_games)} completed games\n")
    
    parlay_files = sorted([f for f in os.listdir(BASE) if f.startswith("parlays_") and f.endswith(".json")])
    
    print(f"{'='*70}")
    print(f"  SCORING 12 PARLAY SETS — Feb 21, 2026 (Top pick per leg count)")
    print(f"{'='*70}\n")
    
    total_parlays = 0
    total_hits = 0
    total_legs = 0
    total_legs_hit = 0
    
    for pf in parlay_files:
        filepath = os.path.join(BASE, pf)
        name = pf.replace("parlays_", "").replace(".json", "").replace("_", " ").upper()
        
        results = score_file(filepath, scores)
        
        hits = sum(1 for r in results if r["hit"] is True)
        misses = sum(1 for r in results if r["hit"] is False)
        unknown = sum(1 for r in results if r["hit"] is None)
        
        leg_hits = sum(1 for r in results for l in r["legs"] if l["hit"] is True)
        leg_total = sum(1 for r in results for l in r["legs"] if l["hit"] is not None)
        
        total_parlays += len(results)
        total_hits += hits
        total_legs += leg_total
        total_legs_hit += leg_hits
        
        print(f"📋 {name}")
        print(f"   Parlays: {hits}✅ {misses}❌ {unknown}❓ / {len(results)} | Legs: {leg_hits}/{leg_total} ({leg_hits/leg_total*100:.0f}%)" if leg_total else f"   {len(results)} parlays (no scoreable legs)")
        
        for r in results:
            emoji = "✅" if r["hit"] else ("❌" if r["hit"] is False else "❓")
            prob_str = f" ({r['combined_prob']*100:.1f}%)" if r['combined_prob'] else ""
            print(f"   {emoji} {r['size']} ({r['num_legs']}-leg){prob_str}")
            for leg in r["legs"]:
                le = "✅" if leg["hit"] else ("❌" if leg["hit"] is False else "❓")
                print(f"      {le} {leg['pick']} — {leg['detail']}")
        print()
    
    print(f"{'='*70}")
    pct = total_hits/total_parlays*100 if total_parlays else 0
    lpct = total_legs_hit/total_legs*100 if total_legs else 0
    print(f"  PARLAYS HIT: {total_hits}/{total_parlays} ({pct:.0f}%)")
    print(f"  INDIVIDUAL LEGS HIT: {total_legs_hit}/{total_legs} ({lpct:.0f}%)")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
