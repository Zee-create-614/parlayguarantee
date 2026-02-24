"""
CLOSING LINES SNAPSHOT — Run at 6:45 PM EST (right before tipoff)
Re-fetches all odds, re-runs upset composite, generates all parlays.
Saves everything with _closing_ tag for comparison against opening snapshot.

Compare:
  1. Opening lines (3 PM) vs Closing lines (6:45 PM) — line movement
  2. Pure model vs Upset composite — which approach wins
  3. Opening picks vs Closing picks — did picks change with line movement
"""
import sys, json, itertools, requests, os, math
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

# Tank teams for NBA
TANK_TEAMS = {"Washington Wizards", "Charlotte Hornets", "Brooklyn Nets", "Portland Trail Blazers", "Utah Jazz"}
TANK_THRESHOLD = 0.35

# ── Upset composite weights (same as analyzer.py) ──
UPSET_WEIGHTS = {
    'h2h': 0.12, 'momentum': 0.10, 'clutch': 0.06, 'streak': 0.07,
    'three_pt_matchup': 0.08, 'post_asb': 0.04, 'home_record': 0.08, 'star_matchup': 0.10
}

def fetch_odds(sport):
    """Fetch fresh odds from Odds API."""
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
        params={"apiKey": API_KEY, "regions": "us", "markets": "h2h,spreads,totals", "dateFormat": "iso"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    remaining = r.headers.get("x-requests-remaining", "?")
    tonight = [g for g in data 
               if UTC_START <= datetime.fromisoformat(g["commence_time"].replace("Z","+00:00")) <= UTC_END]
    print(f"  {sport}: {len(tonight)} evening games (API calls remaining: {remaining})")
    return tonight

def avg_ml(bookmakers, team):
    """Average moneyline price across books."""
    prices = []
    for bm in bookmakers:
        for m in bm.get("markets", []):
            if m["key"] == "h2h":
                for o in m["outcomes"]:
                    if o["name"] == team:
                        prices.append(o["price"])
    return sum(prices) / len(prices) if prices else None

def avg_spread(bookmakers, team):
    """Average spread across books."""
    pts = []
    for bm in bookmakers:
        for m in bm.get("markets", []):
            if m["key"] == "spreads":
                for o in m["outcomes"]:
                    if o["name"] == team:
                        pts.append(o.get("point", 0))
    return round(sum(pts) / len(pts), 1) if pts else None

def get_ou(bookmakers):
    """Over/under data from books."""
    lines, over_prices, under_prices = [], [], []
    for bm in bookmakers:
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
    return {
        "line": round(sum(lines) / len(lines), 1),
        "over_price": round(sum(over_prices) / len(over_prices)) if over_prices else -110,
        "under_price": round(sum(under_prices) / len(under_prices)) if under_prices else -110,
        "book_count": len(lines)
    }

def ml_to_implied(ml):
    """American moneyline to implied probability."""
    if ml is None:
        return 0.5
    if ml > 0:
        return 100 / (ml + 100)
    else:
        return abs(ml) / (abs(ml) + 100)

def compute_upset_score(home_team, away_team, home_prob, away_prob, spread, home_is_fav):
    """
    Compute upset composite score. Same logic as analyzer.py.
    Returns (score, reasons, should_flip).
    """
    score = 0.0
    reasons = []
    
    # Tight spread (abs <= 5)
    if abs(spread) <= 5.0:
        score += 0.30
        reasons.append(f"Tight spread ({spread:+.1f})")
    
    # Home underdog
    if not home_is_fav and spread > 0:
        score += 0.40
        reasons.append("Home underdog")
    
    # Model disagrees with market (model margin < 10%)
    model_margin = abs(home_prob - away_prob)
    if model_margin < 0.10:
        score += 0.40
        reasons.append("Model likes road dog" if away_prob > home_prob else "Model likes underdog")
    elif model_margin < 0.20:
        score += 0.20
        reasons.append("Model margin thin")
    
    # Base factors (approximated without detailed stats — using defaults)
    score += 0.06  # h2h default
    score += 0.03  # momentum default
    score += 0.024  # home_record default
    score += 0.03  # star_matchup default
    score += 0.03  # streak default
    score += 0.03  # clutch default
    score += 0.04  # three_pt_matchup default
    score += 0.032  # post_asb default
    
    # Tank bowl check
    is_tank = home_team in TANK_TEAMS and away_team in TANK_TEAMS
    
    # Flip threshold: ~0.85+ with tight spread or home dog
    should_flip = score >= 0.85 and (abs(spread) <= 5.0 or (not home_is_fav and spread > 0))
    
    return round(score, 3), reasons, should_flip, is_tank

def build_nba_games(odds_data):
    """Build NBA game analysis from fresh odds."""
    games_pure = []
    games_upset = []
    
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bms = g.get("bookmakers", [])
        
        home_ml = avg_ml(bms, home)
        away_ml = avg_ml(bms, away)
        spread = avg_spread(bms, home)
        ou = get_ou(bms)
        
        if home_ml is None or away_ml is None:
            continue
        
        # Implied probabilities from moneyline
        home_imp = ml_to_implied(home_ml)
        away_imp = ml_to_implied(away_ml)
        # Normalize (remove vig)
        total_imp = home_imp + away_imp
        home_prob = home_imp / total_imp
        away_prob = away_imp / total_imp
        
        home_is_fav = home_prob > away_prob
        pick_pure = home if home_prob >= away_prob else away
        prob_pure = max(home_prob, away_prob)
        
        ct = g.get("commence_time", "")
        dt = datetime.fromisoformat(ct.replace("Z", "+00:00")) - timedelta(hours=5)
        time_str = dt.strftime("%I:%M %p")
        
        # Pure model game
        game_pure = {
            "home": home, "away": away,
            "pick": pick_pure, "win_prob": round(prob_pure, 4),
            "spread": spread if spread else 0,
            "sport": "NBA", "time": time_str,
            "home_ml": round(home_ml) if home_ml else None,
            "away_ml": round(away_ml) if away_ml else None,
            "upset_flip": False,
            "game_id": g.get("id", ""),
        }
        if ou:
            game_pure["ou_line"] = ou["line"]
            game_pure["ou_over_price"] = ou["over_price"]
            game_pure["ou_under_price"] = ou["under_price"]
        
        games_pure.append(game_pure)
        
        # Upset composite
        upset_score, reasons, should_flip, is_tank = compute_upset_score(
            home, away, home_prob, away_prob, spread if spread else 0, home_is_fav
        )
        
        game_upset = deepcopy(game_pure)
        game_upset["upset_score"] = upset_score
        game_upset["upset_reasons"] = reasons
        game_upset["tank_bowl"] = is_tank
        
        if should_flip:
            game_upset["upset_flip"] = True
            game_upset["original_pick"] = pick_pure
            game_upset["original_prob"] = round(prob_pure, 4)
            # Flip to the other team
            if pick_pure == home:
                game_upset["pick"] = away
                game_upset["win_prob"] = round(away_prob, 4)
            else:
                game_upset["pick"] = home
                game_upset["win_prob"] = round(home_prob, 4)
        
        games_upset.append(game_upset)
    
    games_pure.sort(key=lambda x: x["win_prob"], reverse=True)
    games_upset.sort(key=lambda x: x["win_prob"], reverse=True)
    
    return games_pure, games_upset

def build_ncaab_games(odds_data):
    """Build NCAAB game analysis from fresh odds."""
    games = []
    flips = 0
    
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bms = g.get("bookmakers", [])
        
        home_ml = avg_ml(bms, home)
        away_ml = avg_ml(bms, away)
        spread = avg_spread(bms, home)
        ou = get_ou(bms)
        
        if home_ml is None or away_ml is None:
            continue
        
        home_imp = ml_to_implied(home_ml)
        away_imp = ml_to_implied(away_ml)
        total_imp = home_imp + away_imp
        home_prob = home_imp / total_imp
        away_prob = away_imp / total_imp
        
        home_is_fav = home_prob > away_prob
        pick = home if home_prob >= away_prob else away
        prob = max(home_prob, away_prob)
        
        ct = g.get("commence_time", "")
        dt = datetime.fromisoformat(ct.replace("Z", "+00:00")) - timedelta(hours=5)
        
        game = {
            "home": home, "away": away,
            "pick": pick, "win_prob": round(prob, 4),
            "spread": spread if spread else 0,
            "sport": "NCAAB", "time": dt.strftime("%I:%M %p"),
            "home_ml": round(home_ml) if home_ml else None,
            "away_ml": round(away_ml) if away_ml else None,
            "upset_flip": False,
            "game_id": g.get("id", ""),
        }
        if ou:
            game["ou_line"] = ou["line"]
            game["ou_over_price"] = ou["over_price"]
            game["ou_under_price"] = ou["under_price"]
        
        # Light upset check for NCAAB
        if abs(spread if spread else 99) <= 5.0 and not home_is_fav and spread and spread > 0:
            game["upset_flag"] = True
            game["upset_note"] = f"Home dog {home} +{spread}, close game"
        
        games.append(game)
    
    games.sort(key=lambda x: x["win_prob"], reverse=True)
    return games

def gen_parlays(games, product, max_legs=None):
    n = len(games)
    if n == 0:
        return {"date": DATE, "product": product, "total_games": 0, "games": games, "bets": {}, "summary": {"total_bets": 0, "high_conf": 0}}
    
    if max_legs is None:
        max_legs = min(n, 9)
    if n > 20: max_legs = min(max_legs, 4)
    elif n > 15: max_legs = min(max_legs, 5)
    
    out = {"date": DATE, "product": product, "total_games": n, "games": games, "bets": {}, "summary": {}}
    total = hc = 0
    
    for legs in range(2, min(max_legs + 1, n + 1)):
        tier = f"{legs}leg"
        bets = []
        for ci, combo in enumerate(itertools.combinations(range(n), legs)):
            picks = [games[i] for i in combo]
            prob = 1.0
            for p in picks:
                prob *= p["win_prob"]
            payout = round(100 / prob, 2) if prob > 0 else 0
            ahc = all(p["win_prob"] >= 0.60 for p in picks)
            if ahc: hc += 1
            bets.append({
                "bet_id": f"{product}_{tier}_{ci+1:04d}",
                "legs": legs,
                "picks": [{
                    "home": p["home"], "away": p["away"], "pick": p["pick"],
                    "win_prob": p["win_prob"], "sport": p.get("sport"),
                    "spread": p.get("spread"), "upset_flip": p.get("upset_flip", False),
                    "ou_line": p.get("ou_line"), "time": p.get("time", "")
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

def load_opening():
    """Load opening snapshot for line movement comparison."""
    opening = {}
    try:
        with open(os.path.join(DIR, "analyzed_games.json")) as f:
            for g in json.load(f):
                key = f"{g['away'][:3]}@{g['home'][:3]}"
                opening[key] = {
                    "spread": g["spread"],
                    "pick": g["pick"],
                    "win_prob": g["win_prob"],
                    "upset_score": g.get("upset_score", 0),
                    "upset_flip": g.get("upset_flip", False)
                }
    except:
        pass
    return opening

def main():
    timestamp = datetime.now().strftime("%I:%M %p EST")
    print("=" * 70)
    print(f"CLOSING LINES SNAPSHOT — {timestamp}")
    print("=" * 70)
    
    # ── Fetch fresh odds ──
    print("\nFetching fresh odds...")
    nba_odds = fetch_odds("basketball_nba")
    ncaab_odds = fetch_odds("basketball_ncaab")
    
    # ── Build NBA games ──
    nba_pure, nba_upset = build_nba_games(nba_odds)
    print(f"\nNBA: {len(nba_pure)} games")
    
    # ── Load opening snapshot for comparison ──
    opening = load_opening()
    
    # ── Print NBA comparison ──
    print("\n--- NBA CLOSING LINES: PURE MODEL ---")
    print(f"{'#':<3} {'Game':<22} {'Pick':<18} {'Win%':<7} {'Spread':<8} {'ML':<12} {'60%+'}")
    print("-" * 80)
    for i, g in enumerate(nba_pure, 1):
        m = f"{g['away'][:3].upper()} @ {g['home'][:3].upper()}"
        pk = g['pick'].split()[-1]
        ml = f"{g.get('home_ml','')}/{g.get('away_ml','')}"
        marker = "YES" if g["win_prob"] >= 0.60 else ""
        print(f"{i:<3} {m:<22} {pk:<18} {g['win_prob']:.1%}  {g['spread']:+.1f}   {ml:<12} {marker}")
    
    print("\n--- NBA CLOSING LINES: UPSET-ADJUSTED ---")
    print(f"{'#':<3} {'Game':<22} {'Pick':<18} {'Win%':<7} {'Spread':<8} {'Upset':<7} {'Flip?':<6} {'60%+'}")
    print("-" * 85)
    for i, g in enumerate(nba_upset, 1):
        m = f"{g['away'][:3].upper()} @ {g['home'][:3].upper()}"
        pk = g['pick'].split()[-1]
        flip = "FLIP" if g.get("upset_flip") else ""
        marker = "YES" if g["win_prob"] >= 0.60 else ""
        print(f"{i:<3} {m:<22} {pk:<18} {g['win_prob']:.1%}  {g['spread']:+.1f}   {g.get('upset_score',0):.3f}  {flip:<6} {marker}")
    
    # ── Line Movement ──
    if opening:
        print("\n--- LINE MOVEMENT (Opening -> Closing) ---")
        print(f"{'Game':<22} {'Open Spread':<14} {'Close Spread':<14} {'Move':<8} {'Pick Changed?'}")
        print("-" * 75)
        for g in nba_pure:
            key = f"{g['away'][:3]}@{g['home'][:3]}"
            if key in opening:
                o = opening[key]
                spread_move = g["spread"] - o["spread"]
                pick_changed = g["pick"].split()[-1] != o["pick"].split()[-1]
                print(f"{key:<22} {o['spread']:+.1f}{'':>8} {g['spread']:+.1f}{'':>8} {spread_move:+.1f}{'':>4} {'YES!' if pick_changed else 'no'}")
    
    # ── O/U snapshot ──
    print("\n--- OVER/UNDERS (Closing) ---")
    print(f"{'Game':<22} {'Total':<8} {'Over':<8} {'Under':<8}")
    print("-" * 50)
    for g in nba_pure:
        m = f"{g['away'][:3].upper()} @ {g['home'][:3].upper()}"
        if "ou_line" in g:
            print(f"{m:<22} {g['ou_line']:<8} {g.get('ou_over_price',''):<8} {g.get('ou_under_price',''):<8}")
    
    # ── NCAAB ──
    ncaab_games = build_ncaab_games(ncaab_odds)
    print(f"\nNCAAB: {len(ncaab_games)} games")
    ncaab_upsets = [g for g in ncaab_games if g.get("upset_flag")]
    if ncaab_upsets:
        print("\n--- NCAAB UPSET FLAGS ---")
        for g in ncaab_upsets:
            m = f"{g['away'][:20]} @ {g['home'][:20]}"
            print(f"  {m} -> {g.get('upset_note','')}")
    
    # ── Generate all parlays ──
    print("\n" + "=" * 70)
    print("GENERATING CLOSING PARLAYS")
    print("=" * 70)
    
    print("\n1. NBA PURE MODEL (closing)")
    d = gen_parlays(nba_pure, "closing_nba_pure")
    save(d, f"closing_nba_pure_{DATE}.json")
    
    print("\n2. NBA UPSET-ADJUSTED (closing)")
    d = gen_parlays(nba_upset, "closing_nba_upset")
    save(d, f"closing_nba_upset_{DATE}.json")
    
    print("\n3. NCAAB (closing)")
    d = gen_parlays(ncaab_games, "closing_ncaab")
    save(d, f"closing_ncaab_{DATE}.json")
    
    print("\n4. MIXED NBA UPSET + NCAAB (closing)")
    mixed = nba_upset + ncaab_games
    mixed.sort(key=lambda x: x["win_prob"], reverse=True)
    d = gen_parlays(mixed, "closing_mixed", max_legs=5)
    save(d, f"closing_mixed_{DATE}.json")
    
    # ── Save raw snapshot for scoring ──
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot_type": "closing",
        "nba_pure": nba_pure,
        "nba_upset": nba_upset,
        "ncaab": ncaab_games,
        "line_movement": {}
    }
    if opening:
        for g in nba_pure:
            key = f"{g['away'][:3]}@{g['home'][:3]}"
            if key in opening:
                snapshot["line_movement"][key] = {
                    "open_spread": opening[key]["spread"],
                    "close_spread": g["spread"],
                    "open_pick": opening[key]["pick"],
                    "close_pick": g["pick"],
                    "open_upset_score": opening[key].get("upset_score", 0),
                }
    
    snap_path = os.path.join(DIR, f"snapshot_closing_{DATE}.json")
    json.dump(snapshot, open(snap_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n  Raw snapshot saved: snapshot_closing_{DATE}.json")
    
    # Also save opening snapshot if not already saved
    open_snap_path = os.path.join(DIR, f"snapshot_opening_{DATE}.json")
    if not os.path.exists(open_snap_path) and opening:
        open_snap = {
            "timestamp": "2026-02-20T20:00:00+00:00",
            "snapshot_type": "opening",
            "games": opening
        }
        json.dump(open_snap, open(open_snap_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"  Opening snapshot saved: snapshot_opening_{DATE}.json")
    
    # ── Summary ──
    print("\n" + "=" * 70)
    print("ALL FILES FOR COMPARISON:")
    print("=" * 70)
    all_files = [
        ("OPENING (3 PM)", f"comparison_nba_pure_{DATE}.json"),
        ("OPENING (3 PM)", f"comparison_nba_upset_{DATE}.json"),
        ("OPENING (3 PM)", f"comparison_ncaab_standard_{DATE}.json"),
        ("OPENING (3 PM)", f"comparison_mixed_upset_{DATE}.json"),
        ("CLOSING (6:45 PM)", f"closing_nba_pure_{DATE}.json"),
        ("CLOSING (6:45 PM)", f"closing_nba_upset_{DATE}.json"),
        ("CLOSING (6:45 PM)", f"closing_ncaab_{DATE}.json"),
        ("CLOSING (6:45 PM)", f"closing_mixed_{DATE}.json"),
    ]
    for label, fn in all_files:
        fp = os.path.join(DIR, fn)
        if os.path.exists(fp):
            sz = os.path.getsize(fp)
            print(f"  [{label}] {fn} ({sz/1024:.0f} KB)")
    
    nba_flips_closing = sum(1 for g in nba_upset if g.get("upset_flip"))
    print(f"\n  NBA closing flips: {nba_flips_closing}")
    print(f"  NBA pure 60%+: {sum(1 for g in nba_pure if g['win_prob'] >= 0.60)}")
    print(f"  NBA upset 60%+: {sum(1 for g in nba_upset if g['win_prob'] >= 0.60)}")
    print(f"  NCAAB games: {len(ncaab_games)}")
    print(f"  NCAAB upset flags: {len(ncaab_upsets)}")
    print("\n  TOMORROW: Score all 8 files against actual results!")
    print("  Compare: opening vs closing, pure vs upset, NBA vs NCAAB vs mixed")

if __name__ == "__main__":
    main()
