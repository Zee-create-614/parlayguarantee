#!/usr/bin/env python3
"""
Feb 22, 2026 — Full Parlay Simulation
Generates ALL unique parlay combinations across NBA/NCAAB spreads, ML, O/U.
Uses compact format: legs stored as indices into a master legs list.
Each output file has {"legs_index": [...], "parlays": [{leg_ids, prob, odds, n}]}
"""

import json, math, sys, time
from itertools import combinations
from pathlib import Path
from collections import defaultdict
import heapq

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = Path(__file__).parent
SIM_DIR = ENGINE_DIR / "sim"
SIM_DIR.mkdir(exist_ok=True)

with open(ENGINE_DIR / "analyzed_games.json", encoding="utf-8") as f:
    ALL_GAMES = json.load(f)

NBA = [g for g in ALL_GAMES if g["sport"] == "NBA"]
NCAAB = [g for g in ALL_GAMES if g["sport"] == "NCAAB"]
print(f"Loaded {len(ALL_GAMES)} games: {len(NBA)} NBA, {len(NCAAB)} NCAAB", flush=True)


def prob_to_american(prob):
    if prob <= 0 or prob >= 1:
        return 0
    return round(-prob / (1 - prob) * 100) if prob >= 0.5 else round((1 - prob) / prob * 100)


def make_spread_leg(g):
    return {
        "team": g["pick"], "pick": f"{g['pick']} {g['spread_str']}",
        "line": g.get("spread", 0), "odds": prob_to_american(g.get("enhanced_prob", g.get("cover_prob", 0.5))),
        "prob": g.get("enhanced_prob", g.get("cover_prob", 0.5)),
        "sport": g["sport"], "bet_type": "spread",
        "home": g["home"], "away": g["away"],
    }


def make_ml_leg(g):
    p = g.get("ml_prob", 0.5)
    return {
        "team": g.get("ml_pick", g["pick"]), "pick": f"{g.get('ml_pick', g['pick'])} ML",
        "line": 0, "odds": prob_to_american(p), "prob": p,
        "sport": g["sport"], "bet_type": "moneyline",
        "home": g["home"], "away": g["away"],
    }


def make_ou_leg(g):
    v3 = g.get("ou_model_v3", {})
    pick = v3.get("pick", "PASS")
    conf = v3.get("confidence", g.get("ou_prob", 0.5))
    return {
        "team": f"{g['home']} vs {g['away']}",
        "pick": f"{pick} {g.get('total_line', 0)}",
        "line": g.get("total_line", 0), "odds": prob_to_american(conf), "prob": conf,
        "sport": g["sport"], "bet_type": "over_under",
        "home": g["home"], "away": g["away"],
    }


def generate_and_save(legs, filename, label, min_legs=2, max_legs=7,
                       max_per_size=None, filter_fn=None):
    """Generate parlays and save compactly. legs_index + parlays with leg indices."""
    probs = [l["prob"] for l in legs]
    legs_clean = [{k: v for k, v in l.items() if k != "prob"} for l in legs]
    n = len(legs)
    
    all_parlays = []
    total_count = 0
    
    for size in range(min_legs, min(max_legs, n) + 1):
        tc = math.comb(n, size)
        need_sample = max_per_size and tc > max_per_size * 2
        
        if need_sample:
            print(f"    {size}-leg: {tc:,} combos -> sampling top {max_per_size:,}", flush=True)
            heap = []
            cnt = 0
            for combo in combinations(range(n), size):
                if filter_fn:
                    # Quick check using precomputed sport/type arrays
                    if not filter_fn(combo):
                        continue
                cp = 1.0
                for i in combo:
                    cp *= probs[i]
                cnt += 1
                if len(heap) < max_per_size:
                    heapq.heappush(heap, (cp, cnt, combo))
                elif cp > heap[0][0]:
                    heapq.heapreplace(heap, (cp, cnt, combo))
            
            for cp, _, combo in heap:
                all_parlays.append((list(combo), round(cp, 8), prob_to_american(cp), size))
            total_count += len(heap)
            print(f"      -> {len(heap):,} kept (from {cnt:,} valid)", flush=True)
        else:
            cnt = 0
            for combo in combinations(range(n), size):
                if filter_fn and not filter_fn(combo):
                    continue
                cp = 1.0
                for i in combo:
                    cp *= probs[i]
                all_parlays.append((list(combo), round(cp, 8), prob_to_american(cp), size))
                cnt += 1
            total_count += cnt
            print(f"    {size}-leg: {cnt:,} parlays", flush=True)
    
    # Save compact format
    output = {
        "legs_index": legs_clean,
        "parlays": [{"l": p[0], "p": p[1], "o": p[2], "n": p[3]} for p in all_parlays]
    }
    path = SIM_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
    
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"  {label}: {total_count:,} parlays -> {filename} ({size_mb:.1f}MB)", flush=True)
    return all_parlays, legs_clean


def summarize_category(parlays_tuples):
    by_legs = defaultdict(list)
    for leg_ids, cp, odds, n in parlays_tuples:
        by_legs[n].append(cp)
    
    avg_by_legs = {}
    for n, ps in sorted(by_legs.items()):
        avg_by_legs[str(n)] = {"count": len(ps), "avg_prob": round(sum(ps)/len(ps), 8), "max_prob": round(max(ps), 8)}
    
    best_idx = max(range(len(parlays_tuples)), key=lambda i: parlays_tuples[i][1]) if parlays_tuples else None
    best = None
    if best_idx is not None:
        b = parlays_tuples[best_idx]
        best = {"leg_ids": b[0], "combined_probability": b[1], "combined_american_odds": b[2], "number_of_legs": b[3]}
    
    return {"total": len(parlays_tuples), "by_legs": avg_by_legs, "best_parlay": best}


# ============================================================
summary = {}
t0 = time.time()

# 3. NBA Spread
print("\n=== NBA Spread Parlays (11 games) ===", flush=True)
nba_spread_legs = [make_spread_leg(g) for g in NBA]
nba_sp, _ = generate_and_save(nba_spread_legs, "feb22_nba_spread_parlays.json", "NBA Spread")
summary["nba_spread"] = summarize_category(nba_sp)

# 3b. NBA ML
print("\n=== NBA ML Parlays (11 games) ===", flush=True)
nba_ml_legs = [make_ml_leg(g) for g in NBA]
nba_ml, _ = generate_and_save(nba_ml_legs, "feb22_nba_ml_parlays.json", "NBA ML")
summary["nba_ml"] = summarize_category(nba_ml)

# 4. NCAAB Spread
print("\n=== NCAAB Spread Parlays (22 games) ===", flush=True)
ncaab_spread_legs = [make_spread_leg(g) for g in NCAAB]
ncaab_sp, _ = generate_and_save(ncaab_spread_legs, "feb22_ncaab_spread_parlays.json", "NCAAB Spread")
summary["ncaab_spread"] = summarize_category(ncaab_sp)

# 4b. NCAAB ML
print("\n=== NCAAB ML Parlays (22 games) ===", flush=True)
ncaab_ml_legs = [make_ml_leg(g) for g in NCAAB]
ncaab_ml, _ = generate_and_save(ncaab_ml_legs, "feb22_ncaab_ml_parlays.json", "NCAAB ML")
summary["ncaab_ml"] = summarize_category(ncaab_ml)

# 5. Mixed Spread (both sports required)
print("\n=== Mixed NBA+NCAAB Spread Parlays ===", flush=True)
all_spread_legs = nba_spread_legs + ncaab_spread_legs
# Precompute sport per leg for fast filtering
spread_sports = [l["sport"] for l in all_spread_legs]
nba_count = len(nba_spread_legs)

def has_both_sports_spread(combo):
    has_nba = any(i < nba_count for i in combo)
    has_ncaab = any(i >= nba_count for i in combo)
    return has_nba and has_ncaab

mixed_sp, _ = generate_and_save(all_spread_legs, "feb22_mixed_spread_parlays.json", "Mixed Spread",
                                 max_per_size=10000, filter_fn=has_both_sports_spread)
summary["mixed_spread"] = summarize_category(mixed_sp)

# 5b. Mixed ML
print("\n=== Mixed NBA+NCAAB ML Parlays ===", flush=True)
all_ml_legs = nba_ml_legs + ncaab_ml_legs

def has_both_sports_ml(combo):
    has_nba = any(i < len(nba_ml_legs) for i in combo)
    has_ncaab = any(i >= len(nba_ml_legs) for i in combo)
    return has_nba and has_ncaab

mixed_ml, _ = generate_and_save(all_ml_legs, "feb22_mixed_ml_parlays.json", "Mixed ML",
                                 max_per_size=10000, filter_fn=has_both_sports_ml)
summary["mixed_ml"] = summarize_category(mixed_ml)

# 6. O/U
print("\n=== O/U Parlays ===", flush=True)
ou_games = [g for g in ALL_GAMES if g.get("ou_model_v3", {}).get("pick", "PASS") != "PASS"]
print(f"  {len(ou_games)} games with O/U picks", flush=True)
ou_legs = [make_ou_leg(g) for g in ou_games]
ou_p, _ = generate_and_save(ou_legs, "feb22_ou_parlays.json", "O/U")
summary["ou"] = summarize_category(ou_p)

# 7. Mixed Everything (spread + O/U, 2+ bet types)
print("\n=== Mixed Everything (Spread + O/U) ===", flush=True)
everything_legs = [make_spread_leg(g) for g in ALL_GAMES] + ou_legs
spread_count = len(ALL_GAMES)

def has_two_types(combo):
    has_spread = any(i < spread_count for i in combo)
    has_ou = any(i >= spread_count for i in combo)
    return has_spread and has_ou

mixed_ev, _ = generate_and_save(everything_legs, "feb22_everything_mixed.json", "Everything Mixed",
                                 max_per_size=10000, filter_fn=has_two_types)
summary["everything_mixed"] = summarize_category(mixed_ev)

# Save summary
with open(SIM_DIR / "feb22_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

elapsed = time.time() - t0
print(f"\n{'='*60}", flush=True)
print(f"SIMULATION COMPLETE in {elapsed:.1f}s", flush=True)
print(f"{'='*60}", flush=True)
print(f"\nSummary by category:", flush=True)
for cat, data in summary.items():
    print(f"  {cat}: {data['total']:,} total parlays")
    for legs, info in data["by_legs"].items():
        print(f"    {legs}-leg: {info['count']:,} combos, avg prob {info['avg_prob']:.6f}, best {info['max_prob']:.6f}")
    if data.get("best_parlay"):
        bp = data["best_parlay"]
        print(f"    BEST: {bp['number_of_legs']}-leg @ {bp['combined_probability']:.6f} ({bp['combined_american_odds']})")
print(f"\nAll files saved to {SIM_DIR}", flush=True)
