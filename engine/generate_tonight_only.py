"""
Generate ALL parlays for TONIGHT ONLY — games that haven't tipped off yet.
This is the real test batch with accurate numbers.
"""
import sys, json, itertools, requests, os
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(__file__)
API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
NOW = datetime.now(timezone.utc)

# Only count games starting AFTER now
CUTOFF = NOW + timedelta(minutes=5)

TANK_TEAMS = {
    "Washington Wizards", "Charlotte Hornets", "Brooklyn Nets",
    "Portland Trail Blazers", "Utah Jazz",
}

def fetch_odds(sport):
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
        params={"apiKey": API_KEY, "regions": "us", "markets": "h2h,spreads,totals", "dateFormat": "iso"}, timeout=20)
    r.raise_for_status()
    remaining = r.headers.get("x-requests-remaining", "?")
    data = r.json()
    # Filter to only upcoming games
    upcoming = []
    for g in data:
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        if ct > CUTOFF:
            upcoming.append(g)
    print(f"  {sport}: {len(upcoming)} upcoming out of {len(data)} total (API remaining: {remaining})")
    return upcoming

def avg_odds(bookmakers, market_key, team):
    prices = []
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == market_key:
                for o in mkt["outcomes"]:
                    if o["name"] == team:
                        prices.append(o["price"])
    return sum(prices) / len(prices) if prices else None

def avg_spread(bookmakers, team):
    points = []
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == "spreads":
                for o in mkt["outcomes"]:
                    if o["name"] == team:
                        points.append(o.get("point", 0))
    return sum(points) / len(points) if points else 0

def get_totals_data(bookmakers):
    """Get over/under line and pick direction from bookmaker consensus."""
    lines = []
    over_favored = 0
    under_favored = 0
    total_books = 0
    
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == "totals":
                for o in mkt["outcomes"]:
                    if o["name"] == "Over":
                        lines.append(o.get("point", 0))
                        total_books += 1
                        if o.get("price", -110) < -110:
                            over_favored += 1
                        elif o.get("price", -110) > -110:
                            under_favored += 1
    
    if not lines:
        return None
    
    avg_line = sum(lines) / len(lines)
    
    if over_favored > under_favored:
        pick = "OVER"
        agreement = over_favored / total_books if total_books else 0.5
    elif under_favored > over_favored:
        pick = "UNDER"
        agreement = under_favored / total_books if total_books else 0.5
    else:
        pick = "OVER"  # default to over on ties
        agreement = 0.5
    
    # Confidence: base 52% + up to 18% based on book agreement
    confidence = 0.52 + (agreement * 0.18)
    
    return {"line": round(avg_line, 1), "pick": pick, "confidence": round(confidence, 4), "agreement": round(agreement, 3)}

def build_spread_games(odds_data, sport):
    """Build spread/ML analyzed games from odds data."""
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])
        
        home_h2h = avg_odds(bm, "h2h", home)
        away_h2h = avg_odds(bm, "h2h", away)
        if not home_h2h or not away_h2h:
            continue
        
        raw_home = 1 / home_h2h
        raw_away = 1 / away_h2h
        total = raw_home + raw_away
        home_prob = raw_home / total
        away_prob = raw_away / total
        
        spread = avg_spread(bm, home)
        
        if home_prob >= away_prob:
            pick = home
            win_prob = home_prob
        else:
            pick = away
            win_prob = away_prob
        
        # Upset detection for NBA
        pick_label = "FAVORITE"
        if sport == "NBA" and pick in TANK_TEAMS and win_prob < 0.55:
            pick_label = "UPSET"
        
        ct = g.get("commence_time", "")
        est_time = ""
        if ct:
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00")) - timedelta(hours=5)
            est_time = dt.strftime("%I:%M %p")
        
        games.append({
            "home": home,
            "away": away,
            "pick": pick,
            "win_prob": round(win_prob, 4),
            "spread": round(spread, 1),
            "pick_label": pick_label,
            "sport": sport,
            "type": "spread",
            "bet_type": "spread",
            "game_time": est_time,
            "commence_time": ct,
        })
    
    games.sort(key=lambda x: x.get("commence_time", ""))
    return games

def build_ou_games(odds_data, sport):
    """Build over/under analyzed games from odds data."""
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])
        
        td = get_totals_data(bm)
        if not td:
            continue
        
        ct = g.get("commence_time", "")
        est_time = ""
        if ct:
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00")) - timedelta(hours=5)
            est_time = dt.strftime("%I:%M %p")
        
        games.append({
            "home": home,
            "away": away,
            "pick": td["pick"],
            "win_prob": td["confidence"],
            "total_line": td["line"],
            "agreement": td["agreement"],
            "sport": sport,
            "type": "over_under",
            "bet_type": "over_under",
            "game_time": est_time,
            "commence_time": ct,
        })
    
    games.sort(key=lambda x: x.get("commence_time", ""))
    return games

def generate_all_parlays(games, product, max_legs=None):
    """Generate all unique parlay combos."""
    n = len(games)
    if max_legs is None:
        if n > 20: max_legs = 4
        elif n > 15: max_legs = 5
        else: max_legs = n
    
    result = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "product": product,
        "generated_at": datetime.now().isoformat(),
        "total_games": n,
        "games": games,
        "bets": {},
        "summary": {},
    }
    
    total = 0
    hc = 0
    
    for legs in range(1, min(max_legs + 1, n + 1)):
        tier = "single" if legs == 1 else f"{legs}leg"
        combos = list(itertools.combinations(range(n), legs))
        bets = []
        
        for ci, combo in enumerate(combos):
            picks = [games[i] for i in combo]
            prob = 1.0
            for p in picks:
                prob *= p["win_prob"]
            
            payout = round(100 / prob, 2) if prob > 0 else 0
            all_hc = all(p["win_prob"] >= 0.60 for p in picks)
            if all_hc: hc += 1
            
            bets.append({
                "bet_id": f"{product}_{tier}_{ci+1:05d}",
                "legs": legs,
                "game_indices": list(combo),
                "picks": [{
                    "home": p["home"], "away": p["away"], "pick": p["pick"],
                    "win_prob": round(p["win_prob"], 4),
                    "sport": p.get("sport", "?"), "type": p.get("type", "spread"),
                    "total_line": p.get("total_line"), "spread": p.get("spread"),
                    "game_time": p.get("game_time", ""),
                } for p in picks],
                "combined_prob": round(prob, 6),
                "implied_payout_per_100": payout,
                "all_high_confidence": all_hc,
                "result": None,
            })
        
        bets.sort(key=lambda x: x["combined_prob"], reverse=True)
        result["bets"][tier] = bets
        total += len(bets)
        if bets:
            best = bets[0]["combined_prob"]
            print(f"    {tier}: {len(bets)} parlays (best prob: {best:.4f})")
    
    result["summary"] = {
        "total_bets": total,
        "by_tier": {k: len(v) for k, v in result["bets"].items()},
        "high_confidence_bets": hc,
    }
    return result

def save(data, filename):
    path = os.path.join(DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    size = os.path.getsize(path) / 1024
    print(f"    -> {filename} ({size:.0f} KB)")

def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    print("=" * 60)
    print(f"TONIGHT-ONLY PARLAY BATCH - {today}")
    print(f"Cutoff: only games starting after {CUTOFF.strftime('%H:%M UTC')}")
    print("=" * 60)
    
    # Fetch odds (2 API calls total)
    print("\nFetching odds...")
    nba_odds = fetch_odds("basketball_nba")
    ncaab_odds = fetch_odds("basketball_ncaab")
    
    # Build game arrays
    print("\nBuilding picks...")
    nba_spread = build_spread_games(nba_odds, "NBA")
    nba_ou = build_ou_games(nba_odds, "NBA")
    ncaab_spread = build_spread_games(ncaab_odds, "NCAAB")
    ncaab_ou = build_ou_games(ncaab_odds, "NCAAB")
    
    print(f"\n  NBA Spread: {len(nba_spread)} games")
    print(f"  NBA O/U:    {len(nba_ou)} games")
    print(f"  NCAAB Spread: {len(ncaab_spread)} games")
    print(f"  NCAAB O/U:    {len(ncaab_ou)} games")
    
    # Print the actual games
    print("\n--- NBA SPREAD PICKS ---")
    for g in nba_spread:
        print(f"  {g['game_time']} {g['away']} @ {g['home']} -> {g['pick']} ({g['win_prob']:.0%}, spread {g['spread']:+.1f})")
    
    print("\n--- NBA O/U PICKS ---")
    for g in nba_ou:
        print(f"  {g['game_time']} {g['away']} @ {g['home']} -> {g['pick']} {g['total_line']} ({g['win_prob']:.0%})")
    
    print("\n--- NCAAB SPREAD PICKS ---")
    for g in ncaab_spread:
        print(f"  {g['game_time']} {g['away']} @ {g['home']} -> {g['pick']} ({g['win_prob']:.0%})")
    
    print("\n--- NCAAB O/U PICKS ---")
    for g in ncaab_ou:
        print(f"  {g['game_time']} {g['away']} @ {g['home']} -> {g['pick']} {g['total_line']} ({g['win_prob']:.0%})")
    
    # Generate all products
    products = {}
    
    print("\n" + "=" * 60)
    print("GENERATING PARLAYS")
    print("=" * 60)
    
    # 1. NBA Spread
    if nba_spread:
        print(f"\n1. NBA Spread ({len(nba_spread)} games)")
        d = generate_all_parlays(nba_spread, "nba_spread_tonight")
        save(d, f"tonight_nba_spread_{today}.json")
        products["NBA Spread"] = d["summary"]["total_bets"]
    
    # 2. NBA O/U
    if nba_ou:
        print(f"\n2. NBA O/U ({len(nba_ou)} games)")
        d = generate_all_parlays(nba_ou, "nba_ou_tonight")
        save(d, f"tonight_nba_ou_{today}.json")
        products["NBA O/U"] = d["summary"]["total_bets"]
    
    # 3. NCAAB Spread
    if ncaab_spread:
        print(f"\n3. NCAAB Spread ({len(ncaab_spread)} games)")
        d = generate_all_parlays(ncaab_spread, "ncaab_spread_tonight")
        save(d, f"tonight_ncaab_spread_{today}.json")
        products["NCAAB Spread"] = d["summary"]["total_bets"]
    
    # 4. NCAAB O/U
    if ncaab_ou:
        print(f"\n4. NCAAB O/U ({len(ncaab_ou)} games)")
        d = generate_all_parlays(ncaab_ou, "ncaab_ou_tonight")
        save(d, f"tonight_ncaab_ou_{today}.json")
        products["NCAAB O/U"] = d["summary"]["total_bets"]
    
    # 5. NBA Mixed (spread + O/U)
    if nba_spread and nba_ou:
        pool = nba_spread + nba_ou
        print(f"\n5. NBA Mixed - Spread + O/U ({len(pool)} legs)")
        d = generate_all_parlays(pool, "nba_mixed_tonight", max_legs=8)
        save(d, f"tonight_nba_mixed_{today}.json")
        products["NBA Mixed"] = d["summary"]["total_bets"]
    
    # 6. NCAAB Mixed (spread + O/U)
    if ncaab_spread and ncaab_ou:
        pool = ncaab_spread + ncaab_ou
        print(f"\n6. NCAAB Mixed - Spread + O/U ({len(pool)} legs)")
        d = generate_all_parlays(pool, "ncaab_mixed_tonight", max_legs=4)
        save(d, f"tonight_ncaab_mixed_{today}.json")
        products["NCAAB Mixed"] = d["summary"]["total_bets"]
    
    # 7. Cross-Sport (NBA + NCAAB spreads)
    if nba_spread and ncaab_spread:
        pool = nba_spread + ncaab_spread
        print(f"\n7. Cross-Sport Spreads ({len(pool)} legs)")
        d = generate_all_parlays(pool, "cross_sport_tonight", max_legs=5)
        save(d, f"tonight_cross_sport_{today}.json")
        products["Cross-Sport"] = d["summary"]["total_bets"]
    
    # 8. Ultimate Mixed
    if nba_spread and nba_ou and ncaab_spread and ncaab_ou:
        pool = nba_spread + nba_ou + ncaab_spread + ncaab_ou
        print(f"\n8. Ultimate Mixed ({len(pool)} legs)")
        d = generate_all_parlays(pool, "ultimate_tonight", max_legs=4)
        save(d, f"tonight_ultimate_mixed_{today}.json")
        products["Ultimate Mixed"] = d["summary"]["total_bets"]
    
    # Grand summary
    print("\n" + "=" * 60)
    print("TONIGHT'S REAL NUMBERS")
    print("=" * 60)
    grand = 0
    for name, count in products.items():
        print(f"  {name:<25} {count:>10,} parlays")
        grand += count
    print("-" * 60)
    print(f"  {'TOTAL':<25} {grand:>10,} parlays")
    
    # Revenue sim
    avg_price = 7.50
    print(f"\n  At avg ${avg_price}/parlay:")
    print(f"  If every parlay sold once: ${grand * avg_price:>12,.0f}")
    print(f"  100 customers x 5 each:   ${500 * avg_price:>12,.0f}")
    print(f"  1000 customers x 10 each: ${10000 * avg_price:>12,.0f}")
    print("=" * 60)

if __name__ == "__main__":
    main()
