#!/usr/bin/env python3
"""
NBA Upset Composite V2 — Tuning Backtest
==========================================
Fetches historical odds (spreads + h2h) and actual scores for past NBA games,
then grid-searches upset composite weights & thresholds to maximize:
  - Upset pick accuracy (cover rate when flagged)
  - Precision (flagged upsets that actually hit)
  - Profit if you bet only on flagged upset dogs

Uses: Odds API historical endpoint + ESPN scoreboard for actual scores.
"""

import json, logging, math, os, sys, time, requests
from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from itertools import product as iterproduct
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("backtest_upset_v2_tune.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("upset_v2_tune")

EST = timezone(timedelta(hours=-5))
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
CACHE_FILE = Path("_backtest_cache_nba.json")


# ═══════════════════════════════════════════════════════════════════════
# DATA COLLECTION
# ═══════════════════════════════════════════════════════════════════════

def fetch_historical_odds(target_date: str) -> List[dict]:
    """Fetch NBA odds for a given date (YYYY-MM-DD) from Odds API historical endpoint."""
    # Use noon ET as snapshot time (games usually start evening)
    dt = f"{target_date}T17:00:00Z"
    url = (f"https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds"
           f"?apiKey={ODDS_API_KEY}&regions=us&markets=spreads,h2h"
           f"&oddsFormat=decimal&date={dt}")
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        games = data.get("data", [])
        log.info(f"  Odds API {target_date}: {len(games)} games, "
                 f"remaining={r.headers.get('x-requests-remaining')}")
        return games
    except Exception as e:
        log.warning(f"  Odds API failed for {target_date}: {e}")
        return []


def fetch_espn_scores(target_date: str) -> Dict[str, dict]:
    """Fetch actual NBA scores from ESPN for a given date. Returns dict keyed by matchup."""
    date_str = target_date.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}"
    try:
        r = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        r.raise_for_status()
        results = {}
        for event in r.json().get("events", []):
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            comp = comps[0]
            teams_info = {}
            for c in comp.get("competitors", []):
                hoa = c.get("homeAway", "")
                team_name = c.get("team", {}).get("displayName", "")
                score = int(c.get("score", 0))
                teams_info[hoa] = {"name": team_name, "score": score}
            
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FINAL":
                continue
            
            home = teams_info.get("home", {})
            away = teams_info.get("away", {})
            if home and away:
                key = f"{home['name']} vs {away['name']}"
                results[key] = {
                    "home": home["name"],
                    "away": away["name"],
                    "home_score": home["score"],
                    "away_score": away["score"],
                    "margin": home["score"] - away["score"],
                }
        log.info(f"  ESPN scores {target_date}: {len(results)} final games")
        return results
    except Exception as e:
        log.warning(f"  ESPN scores failed for {target_date}: {e}")
        return {}


def match_odds_to_scores(odds_games: List[dict], scores: Dict[str, dict]) -> List[dict]:
    """Match Odds API games to ESPN actual scores. Returns enriched game list."""
    matched = []
    for game in odds_games:
        home = game["home_team"]
        away = game["away_team"]
        
        # Find matching ESPN score
        espn_match = None
        for key, sc in scores.items():
            if _fuzzy_match(home, sc["home"]) and _fuzzy_match(away, sc["away"]):
                espn_match = sc
                break
        
        if not espn_match:
            continue
        
        # Extract consensus spread & ML from bookmakers
        spreads = []
        ml_home_prices = []
        ml_away_prices = []
        
        for bk in game.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                if mkt["key"] == "spreads":
                    for o in mkt["outcomes"]:
                        if _fuzzy_match(o["name"], home):
                            spreads.append(o.get("point", 0))
                elif mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if _fuzzy_match(o["name"], home):
                            ml_home_prices.append(o["price"])
                        elif _fuzzy_match(o["name"], away):
                            ml_away_prices.append(o["price"])
        
        if not spreads:
            continue
        
        consensus_spread = sum(spreads) / len(spreads)  # negative = home favored
        
        # Devig ML to get implied probabilities
        if ml_home_prices and ml_away_prices:
            avg_home_ml = sum(ml_home_prices) / len(ml_home_prices)
            avg_away_ml = sum(ml_away_prices) / len(ml_away_prices)
            raw_home = 1 / avg_home_ml
            raw_away = 1 / avg_away_ml
            total = raw_home + raw_away
            ml_home_prob = raw_home / total
            ml_away_prob = raw_away / total
        else:
            # Estimate from spread
            abs_s = abs(consensus_spread)
            fav_prob = min(0.5 + abs_s * 0.03, 0.88)
            if consensus_spread < 0:
                ml_home_prob, ml_away_prob = fav_prob, 1 - fav_prob
            else:
                ml_home_prob, ml_away_prob = 1 - fav_prob, fav_prob
        
        # Determine who covers the spread
        actual_margin = espn_match["margin"]  # home - away
        # Home covers if margin > -spread (e.g. spread=-5, margin=-3 → -3 > 5? no. margin=6 > 5? yes)
        # Actually: home covers if margin + spread > 0 (spread is already signed)
        # e.g. home -5 (spread=-5): margin=6 → 6+(-5)=1>0 → home covers
        # e.g. home +3 (spread=3): margin=-1 → -1+3=2>0 → home covers
        home_covers = (actual_margin + consensus_spread) > 0
        away_covers = (actual_margin + consensus_spread) < 0
        push = (actual_margin + consensus_spread) == 0
        
        matched.append({
            "home": home,
            "away": away,
            "spread": round(consensus_spread, 1),  # negative = home fav
            "ml_home_prob": round(ml_home_prob, 4),
            "ml_away_prob": round(ml_away_prob, 4),
            "actual_margin": actual_margin,
            "home_score": espn_match["home_score"],
            "away_score": espn_match["away_score"],
            "home_covers": home_covers,
            "away_covers": away_covers,
            "push": push,
            "date": game.get("commence_time", "")[:10],
        })
    
    return matched


def _fuzzy_match(name1: str, name2: str) -> bool:
    """Fuzzy match team names."""
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()
    if n1 == n2:
        return True
    # Last word match
    w1 = n1.split()[-1] if n1 else ""
    w2 = n2.split()[-1] if n2 else ""
    if w1 == w2 and len(w1) > 3:
        return True
    # Handle "LA Clippers" vs "Los Angeles Clippers", etc
    if w1 in n2 or w2 in n1:
        return True
    return False


def collect_data(start_date: str, end_date: str) -> List[dict]:
    """Collect all historical games between dates. Uses cache."""
    if CACHE_FILE.exists():
        cached = json.loads(CACHE_FILE.read_text())
        cached_dates = set(g["date"][:10] for g in cached)
        log.info(f"Cache has {len(cached)} games across {len(cached_dates)} dates")
    else:
        cached = []
        cached_dates = set()
    
    all_games = list(cached)
    
    d = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    new_dates = 0
    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        if ds not in cached_dates:
            odds = fetch_historical_odds(ds)
            if odds:
                scores = fetch_espn_scores(ds)
                if scores:
                    matched = match_odds_to_scores(odds, scores)
                    all_games.extend(matched)
                    new_dates += 1
            time.sleep(0.5)  # Rate limit
        d += timedelta(days=1)
    
    if new_dates > 0:
        CACHE_FILE.write_text(json.dumps(all_games, indent=2))
        log.info(f"Cached {len(all_games)} total games (+{new_dates} new dates)")
    
    return all_games


# ═══════════════════════════════════════════════════════════════════════
# ESPN STANDINGS (for backtest, we use current — imperfect but workable)
# ═══════════════════════════════════════════════════════════════════════

def fetch_standings() -> Dict:
    """Fetch current NBA standings from ESPN."""
    from nba_upset_composite import fetch_nba_standings
    return fetch_nba_standings()


# ═══════════════════════════════════════════════════════════════════════
# PARAMETERIZED COMPOSITE (for grid search)
# ═══════════════════════════════════════════════════════════════════════

def compute_composite_parameterized(
    game: dict,
    standings: Dict,
    b2b_teams: set,
    # TUNABLE WEIGHTS
    w_disagree: float = 0.35,
    w_form: float = 0.20,
    w_splits: float = 0.15,
    w_rest: float = 0.15,
    w_injury: float = 0.15,
    # TUNABLE THRESHOLDS
    upset_threshold: float = 0.35,
    # ML prob buckets for disagreement score
    ml_buckets: tuple = (0.45, 0.40, 0.35, 0.28),
    ml_scores: tuple = (0.9, 0.7, 0.4, 0.2),
    # Form: L10 diff thresholds
    l10_thresholds: tuple = (0.2, 0.0, -0.2),
    l10_scores: tuple = (1.0, 0.6, 0.3, 0.0),
    # Tank penalty thresholds
    tank_wp: tuple = (0.35, 0.42),
    tank_mult: tuple = (0.3, 0.6),
) -> Tuple[float, bool, str]:
    """
    Parameterized version of the upset composite for grid search.
    Returns (score, is_upset, dog_team).
    """
    home = game["home"]
    away = game["away"]
    spread = game["spread"]
    
    if spread == 0:
        return 0.0, False, ""
    
    # Determine market favorite and dog
    if spread < 0:
        market_fav, market_dog = home, away
        dog_side = "away"
    else:
        market_fav, market_dog = away, home
        dog_side = "home"
    
    # Dog's ML prob
    if dog_side == "home":
        dog_ml_prob = game["ml_home_prob"]
    else:
        dog_ml_prob = game["ml_away_prob"]
    
    # ─── Factor 1: Disagreement ───────────────────────────────────
    disagree_score = 0.0
    for i, bucket in enumerate(ml_buckets):
        if dog_ml_prob >= bucket:
            disagree_score = ml_scores[i]
            break
    
    score = disagree_score * w_disagree
    
    # ─── Factor 2: Form (L10) ────────────────────────────────────
    form_score = 0.0
    from nba_upset_composite import get_team_stats
    dog_stats = get_team_stats(standings, market_dog)
    fav_stats = get_team_stats(standings, market_fav)
    
    if dog_stats and fav_stats:
        dog_l10 = dog_stats.get("l10_pct", 0.5)
        fav_l10 = fav_stats.get("l10_pct", 0.5)
        l10_diff = dog_l10 - fav_l10
        
        for i, thresh in enumerate(l10_thresholds):
            if l10_diff > thresh:
                form_score = l10_scores[i]
                break
        else:
            form_score = l10_scores[-1]
        
        dog_wp = dog_stats.get("win_pct", 0.5)
        for i, wp in enumerate(tank_wp):
            if dog_wp < wp:
                form_score *= tank_mult[i]
                break
    
    score += form_score * w_form
    
    # ─── Factor 3: Home/Away Splits ──────────────────────────────
    split_score = 0.0
    if dog_stats:
        if dog_side == "home":
            hp = dog_stats.get("home_pct", 0.5)
            if hp >= 0.60: split_score = 1.0
            elif hp >= 0.50: split_score = 0.6
            elif hp >= 0.40: split_score = 0.3
        else:
            ap = dog_stats.get("away_pct", 0.5)
            if ap >= 0.55: split_score = 0.8
            elif ap >= 0.45: split_score = 0.5
            elif ap >= 0.35: split_score = 0.2
    
    if fav_stats and dog_side == "home":
        fav_away_pct = fav_stats.get("away_pct", 0.5)
        if fav_away_pct < 0.50:
            split_score = min(split_score + 0.2, 1.0)
    
    score += split_score * w_splits
    
    # ─── Factor 4: Rest / B2B ────────────────────────────────────
    rest_score = 0.3  # Default (no B2B data in backtest usually)
    score += rest_score * w_rest
    
    # ─── Factor 5: Injury (skip in backtest — no historical data) ─
    injury_score = 0.3  # Neutral default
    score += injury_score * w_injury
    
    final_score = round(min(1.0, score), 4)
    is_upset = final_score >= upset_threshold
    
    return final_score, is_upset, market_dog


# ═══════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════

def run_backtest(games: List[dict], standings: Dict, **params) -> dict:
    """
    Run the upset composite on all games with given params.
    For each game, we simulate: "if the composite flags this as an upset,
    we bet the DOG to cover the spread."
    
    Returns performance metrics.
    """
    total = 0
    flagged = 0
    flagged_hits = 0
    flagged_misses = 0
    not_flagged = 0
    not_flagged_would_hit = 0  # Dogs that covered but we didn't flag
    
    # Track by spread bucket
    by_spread = defaultdict(lambda: {"flagged": 0, "hit": 0, "total": 0})
    # Track by composite score bucket
    by_score = defaultdict(lambda: {"flagged": 0, "hit": 0})
    
    details = []
    
    for game in games:
        if game.get("push"):
            continue
        
        spread = game["spread"]
        if spread == 0:
            continue
        
        # Who is the dog?
        if spread < 0:
            dog = game["away"]
            dog_covers = game["away_covers"]
            dog_spread = abs(spread)
        else:
            dog = game["home"]
            dog_covers = game["home_covers"]
            dog_spread = spread
        
        total += 1
        
        composite_score, is_upset, dog_team = compute_composite_parameterized(
            game, standings, set(), **params
        )
        
        bucket = f"{int(dog_spread)}-{int(dog_spread)+2}"
        by_spread[bucket]["total"] += 1
        
        score_bucket = f"{int(composite_score * 10) / 10:.1f}"
        
        if is_upset:
            flagged += 1
            by_spread[bucket]["flagged"] += 1
            by_score[score_bucket]["flagged"] += 1
            
            if dog_covers:
                flagged_hits += 1
                by_spread[bucket]["hit"] += 1
                by_score[score_bucket]["hit"] += 1
                details.append({"game": f"{dog} +{dog_spread}", "score": composite_score, "result": "HIT"})
            else:
                flagged_misses += 1
                details.append({"game": f"{dog} +{dog_spread}", "score": composite_score, "result": "MISS"})
        else:
            not_flagged += 1
            if dog_covers:
                not_flagged_would_hit += 1
    
    precision = flagged_hits / max(flagged, 1)
    recall = flagged_hits / max(flagged_hits + not_flagged_would_hit, 1)
    
    # Profit simulation: -110 odds, $100 per bet
    profit = flagged_hits * 90.91 - flagged_misses * 100  # Standard -110 juice
    roi = profit / max(flagged * 100, 1) * 100
    
    return {
        "total_games": total,
        "flagged": flagged,
        "flagged_hits": flagged_hits,
        "flagged_misses": flagged_misses,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "not_flagged_would_hit": not_flagged_would_hit,
        "profit_$100_bets": round(profit, 2),
        "roi_pct": round(roi, 2),
        "by_spread": dict(by_spread),
        "by_score": dict(by_score),
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════
# GRID SEARCH
# ═══════════════════════════════════════════════════════════════════════

def grid_search(games: List[dict], standings: Dict):
    """Grid search over key parameters to find optimal combo."""
    
    # Weight combos (must sum to ~1.0, rest+injury fixed at 0.15 each)
    # Main knobs: w_disagree, w_form, w_splits
    weight_combos = [
        # (disagree, form, splits, rest, injury)
        (0.35, 0.20, 0.15, 0.15, 0.15),  # Current
        (0.40, 0.20, 0.10, 0.15, 0.15),  # More disagreement weight
        (0.45, 0.15, 0.10, 0.15, 0.15),  # Heavy disagreement
        (0.30, 0.25, 0.15, 0.15, 0.15),  # More form weight
        (0.35, 0.25, 0.10, 0.15, 0.15),  # Balanced disagree+form
        (0.40, 0.15, 0.15, 0.15, 0.15),  # Disagree heavy, less form
        (0.30, 0.20, 0.20, 0.15, 0.15),  # More splits
        (0.50, 0.10, 0.10, 0.15, 0.15),  # Disagree dominant
        (0.35, 0.15, 0.20, 0.15, 0.15),  # Splits up
        (0.25, 0.30, 0.15, 0.15, 0.15),  # Form dominant
    ]
    
    thresholds = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    
    results = []
    
    for weights in weight_combos:
        for thresh in thresholds:
            params = {
                "w_disagree": weights[0],
                "w_form": weights[1],
                "w_splits": weights[2],
                "w_rest": weights[3],
                "w_injury": weights[4],
                "upset_threshold": thresh,
            }
            
            r = run_backtest(games, standings, **params)
            r["params"] = params
            results.append(r)
    
    return results


def main():
    log.info("=" * 70)
    log.info("NBA UPSET COMPOSITE V2 — TUNING BACKTEST")
    log.info("=" * 70)
    
    # Collect data: last 30 days of NBA games
    end = datetime.now(EST) - timedelta(days=1)  # Yesterday (most recent completed)
    start = end - timedelta(days=30)
    
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    log.info(f"Date range: {start_str} to {end_str}")
    
    games = collect_data(start_str, end_str)
    log.info(f"\nTotal matched games: {len(games)}")
    
    if len(games) < 20:
        log.error("Not enough games for meaningful backtest. Need at least 20.")
        return
    
    # Quick stats
    dogs_covered = sum(1 for g in games if not g.get("push") and (
        (g["spread"] < 0 and g["away_covers"]) or 
        (g["spread"] > 0 and g["home_covers"])
    ))
    log.info(f"Dogs that covered: {dogs_covered}/{len(games)} ({dogs_covered/len(games):.1%})")
    
    # Fetch standings
    standings = fetch_standings()
    log.info(f"Standings loaded: {len(standings)} entries")
    
    # Run grid search
    log.info("\n" + "=" * 70)
    log.info("GRID SEARCH — 60 parameter combos")
    log.info("=" * 70)
    
    results = grid_search(games, standings)
    
    # Sort by precision (primary) then ROI (secondary)
    # Only consider combos that flagged at least 5 games (statistical relevance)
    valid = [r for r in results if r["flagged"] >= 5]
    valid.sort(key=lambda x: (x["precision"], x["roi_pct"]), reverse=True)
    
    log.info("\n" + "=" * 70)
    log.info("TOP 10 PARAMETER COMBOS (min 5 flagged games)")
    log.info("=" * 70)
    
    for i, r in enumerate(valid[:10]):
        p = r["params"]
        log.info(f"\n#{i+1}: Precision={r['precision']:.1%} | ROI={r['roi_pct']:+.1f}% | "
                 f"Flagged={r['flagged']}/{r['total_games']} | Hits={r['flagged_hits']}")
        log.info(f"  Weights: disagree={p['w_disagree']}, form={p['w_form']}, "
                 f"splits={p['w_splits']} | Threshold={p['upset_threshold']}")
        log.info(f"  Profit: ${r['profit_$100_bets']:+.0f} on {r['flagged']} bets | "
                 f"Missed dogs: {r['not_flagged_would_hit']}")
    
    # Also show the CURRENT settings performance
    current = next((r for r in results if 
                     r["params"]["w_disagree"] == 0.35 and 
                     r["params"]["w_form"] == 0.20 and 
                     r["params"]["upset_threshold"] == 0.35), None)
    
    if current:
        log.info(f"\n{'=' * 70}")
        log.info(f"CURRENT SETTINGS: Precision={current['precision']:.1%} | "
                 f"ROI={current['roi_pct']:+.1f}% | Flagged={current['flagged']}")
    
    # Best combo details
    if valid:
        best = valid[0]
        log.info(f"\n{'=' * 70}")
        log.info("BEST COMBO — DETAILED PICKS")
        log.info(f"{'=' * 70}")
        for d in best["details"]:
            emoji = "+" if d["result"] == "HIT" else "x"
            log.info(f"  [{emoji}] {d['game']} (composite={d['score']:.2f}) — {d['result']}")
        
        log.info(f"\nBy composite score bucket:")
        for bucket in sorted(best["by_score"].keys()):
            bs = best["by_score"][bucket]
            hit_rate = bs["hit"] / max(bs["flagged"], 1)
            log.info(f"  Score {bucket}: {bs['hit']}/{bs['flagged']} hit ({hit_rate:.0%})")
    
    # Save results
    output = {
        "date_range": f"{start_str} to {end_str}",
        "total_games": len(games),
        "top_10": [{"rank": i+1, **r} for i, r in enumerate(valid[:10])],
        "current_settings": current,
        "all_results": results,
    }
    
    outfile = Path("backtest_upset_v2_tune_results.json")
    outfile.write_text(json.dumps(output, indent=2, default=str))
    log.info(f"\nResults saved to {outfile}")


if __name__ == "__main__":
    main()
