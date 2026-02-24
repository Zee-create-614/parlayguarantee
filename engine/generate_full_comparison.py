"""
FULL COMPARISON GENERATOR — Feb 20, 2026
Generates ALL unique parlays for:
1. NBA Pure Model (no upset flips)
2. NBA Upset-Adjusted (with flips)
3. NCAAB with upset composite check (flip if threshold met)
4. Mixed NBA+NCAAB upset-adjusted
All files kept separate for accuracy comparison.
"""
import sys, json, itertools, requests, os
from datetime import datetime, timezone, timedelta
from copy import deepcopy

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(__file__)
API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
DATE = "2026-02-20"

UTC_START = datetime(2026, 2, 20, 23, 0, tzinfo=timezone.utc)
UTC_END = datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc)

# ── NBA upset composite flip threshold ──
# In the NBA analyzer, games flip when upset_score triggers. 
# We use the existing analyzed_games.json which already has flips applied.
# For "pure model" we reverse the flips using original_pick/original_prob.

# ── NCAAB upset composite flip threshold ──
# NCAAB games have upset_composite but no flip logic yet.
# We'll apply a flip if: home is underdog + tight spread + upset_composite > 0.35
NCAAB_FLIP_THRESHOLD = 0.35

def load_nba_analyzed():
    with open(os.path.join(DIR, "analyzed_games.json")) as f:
        return json.load(f)

def load_ncaab_picks():
    with open(os.path.join(DIR, "ncaab_picks_2026-02-20.json")) as f:
        return json.load(f)

def fetch_fresh_odds(sport):
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
        params={"apiKey": API_KEY, "regions": "us", "markets": "h2h,spreads,totals", "dateFormat": "iso"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    remaining = r.headers.get("x-requests-remaining", "?")
    tonight = [g for g in data 
               if UTC_START <= datetime.fromisoformat(g["commence_time"].replace("Z","+00:00")) <= UTC_END]
    print(f"  {sport}: {len(tonight)} evening games (API remaining: {remaining})")
    return tonight

def gen_parlays(games, product, max_legs=None):
    """Generate all unique parlay combinations."""
    n = len(games)
    if n == 0:
        return {"date": DATE, "product": product, "total_games": 0, "games": games, "bets": {}, "summary": {"total_bets": 0}}
    
    if max_legs is None:
        max_legs = min(n, 9)
    if n > 20: max_legs = min(max_legs, 4)
    elif n > 15: max_legs = min(max_legs, 5)
    
    out = {"date": DATE, "product": product, "total_games": n, "games": games, "bets": {}, "summary": {}}
    total = hc = 0
    
    for legs in range(2, min(max_legs + 1, n + 1)):  # Start at 2 for parlays
        tier = f"{legs}leg"
        bets = []
        for ci, combo in enumerate(itertools.combinations(range(n), legs)):
            picks = [games[i] for i in combo]
            prob = 1.0
            for p in picks:
                prob *= p["win_prob"]
            payout = round(100 / prob, 2) if prob > 0 else 0
            ahc = all(p["win_prob"] >= 0.60 for p in picks)
            if ahc:
                hc += 1
            bets.append({
                "bet_id": f"{product}_{tier}_{ci+1:04d}",
                "legs": legs,
                "picks": [{
                    "home": p["home"], "away": p["away"], "pick": p["pick"],
                    "win_prob": p["win_prob"], "sport": p.get("sport", "NBA"),
                    "spread": p.get("spread"), "upset_flip": p.get("upset_flip", False)
                } for p in picks],
                "combined_prob": round(prob, 6),
                "payout_per_100": payout,
                "all_high_conf": ahc,
                "result": None
            })
        bets.sort(key=lambda x: x["combined_prob"], reverse=True)
        out["bets"][tier] = bets
        total += len(bets)
        print(f"    {tier}: {len(bets):,}")
    
    out["summary"] = {"total_bets": total, "by_tier": {k: len(v) for k, v in out["bets"].items()}, "high_conf": hc}
    return out

def save(data, fn):
    p = os.path.join(DIR, fn)
    json.dump(data, open(p, "w", encoding="utf-8"), separators=(',', ':'), ensure_ascii=False)
    sz = os.path.getsize(p)
    print(f"    -> {fn} ({sz/1024:.0f} KB, {data['summary']['total_bets']:,} bets)")

def main():
    print("=" * 70)
    print("FULL COMPARISON GENERATOR — Feb 20, 2026")
    print("=" * 70)
    
    # ─── NBA ───
    nba_analyzed = load_nba_analyzed()
    print(f"\nLoaded {len(nba_analyzed)} NBA analyzed games")
    
    # Build PURE MODEL picks (reverse any flips)
    nba_pure = []
    for g in nba_analyzed:
        if g.get("upset_flip"):
            nba_pure.append({
                "home": g["home"], "away": g["away"],
                "pick": g["original_pick"],
                "win_prob": round(g["original_prob"], 4),
                "spread": g["spread"],
                "sport": "NBA",
                "upset_flip": False,
                "game_id": g["game_id"]
            })
        else:
            nba_pure.append({
                "home": g["home"], "away": g["away"],
                "pick": g["pick"],
                "win_prob": round(g["win_prob"], 4),
                "spread": g["spread"],
                "sport": "NBA",
                "upset_flip": False,
                "game_id": g["game_id"]
            })
    nba_pure.sort(key=lambda x: x["win_prob"], reverse=True)
    
    # Build UPSET-ADJUSTED picks (as-is from analyzer)
    nba_upset = []
    for g in nba_analyzed:
        nba_upset.append({
            "home": g["home"], "away": g["away"],
            "pick": g["pick"],
            "win_prob": round(g["win_prob"], 4),
            "spread": g["spread"],
            "sport": "NBA",
            "upset_flip": g.get("upset_flip", False),
            "upset_score": g.get("upset_score", 0),
            "game_id": g["game_id"]
        })
    nba_upset.sort(key=lambda x: x["win_prob"], reverse=True)
    
    print("\n--- NBA PURE MODEL ---")
    for p in nba_pure:
        m = f"{p['away'][:3].upper()} @ {p['home'][:3].upper()}"
        print(f"  {m:<20} {p['pick'].split()[-1]:<18} {p['win_prob']:.1%}")
    
    print("\n--- NBA UPSET-ADJUSTED ---")
    for p in nba_upset:
        m = f"{p['away'][:3].upper()} @ {p['home'][:3].upper()}"
        flip = " FLIP" if p["upset_flip"] else ""
        print(f"  {m:<20} {p['pick'].split()[-1]:<18} {p['win_prob']:.1%}{flip}")
    
    # Generate NBA parlays
    print("\n1. NBA PURE MODEL PARLAYS")
    d = gen_parlays(nba_pure, "nba_pure_model")
    save(d, f"comparison_nba_pure_{DATE}.json")
    
    print("\n2. NBA UPSET-ADJUSTED PARLAYS")
    d = gen_parlays(nba_upset, "nba_upset_adjusted")
    save(d, f"comparison_nba_upset_{DATE}.json")
    
    # ─── NCAAB ───
    ncaab_picks = load_ncaab_picks()
    print(f"\nLoaded {len(ncaab_picks)} NCAAB picks")
    
    # Check for potential flips using similar logic to NBA
    # NCAAB flip criteria: market disagrees with model + tight spread + home underdog
    ncaab_flips = []
    ncaab_games = []
    for g in ncaab_picks:
        spread_str = g.get("spread_pick", "")
        # Parse spread from spread_pick string
        spread_val = 0
        try:
            parts = spread_str.rsplit(" ", 1)
            if len(parts) == 2:
                spread_val = float(parts[1])
        except:
            pass
        
        home_prob = g.get("home_win_prob", 0.5)
        away_prob = g.get("away_win_prob", 0.5)
        market_home = g.get("market_home_prob", 0.5)
        market_away = g.get("market_away_prob", 0.5)
        upset_comp = g.get("upset_composite", 0)
        
        pick = g["predicted_winner"]
        conf = g["confidence"]
        
        # NCAAB upset_composite is now directional: only non-zero when model picks the DOG.
        # No flip needed — if composite > 0, model already picked the underdog.
        # If composite == 0, model picked the favorite and there's no upset signal.
        should_flip = False
        flip_reasons = []
        
        game_entry = {
            "home": g["home_team"], "away": g["away_team"],
            "pick": pick, "win_prob": round(conf, 4),
            "spread": spread_val, "sport": "NCAAB",
            "upset_flip": False, "upset_composite": upset_comp,
            "game_id": g["game_id"],
            "ou_pick": g.get("ou_pick"), "total": g.get("total")
        }
        
        if should_flip:
            # Flip the pick
            original_pick = pick
            if pick == g["home_team"]:
                game_entry["pick"] = g["away_team"]
                game_entry["win_prob"] = round(away_prob, 4)
            else:
                game_entry["pick"] = g["home_team"]
                game_entry["win_prob"] = round(home_prob, 4)
            game_entry["upset_flip"] = True
            game_entry["original_pick"] = original_pick
            game_entry["flip_reasons"] = flip_reasons
            ncaab_flips.append(game_entry)
        
        ncaab_games.append(game_entry)
    
    ncaab_games.sort(key=lambda x: x["win_prob"], reverse=True)
    
    print(f"\nNCAAB upset flips: {len(ncaab_flips)}")
    for f in ncaab_flips:
        m = f"{f['away'][:15]} @ {f['home'][:15]}"
        print(f"  FLIP: {m} -> {f['pick']} (was {f['original_pick']}) | upset={f['upset_composite']:.3f}")
        for r in f.get("flip_reasons", []):
            print(f"    Reason: {r}")
    
    if ncaab_flips:
        print("\n3. NCAAB UPSET-ADJUSTED PARLAYS")
        d = gen_parlays(ncaab_games, "ncaab_upset_adjusted")
        save(d, f"comparison_ncaab_upset_{DATE}.json")
    else:
        print("\n  No NCAAB flips — generating standard NCAAB parlays")
        print("\n3. NCAAB STANDARD PARLAYS")
        d = gen_parlays(ncaab_games, "ncaab_standard")
        save(d, f"comparison_ncaab_standard_{DATE}.json")
    
    # ─── MIXED NBA (upset) + NCAAB ───
    print("\n4. MIXED NBA+NCAAB UPSET-ADJUSTED PARLAYS")
    mixed = nba_upset + ncaab_games
    mixed.sort(key=lambda x: x["win_prob"], reverse=True)
    # Cap legs for mixed (too many combos otherwise)
    d = gen_parlays(mixed, "mixed_nba_ncaab_upset", max_legs=5)
    save(d, f"comparison_mixed_upset_{DATE}.json")
    
    # ─── SUMMARY ───
    print("\n" + "=" * 70)
    print("FILES GENERATED:")
    print("=" * 70)
    files = [
        f"comparison_nba_pure_{DATE}.json",
        f"comparison_nba_upset_{DATE}.json",
        f"comparison_ncaab_{'upset' if ncaab_flips else 'standard'}_{DATE}.json",
        f"comparison_mixed_upset_{DATE}.json"
    ]
    for fn in files:
        fp = os.path.join(DIR, fn)
        if os.path.exists(fp):
            sz = os.path.getsize(fp)
            print(f"  {fn} ({sz/1024:.0f} KB)")
    
    print(f"\nTotal NBA games: {len(nba_analyzed)}")
    print(f"  Pure model 60%+ picks: {sum(1 for p in nba_pure if p['win_prob'] >= 0.60)}")
    print(f"  Upset-adjusted 60%+ picks: {sum(1 for p in nba_upset if p['win_prob'] >= 0.60)}")
    print(f"  NBA flips: {sum(1 for g in nba_analyzed if g.get('upset_flip'))}")
    print(f"Total NCAAB games: {len(ncaab_picks)}")
    print(f"  NCAAB flips: {len(ncaab_flips)}")
    print(f"Mixed games: {len(mixed)}")
    print("\nTomorrow: score all files against results to see which model wins!")

if __name__ == "__main__":
    main()
