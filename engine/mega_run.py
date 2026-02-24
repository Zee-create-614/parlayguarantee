#!/usr/bin/env python3
"""
Mega Pick Generator — Production
Generates 13 datasets from Odds API data (DraftKings, FanDuel, BetMGM only).
"""

import json, os, sys, requests, time, argparse
from datetime import datetime, timezone
from itertools import combinations
from math import comb

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE = "https://api.the-odds-api.com/v4"
ALLOWED_BOOKS = {"draftkings", "fanduel", "betmgm"}

_parser = argparse.ArgumentParser()
_parser.add_argument("--tag", default=None, help="Time tag like 11am, 1pm")
_parser.add_argument("--books", default="draftkings,fanduel,betmgm",
                     help="Comma-separated bookmaker keys to use")
_args = _parser.parse_args()

# Parse books argument
ACTIVE_BOOKS = set(b.strip().lower() for b in _args.books.split(","))

TODAY = datetime.now().strftime('%Y-%m-%d')
if _args.tag:
    OUT_DIR = os.path.join(os.path.dirname(__file__), f"picks_{TODAY}_{_args.tag}")
else:
    OUT_DIR = os.path.join(os.path.dirname(__file__), f"picks_{TODAY}")
os.makedirs(OUT_DIR, exist_ok=True)

NOW = datetime.now(timezone.utc)
print(f"[{NOW.strftime('%H:%M:%S UTC')}] Starting mega run...")
print(f"  Books filter: {', '.join(sorted(ACTIVE_BOOKS))}")

# ─── helpers ──────────────────────────────────────────────────────────

def american_to_prob(odds):
    if odds is None:
        return 0.5
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def devig(p1, p2):
    total = p1 + p2
    if total == 0:
        return 0.5, 0.5
    return p1 / total, p2 / total

def prob_to_american(p):
    if p <= 0 or p >= 1:
        return 0
    if p >= 0.5:
        return round(-100 * p / (1 - p))
    else:
        return round(100 * (1 - p) / p)

def parlay_payout(probs):
    combined = 1.0
    for p in probs:
        if p <= 0 or p >= 1:
            return 0
        combined *= (1 / p)
    return round((combined - 1) * 100, 2)

# ─── fetch odds ───────────────────────────────────────────────────────

def fetch_odds(sport_key):
    url = f"{BASE}/sports/{sport_key}/odds"
    params = {
        'apiKey': API_KEY,
        'regions': 'us',
        'markets': 'h2h,spreads,totals',
        'oddsFormat': 'american',
        'dateFormat': 'iso',
        'bookmakers': ','.join(sorted(ACTIVE_BOOKS)),
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        print(f"  ERROR fetching {sport_key}: {r.status_code} {r.text[:200]}")
        return []
    data = r.json()
    future = []
    for g in data:
        ct = datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00'))
        if ct > NOW:
            # Only keep games that have at least one allowed bookmaker
            allowed_bms = [bm for bm in g.get("bookmakers", []) if bm["key"].lower() in ACTIVE_BOOKS]
            if allowed_bms:
                g["bookmakers"] = allowed_bms
                future.append(g)
    print(f"  {sport_key}: {len(future)} upcoming games with allowed books (filtered from {len(data)})")
    return future

print("Fetching NBA odds...")
nba_raw = fetch_odds("basketball_nba")
time.sleep(1)
print("Fetching NCAAB odds...")
ncaab_raw = fetch_odds("basketball_ncaab")

# ─── Dataset 1: Per-sportsbook lines ─────────────────────────────────

def build_sportsbook_lines(games):
    result = []
    for g in games:
        entry = {
            "home": g["home_team"],
            "away": g["away_team"],
            "commence_time": g["commence_time"],
            "sportsbooks": {}
        }
        for bm in g.get("bookmakers", []):
            if bm["key"].lower() not in ACTIVE_BOOKS:
                continue
            name = bm.get("title", bm["key"])
            book_data = {}
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if o["name"] == g["home_team"]:
                            book_data["ml_home"] = o["price"]
                        elif o["name"] == g["away_team"]:
                            book_data["ml_away"] = o["price"]
                elif mkt["key"] == "spreads":
                    for o in mkt["outcomes"]:
                        if o["name"] == g["home_team"]:
                            book_data["spread_home"] = o.get("point", 0)
                            book_data["spread_home_odds"] = o["price"]
                        elif o["name"] == g["away_team"]:
                            book_data["spread_away"] = o.get("point", 0)
                            book_data["spread_away_odds"] = o["price"]
                elif mkt["key"] == "totals":
                    for o in mkt["outcomes"]:
                        if o["name"] == "Over":
                            book_data["total"] = o.get("point", 0)
                            book_data["over_odds"] = o["price"]
                        elif o["name"] == "Under":
                            book_data["under_odds"] = o["price"]
            if book_data:
                entry["sportsbooks"][name] = book_data
        if entry["sportsbooks"]:
            result.append(entry)
    return result

print("\n[Dataset 1] Building per-sportsbook lines...")
ds1 = {
    "nba": build_sportsbook_lines(nba_raw),
    "ncaab": build_sportsbook_lines(ncaab_raw),
    "books_used": sorted(ACTIVE_BOOKS),
    "generated_at": NOW.isoformat()
}
with open(os.path.join(OUT_DIR, "per_sportsbook_lines.json"), "w") as f:
    json.dump(ds1, f, indent=2)
print(f"  Saved: {len(ds1['nba'])} NBA + {len(ds1['ncaab'])} NCAAB games")

# ─── Build consensus picks from odds ─────────────────────────────────

def extract_picks(games, sport_label):
    ml_spread_picks = []
    ou_picks = []

    for g in games:
        home = g["home_team"]
        away = g["away_team"]

        # Only use allowed bookmakers
        allowed_bms = [bm for bm in g.get("bookmakers", []) if bm["key"].lower() in ACTIVE_BOOKS]
        if not allowed_bms:
            continue

        books_used = sorted(set(bm["key"].lower() for bm in allowed_bms))

        ml_home_odds_list = []
        ml_away_odds_list = []
        spread_home_list = []
        spread_away_list = []
        total_list = []

        for bm in allowed_bms:
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if o["name"] == home:
                            ml_home_odds_list.append(o["price"])
                        elif o["name"] == away:
                            ml_away_odds_list.append(o["price"])
                elif mkt["key"] == "spreads":
                    for o in mkt["outcomes"]:
                        if o["name"] == home:
                            spread_home_list.append(o.get("point", 0))
                        elif o["name"] == away:
                            spread_away_list.append(o.get("point", 0))
                elif mkt["key"] == "totals":
                    for o in mkt["outcomes"]:
                        if o["name"] == "Over":
                            total_list.append(o.get("point", 0))

        if ml_home_odds_list and ml_away_odds_list:
            avg_ml_home = sum(ml_home_odds_list) / len(ml_home_odds_list)
            avg_ml_away = sum(ml_away_odds_list) / len(ml_away_odds_list)
            ph = american_to_prob(avg_ml_home)
            pa = american_to_prob(avg_ml_away)
            ph_dv, pa_dv = devig(ph, pa)
        else:
            avg_ml_home, avg_ml_away = -110, -110
            ph_dv, pa_dv = 0.5, 0.5

        avg_spread_home = sum(spread_home_list) / len(spread_home_list) if spread_home_list else 0
        avg_spread_away = sum(spread_away_list) / len(spread_away_list) if spread_away_list else 0
        avg_total = sum(total_list) / len(total_list) if total_list else 0

        if ph_dv >= pa_dv:
            ml_pick = home
            ml_side = "home"
            ml_prob = ph_dv
        else:
            ml_pick = away
            ml_side = "away"
            ml_prob = pa_dv

        if avg_spread_home < 0:
            spread_pick = home
            spread_side = "home"
            cover_prob = ph_dv * 0.85 + 0.08
        else:
            spread_pick = away
            spread_side = "away"
            cover_prob = pa_dv * 0.85 + 0.08

        # Upset composite: 0 in this engine (always picks market favorite).
        # Real upset detection lives in run_full_analysis.py
        upset_composite = 0

        game_pick = {
            "home": home,
            "away": away,
            "commence_time": g["commence_time"],
            "sport": sport_label,
            "ml_pick": ml_pick,
            "ml_side": ml_side,
            "ml_prob": round(ml_prob, 4),
            "ml_odds": prob_to_american(ml_prob),
            "spread_pick": spread_pick,
            "spread_side": spread_side,
            "spread_line": round(avg_spread_home, 1),  # home perspective
            "pick_spread": round(avg_spread_home if spread_side == "home" else -avg_spread_home, 1),  # from picked team's perspective
            "cover_prob": round(cover_prob, 4),
            "upset_composite": upset_composite,
            "consensus_ml_home": round(avg_ml_home),
            "consensus_ml_away": round(avg_ml_away),
            "books_used": books_used,
        }
        ml_spread_picks.append(game_pick)

        ou_pick = {
            "home": home,
            "away": away,
            "commence_time": g["commence_time"],
            "sport": sport_label,
            "total_line": round(avg_total, 1),
            "ou_pick": "Over" if avg_total > 0 else "N/A",
            "ou_prob": 0.52,
            "upset_composite": upset_composite,
            "books_used": books_used,
        }
        ou_picks.append(ou_pick)

    return ml_spread_picks, ou_picks

print("\n[Datasets 2-5] Generating picks from consensus odds...")
nba_ml_spread, nba_ou = extract_picks(nba_raw, "NBA")
ncaab_ml_spread, ncaab_ou = extract_picks(ncaab_raw, "NCAAB")

for name, data, ds_num in [
    ("nba_ml_spread.json", nba_ml_spread, 2),
    ("nba_ou.json", nba_ou, 3),
    ("ncaab_ml_spread.json", ncaab_ml_spread, 4),
    ("ncaab_ou.json", ncaab_ou, 5),
]:
    with open(os.path.join(OUT_DIR, name), "w") as f:
        json.dump({"picks": data, "count": len(data), "books_used": sorted(ACTIVE_BOOKS), "generated_at": NOW.isoformat()}, f, indent=2)
    print(f"  [Dataset {ds_num}] {name}: {len(data)} picks")

# ─── Parlay Generation ───────────────────────────────────────────────

def make_parlay_legs(picks, pick_type):
    legs = []
    for p in picks:
        if pick_type == "ml":
            legs.append({
                "game": f"{p['away']} @ {p['home']}",
                "pick": p["ml_pick"],
                "type": "ML",
                "odds": p["ml_odds"],
                "prob": p["ml_prob"],
                "commence_time": p["commence_time"],
            })
        elif pick_type == "spread":
            legs.append({
                "game": f"{p['away']} @ {p['home']}",
                "pick": f"{p['spread_pick']} {p['spread_line']}",
                "type": "Spread",
                "odds": -110,
                "prob": p["cover_prob"],
                "commence_time": p["commence_time"],
            })
        elif pick_type == "ou":
            if p.get("ou_pick", "N/A") == "N/A":
                continue
            legs.append({
                "game": f"{p['away']} @ {p['home']}",
                "pick": f"{p['ou_pick']} {p['total_line']}",
                "type": "O/U",
                "odds": -110,
                "prob": p["ou_prob"],
                "commence_time": p["commence_time"],
            })
    legs.sort(key=lambda x: x["prob"], reverse=True)
    return legs

def generate_parlays(legs, min_legs=2, max_legs=8):
    if len(legs) < min_legs:
        return {}, 0, {}
    result = {}
    total_saved = 0
    counts = {}
    actual_max = min(max_legs, len(legs))

    pool_limits = {2: min(len(legs), 80), 3: min(len(legs), 40), 4: 25, 5: 20, 6: 15, 7: 12, 8: 10}

    for size in range(min_legs, actual_max + 1):
        pool_size = min(pool_limits.get(size, 15), len(legs))
        pool = legs[:pool_size]

        if len(pool) < size:
            continue

        n_from_pool = comb(len(pool), size)
        n_from_all = comb(len(legs), size)
        counts[f"{size}_leg"] = {"from_pool": n_from_pool, "total_possible": n_from_all, "pool_size": pool_size}

        print(f"    {size}-leg: {n_from_pool:,} combos (top {pool_size} legs) | {n_from_all:,} total possible", flush=True)

        combos = []
        for combo in combinations(pool, size):
            probs = [l["prob"] for l in combo]
            combined = 1.0
            for p in probs:
                combined *= p
            combos.append({
                "legs": list(combo),
                "combined_prob": round(combined, 6),
                "payout_per_100": parlay_payout(probs),
                "leg_count": size,
            })

        combos.sort(key=lambda x: x["combined_prob"], reverse=True)
        result[f"{size}_leg"] = combos
        total_saved += len(combos)
        print(f"      -> {len(combos):,} saved", flush=True)

    return result, total_saved, counts

def save_parlays(filename, legs, ds_num, label):
    print(f"  [Dataset {ds_num}] {filename} ({label}, {len(legs)} legs)...")
    parlays, total_saved, counts = generate_parlays(legs)
    with open(os.path.join(OUT_DIR, filename), "w") as f:
        json.dump({
            "parlays": parlays,
            "total_saved": total_saved,
            "combos_per_size": counts,
            "books_used": sorted(ACTIVE_BOOKS),
            "generated_at": NOW.isoformat()
        }, f, indent=2)
    print(f"  -> {total_saved:,} parlays saved to file")

print("\n[Datasets 6-13] Generating parlays...")

nba_ml_legs = make_parlay_legs(nba_ml_spread, "ml")
nba_spread_legs = make_parlay_legs(nba_ml_spread, "spread")
nba_ms_legs = nba_ml_legs + nba_spread_legs
ncaab_ml_legs = make_parlay_legs(ncaab_ml_spread, "ml")
ncaab_spread_legs = make_parlay_legs(ncaab_ml_spread, "spread")
ncaab_ms_legs = ncaab_ml_legs + ncaab_spread_legs
nba_ou_legs = make_parlay_legs(nba_ou, "ou")
ncaab_ou_legs = make_parlay_legs(ncaab_ou, "ou")

for pool in [nba_ms_legs, ncaab_ms_legs, nba_ou_legs, ncaab_ou_legs]:
    pool.sort(key=lambda x: x["prob"], reverse=True)

save_parlays("parlays_nba_pure.json", nba_ms_legs, 6, "NBA ML+Spread")
save_parlays("parlays_ncaab_pure.json", ncaab_ms_legs, 7, "NCAAB ML+Spread")

mixed_ms = nba_ms_legs + ncaab_ms_legs
mixed_ms.sort(key=lambda x: x["prob"], reverse=True)
save_parlays("parlays_mixed_nba_ncaab.json", mixed_ms, 8, "Mixed ML+Spread")

save_parlays("parlays_nba_ou.json", nba_ou_legs, 9, "NBA O/U")
save_parlays("parlays_ncaab_ou.json", ncaab_ou_legs, 10, "NCAAB O/U")

mixed_ou = nba_ou_legs + ncaab_ou_legs
mixed_ou.sort(key=lambda x: x["prob"], reverse=True)
save_parlays("parlays_mixed_ou.json", mixed_ou, 11, "Mixed O/U")

mixed_spread_ou = nba_spread_legs + ncaab_spread_legs + nba_ou_legs + ncaab_ou_legs
mixed_spread_ou.sort(key=lambda x: x["prob"], reverse=True)
save_parlays("parlays_mixed_spread_ou.json", mixed_spread_ou, 12, "Mixed Spread+O/U")

mixed_ml_ou = nba_ml_legs + ncaab_ml_legs + nba_ou_legs + ncaab_ou_legs
mixed_ml_ou.sort(key=lambda x: x["prob"], reverse=True)
save_parlays("parlays_mixed_ml_ou.json", mixed_ml_ou, 13, "Mixed ML+O/U")

# ─── Summary ──────────────────────────────────────────────────────────

print("\n" + "="*60)
print("MEGA RUN COMPLETE — Summary")
print(f"Books: {', '.join(sorted(ACTIVE_BOOKS))}")
print("="*60)
files = sorted(os.listdir(OUT_DIR))
for fn in files:
    fp = os.path.join(OUT_DIR, fn)
    size = os.path.getsize(fp)
    with open(fp) as f:
        d = json.load(f)
    if "picks" in d:
        print(f"  {fn}: {d['count']} picks ({size:,} bytes)")
    elif "total_saved" in d:
        print(f"  {fn}: {d['total_saved']:,} parlays saved ({size:,} bytes)")
    elif "total_combos" in d:
        print(f"  {fn}: {d['total_combos']:,} parlays ({size:,} bytes)")
    elif "nba" in d:
        print(f"  {fn}: {len(d['nba'])} NBA + {len(d['ncaab'])} NCAAB games ({size:,} bytes)")
print(f"\nAll files saved to: {OUT_DIR}")
print(f"Finished at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
