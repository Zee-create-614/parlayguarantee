#!/usr/bin/env python3
"""
Daily Mega Pick Generator — Time-Window Aware
Generates parlays grouped by time window so every parlay is actually
placeable on DraftKings (no mixing started + unstarted games).

Usage:
  python daily_mega_run.py                    # auto-detect date, default 3pm ET publish
  python daily_mega_run.py --tag 3pm          # custom tag for output dir
  python daily_mega_run.py --publish-hour 15  # custom publish hour (ET)
"""

import json, os, sys, requests, time, argparse
from datetime import datetime, timezone, timedelta, date
from itertools import combinations
from math import comb

# Local import
from time_windows import (
    filter_and_group_games, group_legs_by_window, window_label,
    validate_parlay_timing, BUFFER_MINUTES, EST
)

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE = "https://api.the-odds-api.com/v4"

parser = argparse.ArgumentParser()
parser.add_argument("--tag", default=None, help="Time tag like 11am, 3pm")
parser.add_argument("--publish-hour", type=int, default=15, help="Publish hour in ET (24h)")
args = parser.parse_args()

TODAY = date.today().isoformat()
NOW = datetime.now(timezone.utc)

# Publication time in UTC
PUBLISH_ET = datetime.now(EST).replace(hour=args.publish_hour, minute=0, second=0, microsecond=0)
PUBLISH_UTC = PUBLISH_ET.astimezone(timezone.utc)

tag = args.tag or f"{args.publish_hour}h"
OUT_DIR = os.path.join(os.path.dirname(__file__), f"picks_{TODAY}_{tag}")
os.makedirs(OUT_DIR, exist_ok=True)

print(f"[{NOW.strftime('%H:%M:%S UTC')}] Daily Mega Run — Time-Window Aware")
print(f"  Date: {TODAY}")
print(f"  Publish time: {PUBLISH_ET.strftime('%I:%M %p ET')} ({PUBLISH_UTC.strftime('%H:%M UTC')})")
print(f"  Buffer: {BUFFER_MINUTES} min (games must start after {(PUBLISH_UTC + timedelta(minutes=BUFFER_MINUTES)).strftime('%H:%M UTC')})")
print(f"  Output: {OUT_DIR}\n")

# ─── helpers ──────────────────────────────────────────────────────────

def american_to_prob(odds):
    if odds is None: return 0.5
    if odds > 0: return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)

def devig(p1, p2):
    total = p1 + p2
    if total == 0: return 0.5, 0.5
    return p1 / total, p2 / total

def prob_to_american(p):
    if p <= 0 or p >= 1: return 0
    if p >= 0.5: return round(-100 * p / (1 - p))
    return round(100 * (1 - p) / p)

def parlay_payout(probs):
    combined = 1.0
    for p in probs:
        if p <= 0 or p >= 1: return 0
        combined *= (1 / p)
    return round((combined - 1) * 100, 2)

# ─── fetch odds ───────────────────────────────────────────────────────

def fetch_odds(sport_key):
    url = f"{BASE}/sports/{sport_key}/odds"
    params = {
        'apiKey': API_KEY, 'regions': 'us',
        'markets': 'h2h,spreads,totals',
        'oddsFormat': 'american', 'dateFormat': 'iso',
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        print(f"  ERROR fetching {sport_key}: {r.status_code}")
        return []
    data = r.json()
    # Only future games
    future = []
    for g in data:
        ct = datetime.fromisoformat(g['commence_time'].replace('Z', '+00:00'))
        if ct > NOW:
            future.append(g)
    print(f"  {sport_key}: {len(future)} upcoming (filtered from {len(data)})")
    return future

print("Fetching odds...")
nba_raw = fetch_odds("basketball_nba")
time.sleep(1)
ncaab_raw = fetch_odds("basketball_ncaab")

# ─── Per-sportsbook lines ────────────────────────────────────────────

def build_sportsbook_lines(games):
    result = []
    for g in games:
        entry = {
            "home": g["home_team"], "away": g["away_team"],
            "commence_time": g["commence_time"], "sportsbooks": {}
        }
        for bm in g.get("bookmakers", []):
            name = bm.get("title", bm["key"])
            book_data = {}
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if o["name"] == g["home_team"]: book_data["ml_home"] = o["price"]
                        elif o["name"] == g["away_team"]: book_data["ml_away"] = o["price"]
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
        result.append(entry)
    return result

print("\n[1] Per-sportsbook lines...")
ds1 = {"nba": build_sportsbook_lines(nba_raw), "ncaab": build_sportsbook_lines(ncaab_raw), "generated_at": NOW.isoformat()}
with open(os.path.join(OUT_DIR, "per_sportsbook_lines.json"), "w") as f:
    json.dump(ds1, f, indent=2)

# ─── Extract consensus picks ─────────────────────────────────────────

def extract_picks(games, sport_label):
    ml_spread_picks = []
    ou_picks = []
    for g in games:
        home, away = g["home_team"], g["away_team"]
        ml_home_list, ml_away_list, spread_home_list, spread_away_list, total_list = [], [], [], [], []
        for bm in g.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if o["name"] == home: ml_home_list.append(o["price"])
                        elif o["name"] == away: ml_away_list.append(o["price"])
                elif mkt["key"] == "spreads":
                    for o in mkt["outcomes"]:
                        if o["name"] == home: spread_home_list.append(o.get("point", 0))
                        elif o["name"] == away: spread_away_list.append(o.get("point", 0))
                elif mkt["key"] == "totals":
                    for o in mkt["outcomes"]:
                        if o["name"] == "Over": total_list.append(o.get("point", 0))

        if ml_home_list and ml_away_list:
            ph = american_to_prob(sum(ml_home_list)/len(ml_home_list))
            pa = american_to_prob(sum(ml_away_list)/len(ml_away_list))
            ph_dv, pa_dv = devig(ph, pa)
        else:
            ph_dv, pa_dv = 0.5, 0.5

        avg_spread_home = sum(spread_home_list)/len(spread_home_list) if spread_home_list else 0
        avg_total = sum(total_list)/len(total_list) if total_list else 0

        if ph_dv >= pa_dv:
            ml_pick, ml_side, ml_prob = home, "home", ph_dv
        else:
            ml_pick, ml_side, ml_prob = away, "away", pa_dv

        if avg_spread_home < 0:
            spread_pick, spread_side = home, "home"
            cover_prob = ph_dv * 0.85 + 0.08
        else:
            spread_pick, spread_side = away, "away"
            cover_prob = pa_dv * 0.85 + 0.08

        ml_spread_picks.append({
            "home": home, "away": away,
            "commence_time": g["commence_time"],
            "sport": sport_label,
            "ml_pick": ml_pick, "ml_side": ml_side,
            "ml_prob": round(ml_prob, 4), "ml_odds": prob_to_american(ml_prob),
            "spread_pick": spread_pick, "spread_side": spread_side,
            "spread_line": round(avg_spread_home, 1),  # home perspective
            "pick_spread": round(avg_spread_home if spread_side == "home" else -avg_spread_home, 1),  # from picked team's perspective
            "cover_prob": round(cover_prob, 4),
            "upset_composite": 0,  # This engine always picks the market favorite — no upset detection. Use run_full_analysis.py for upset signals.
            "consensus_ml_home": round(sum(ml_home_list)/len(ml_home_list)) if ml_home_list else 0,
            "consensus_ml_away": round(sum(ml_away_list)/len(ml_away_list)) if ml_away_list else 0,
        })
        ou_picks.append({
            "home": home, "away": away,
            "commence_time": g["commence_time"],
            "sport": sport_label,
            "total_line": round(avg_total, 1),
            "ou_pick": "Over" if avg_total > 0 else "N/A",
            "ou_prob": 0.52,
        })
    return ml_spread_picks, ou_picks

print("\n[2-5] Consensus picks...")
nba_ml_spread, nba_ou = extract_picks(nba_raw, "NBA")
ncaab_ml_spread, ncaab_ou = extract_picks(ncaab_raw, "NCAAB")

for name, data, n in [
    ("nba_ml_spread.json", nba_ml_spread, 2),
    ("nba_ou.json", nba_ou, 3),
    ("ncaab_ml_spread.json", ncaab_ml_spread, 4),
    ("ncaab_ou.json", ncaab_ou, 5),
]:
    with open(os.path.join(OUT_DIR, name), "w") as f:
        json.dump({"picks": data, "count": len(data), "generated_at": NOW.isoformat()}, f, indent=2)
    print(f"  [{n}] {name}: {len(data)} picks")

# ─── Time-Window Parlay Generation ───────────────────────────────────

def make_parlay_legs(picks, pick_type):
    legs = []
    for p in picks:
        base = {"game": f"{p['away']} @ {p['home']}", "commence_time": p["commence_time"]}
        if pick_type == "ml":
            legs.append({**base, "pick": p["ml_pick"], "type": "ML",
                        "odds": p["ml_odds"], "prob": p["ml_prob"]})
        elif pick_type == "spread":
            legs.append({**base, "pick": f"{p['spread_pick']} {p['spread_line']}",
                        "type": "Spread", "odds": -110, "prob": p["cover_prob"]})
        elif pick_type == "ou":
            if p.get("ou_pick", "N/A") == "N/A": continue
            legs.append({**base, "pick": f"{p['ou_pick']} {p['total_line']}",
                        "type": "O/U", "odds": -110, "prob": p["ou_prob"]})
    legs.sort(key=lambda x: x["prob"], reverse=True)
    return legs


def generate_windowed_parlays(legs, min_legs=2, max_legs=8):
    """Generate parlays grouped by time window.
    
    Each window gets its own parlay set so every combo is placeable on DK.
    """
    # Group legs by window
    windows = group_legs_by_window(legs, publish_time=PUBLISH_UTC)
    
    all_results = {}
    
    for window_name, window_legs in windows.items():
        if len(window_legs) < min_legs:
            continue
        
        window_legs.sort(key=lambda x: x["prob"], reverse=True)
        pool_limits = {2: min(len(window_legs), 80), 3: min(len(window_legs), 40),
                       4: 25, 5: 20, 6: 15, 7: 12, 8: 10}
        
        window_parlays = {}
        window_total = 0
        
        actual_max = min(max_legs, len(window_legs))
        for size in range(min_legs, actual_max + 1):
            pool_size = min(pool_limits.get(size, 15), len(window_legs))
            pool = window_legs[:pool_size]
            if len(pool) < size:
                continue
            
            combos = []
            for combo in combinations(pool, size):
                probs = [l["prob"] for l in combo]
                combined = 1.0
                for p in probs: combined *= p
                combos.append({
                    "legs": list(combo),
                    "combined_prob": round(combined, 6),
                    "payout_per_100": parlay_payout(probs),
                    "leg_count": size,
                    "window": window_name,
                    "window_label": window_label(window_name),
                })
            combos.sort(key=lambda x: x["combined_prob"], reverse=True)
            window_parlays[f"{size}_leg"] = combos
            window_total += len(combos)
        
        if window_parlays:
            all_results[window_name] = {
                "parlays": window_parlays,
                "total": window_total,
                "window_label": window_label(window_name),
                "games_in_window": len(window_legs),
            }
            print(f"    {window_label(window_name)}: {len(window_legs)} legs → {window_total:,} parlays")
    
    return all_results


def save_windowed_parlays(filename, legs, ds_num, label):
    print(f"  [{ds_num}] {filename} ({label}, {len(legs)} total legs)...")
    result = generate_windowed_parlays(legs)
    
    total_saved = sum(w["total"] for w in result.values())
    
    with open(os.path.join(OUT_DIR, filename), "w") as f:
        json.dump({
            "windows": result,
            "total_saved": total_saved,
            "publish_time": PUBLISH_UTC.isoformat(),
            "buffer_minutes": BUFFER_MINUTES,
            "generated_at": NOW.isoformat(),
        }, f, indent=2)
    print(f"    → {total_saved:,} total parlays across {len(result)} windows")


print(f"\n[6-13] Generating TIME-WINDOWED parlays (buffer={BUFFER_MINUTES}min)...")

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

save_windowed_parlays("parlays_nba_pure.json", nba_ms_legs, 6, "NBA ML+Spread")
save_windowed_parlays("parlays_ncaab_pure.json", ncaab_ms_legs, 7, "NCAAB ML+Spread")

mixed_ms = nba_ms_legs + ncaab_ms_legs
mixed_ms.sort(key=lambda x: x["prob"], reverse=True)
save_windowed_parlays("parlays_mixed_nba_ncaab.json", mixed_ms, 8, "Mixed ML+Spread")

save_windowed_parlays("parlays_nba_ou.json", nba_ou_legs, 9, "NBA O/U")
save_windowed_parlays("parlays_ncaab_ou.json", ncaab_ou_legs, 10, "NCAAB O/U")

mixed_ou = nba_ou_legs + ncaab_ou_legs
mixed_ou.sort(key=lambda x: x["prob"], reverse=True)
save_windowed_parlays("parlays_mixed_ou.json", mixed_ou, 11, "Mixed O/U")

mixed_spread_ou = nba_spread_legs + ncaab_spread_legs + nba_ou_legs + ncaab_ou_legs
mixed_spread_ou.sort(key=lambda x: x["prob"], reverse=True)
save_windowed_parlays("parlays_mixed_spread_ou.json", mixed_spread_ou, 12, "Mixed Spread+O/U")

mixed_ml_ou = nba_ml_legs + ncaab_ml_legs + nba_ou_legs + ncaab_ou_legs
mixed_ml_ou.sort(key=lambda x: x["prob"], reverse=True)
save_windowed_parlays("parlays_mixed_ml_ou.json", mixed_ml_ou, 13, "Mixed ML+O/U")

# ─── Generate customer-facing pick messages with window labels ────────

def generate_pick_messages(all_picks, windows_data):
    """Generate formatted pick messages grouped by time window."""
    messages = []
    
    for window_name in ['early', 'late', 'full_slate']:
        if window_name not in windows_data:
            continue
        wdata = windows_data[window_name]
        parlays = wdata.get("parlays", {})
        
        for size_key in ['2_leg', '3_leg', '4_leg', '5_leg']:
            if size_key not in parlays or not parlays[size_key]:
                continue
            best = parlays[size_key][0]  # highest combined_prob
            
            msg_lines = [
                f"🎯 {window_label(window_name)}",
                f"📊 {size_key.replace('_', '-').upper()} PARLAY",
                ""
            ]
            for leg in best["legs"]:
                ct = leg.get("commence_time", "")
                if ct:
                    from time_windows import parse_commence_time
                    et = parse_commence_time(ct).astimezone(EST)
                    time_str = et.strftime("%-I:%M %p ET")
                else:
                    time_str = "TBD"
                msg_lines.append(f"  ✅ {leg['pick']} ({leg['type']}) — {time_str}")
            
            msg_lines.append(f"\n  Combined: {best['combined_prob']:.1%} | Payout: ${best['payout_per_100']:.0f}/$100")
            messages.append("\n".join(msg_lines))
    
    return messages

# Save pick messages
print("\n[14] Generating pick messages...")
# Use the mixed parlays as the main source
mixed_file = os.path.join(OUT_DIR, "parlays_mixed_nba_ncaab.json")
if os.path.exists(mixed_file):
    with open(mixed_file) as f:
        mixed_data = json.load(f)
    
    msgs = generate_pick_messages(None, mixed_data.get("windows", {}))
    for i, msg in enumerate(msgs):
        msg_file = os.path.join(OUT_DIR, f"picks_msg_{i}.txt")
        with open(msg_file, "w") as f:
            f.write(msg)
    print(f"  {len(msgs)} pick messages saved")

# ─── Summary ──────────────────────────────────────────────────────────

print("\n" + "="*60)
print("DAILY MEGA RUN COMPLETE — Time-Window Aware")
print("="*60)

# Save summary
summary = {
    "date": TODAY,
    "publish_time_et": PUBLISH_ET.strftime('%I:%M %p ET'),
    "publish_time_utc": PUBLISH_UTC.isoformat(),
    "buffer_minutes": BUFFER_MINUTES,
    "nba_games": len(nba_raw),
    "ncaab_games": len(ncaab_raw),
    "output_dir": OUT_DIR,
    "generated_at": NOW.isoformat(),
    "time_window_enabled": True,
}
with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
    json.dump(summary, f, indent=2)

files = sorted(os.listdir(OUT_DIR))
for fn in files:
    fp = os.path.join(OUT_DIR, fn)
    if fn.endswith('.json'):
        size = os.path.getsize(fp)
        print(f"  {fn} ({size:,} bytes)")

print(f"\nAll files in: {OUT_DIR}")
print(f"Done at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
