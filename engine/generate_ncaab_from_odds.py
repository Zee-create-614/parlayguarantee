"""
Generate NCAAB picks directly from Odds API data.
Mirrors generate_from_odds.py (NBA) for consistent output format.
Outputs ncaab_picks_output.json and ncaab_analyzed_games.json.
"""
import requests
import json
import itertools
import os
import sys
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Known weak teams for 2025-26 (sub-.300 win%)
WEAK_TEAMS = set()  # populated dynamically from records


def fetch_odds():
    r = requests.get(
        "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/",
        params={
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "dateFormat": "iso",
        },
        timeout=20,
    )
    r.raise_for_status()
    remaining = r.headers.get("x-requests-remaining", "?")
    print(f"Odds API: {len(r.json())} NCAAB events (remaining: {remaining})")
    return r.json()


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


def avg_total(bookmakers):
    totals = []
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == "totals":
                for o in mkt["outcomes"]:
                    if o["name"] == "Over":
                        totals.append(o.get("point", 0))
    return sum(totals) / len(totals) if totals else None


def build_analyzed_games(odds_data, target_date: str) -> List[Dict]:
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])

        home_h2h = avg_odds(bm, "h2h", home)
        away_h2h = avg_odds(bm, "h2h", away)
        if not home_h2h or not away_h2h:
            continue

        # Implied probabilities (vig-removed)
        raw_home = 1 / home_h2h
        raw_away = 1 / away_h2h
        total_raw = raw_home + raw_away
        home_prob = raw_home / total_raw
        away_prob = raw_away / total_raw

        spread = avg_spread(bm, home)
        total = avg_total(bm)

        # Convert commence_time to ET
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        est = timezone(timedelta(hours=-5))
        ct_est = ct.astimezone(est)
        game_date_str = ct_est.strftime("%Y-%m-%d")

        # Only include games for the target date (or next day for late games)
        target_dt = date.fromisoformat(target_date)
        game_dt = ct_est.date()
        if game_dt != target_dt and game_dt != target_dt + timedelta(days=1):
            continue

        pick = home if home_prob >= away_prob else away
        win_prob = max(home_prob, away_prob)

        # Upset potential scoring (same logic as NBA engine)
        upset_score = 0.0
        upset_reasons = []
        spread_abs = abs(spread)

        if spread_abs < 5:
            upset_score += 0.3
            upset_reasons.append(f"Tight spread ({spread:+.1f})")
        if spread > 0:  # home is underdog
            upset_score += 0.4
            upset_reasons.append("Home underdog")
        if spread_abs >= 7 and win_prob < 0.55:
            upset_score += 0.5
            upset_reasons.append(f"Big dog +{spread_abs:.1f}")

        # Edge vs market
        market_fav_prob = 0.5 + (spread_abs / 25.0)
        market_fav_prob = max(0.3, min(0.85, market_fav_prob))
        edge = win_prob - market_fav_prob if win_prob > 0.5 else 0
        if edge > 0.05:
            upset_score += 0.4
            upset_reasons.append("Model edge vs market")

        # Value score
        value_score = win_prob
        if edge > 0.05:
            value_score += edge * 2.0
        elif edge > 0.02:
            value_score += edge * 1.5
        # Home court advantage is bigger in college
        if pick == home:
            value_score += 0.04
        value_score = max(0.1, min(1.0, value_score))

        # Pick label
        if value_score >= 0.72:
            pick_label = "LOCK"
        elif edge > 0.05:
            pick_label = "VALUE"
        elif upset_score >= 0.5:
            pick_label = "UPSET"
        else:
            pick_label = "LEAN"

        games.append({
            "home": home,
            "away": away,
            "pick": pick,
            "win_prob": round(win_prob, 4),
            "home_probability": round(home_prob, 4),
            "away_probability": round(away_prob, 4),
            "game_date": game_date_str,
            "game_time": ct.isoformat(),
            "game_id": g["id"],
            "game_status": "Scheduled",
            "spread": round(spread, 1),
            "total": round(total, 1) if total else None,
            "value_score": round(value_score, 4),
            "edge_vs_market": round(edge, 4),
            "pick_label": pick_label,
            "upset_potential": round(upset_score, 3),
            "upset_score": round(upset_score, 3),
            "upset_reasons": upset_reasons,
            "sport": "NCAAB",
        })

    games.sort(key=lambda x: x["value_score"], reverse=True)
    return games


def make_payout(prob):
    return f"{1/prob:.1f}x" if prob > 0 else "1.0x"


def generate_single_picks(games, count=5):
    picks = []
    for i, g in enumerate(games[:count]):
        picks.append({
            "pick_number": i + 1,
            "type": "single",
            "legs": 1,
            "bet_type": "moneyline",
            "games": [g],
            "combined_prob": g["win_prob"],
            "value_score": g["value_score"],
            "edge_vs_market": g["edge_vs_market"],
            "pick_label": g["pick_label"],
            "implied_payout": make_payout(g["win_prob"]),
            "earliest_game_time": g["game_time"],
        })
    return picks


def generate_parlay_picks(games, legs, count):
    if len(games) < legs:
        return []
    combos = list(itertools.combinations(games, legs))
    scored = []
    for combo in combos:
        cp = 1.0
        vs = 1.0
        for g in combo:
            cp *= g["win_prob"]
            vs *= g["value_score"]
        times = [g["game_time"] for g in combo]
        scored.append((combo, cp, vs, min(times) if times else ""))
    scored.sort(key=lambda x: x[2], reverse=True)

    picks = []
    used_sets = []
    for combo, cp, vs, et in scored:
        teams_set = frozenset(g["pick"] for g in combo)
        if any(teams_set == u for u in used_sets):
            continue
        used_sets.append(teams_set)
        picks.append({
            "pick_number": len(picks) + 1,
            "type": "parlay",
            "legs": legs,
            "bet_type": "moneyline",
            "games": list(combo),
            "combined_prob": round(cp, 6),
            "value_score": round(vs, 6),
            "implied_payout": make_payout(cp),
            "earliest_game_time": et,
        })
        if len(picks) >= count:
            break
    return picks


def generate_spread_picks(games, legs, count):
    spread_games = []
    for g in games:
        sp = abs(g["spread"])
        if sp <= 3:
            cover = 0.52
        elif sp <= 7:
            cover = 0.50 + (g["win_prob"] - 0.5) * 0.3
        else:
            cover = 0.48 + (g["win_prob"] - 0.5) * 0.2
        cover = max(0.35, min(0.65, cover))

        sg = dict(g)
        sg["spread_pick"] = g["pick"]
        sg["spread_value"] = g["spread"] if g["pick"] == g["home"] else -g["spread"]
        sg["cover_prob"] = round(cover, 4)
        sg["win_prob"] = cover
        spread_games.append(sg)

    spread_games.sort(key=lambda x: x["cover_prob"], reverse=True)

    if legs == 1:
        picks = []
        for i, g in enumerate(spread_games[:count]):
            picks.append({
                "pick_number": i + 1,
                "type": "single",
                "legs": 1,
                "bet_type": "spread",
                "games": [g],
                "combined_prob": g["cover_prob"],
                "implied_payout": make_payout(g["cover_prob"]),
                "earliest_game_time": g["game_time"],
            })
        return picks
    else:
        return generate_parlay_picks(spread_games, legs, count)


def main():
    target_date = date.today().isoformat()
    if len(sys.argv) > 1:
        target_date = sys.argv[1]

    print(f"Generating NCAAB picks for {target_date}...")
    odds_data = fetch_odds()

    games = build_analyzed_games(odds_data, target_date)
    print(f"Analyzed {len(games)} NCAAB games for {target_date}")

    if not games:
        print("No NCAAB games found for this date.")
        result = {
            "date": target_date,
            "generated_at": datetime.now().isoformat(),
            "sport": "NCAAB",
            "total_games": 0,
            "no_games": True,
            "tiers": {},
        }
        with open("ncaab_picks_output.json", "w") as f:
            json.dump(result, f, indent=2)
        return

    # Print analysis
    for g in games:
        print(f"  {g['away']} @ {g['home']}: {g['pick']} ({g['win_prob']:.1%}) "
              f"spread={g['spread']:+.1f} value={g['value_score']:.3f} "
              f"label={g['pick_label']} upset={g['upset_potential']:.2f}")

    # Build tier structure
    TIERS = {
        "single": (1, 5),
        "2leg": (2, 5),
        "3leg": (3, 3),
        "4leg": (4, 3),
        "5leg": (5, 2),
        "6leg": (6, 2),
        "7leg": (7, 1),
    }
    SPREAD_TIERS = {
        "spread_single": (1, 5),
        "spread_2leg": (2, 5),
        "spread_3leg": (3, 3),
        "spread_4leg": (4, 2),
        "spread_5leg": (5, 1),
    }

    result = {
        "date": target_date,
        "generated_at": datetime.now().isoformat(),
        "sport": "NCAAB",
        "total_games": len(games),
        "tiers": {},
    }

    for tid, (legs, count) in TIERS.items():
        if legs == 1:
            picks = generate_single_picks(games, count)
        else:
            picks = generate_parlay_picks(games, legs, count)
        result["tiers"][tid] = {
            "tier_id": tid,
            "tier_name": f"NCAAB {legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
            "legs": legs,
            "picks": picks,
            "total_picks": len(picks),
        }
        print(f"  {tid}: {len(picks)} picks")

    for tid, (legs, count) in SPREAD_TIERS.items():
        picks = generate_spread_picks(games, legs, count)
        result["tiers"][tid] = {
            "tier_id": tid,
            "tier_name": f"NCAAB Spread {legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
            "legs": legs,
            "bet_type": "spread",
            "picks": picks,
            "total_picks": len(picks),
        }
        print(f"  {tid}: {len(picks)} spread picks")

    result["_metadata"] = {
        "engine_version": "ncaab_v1_odds_api",
        "source": "the-odds-api.com",
    }

    engine_dir = os.path.dirname(os.path.abspath(__file__))

    with open(os.path.join(engine_dir, "ncaab_picks_output.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nSaved ncaab_picks_output.json ({len(games)} games)")

    with open(os.path.join(engine_dir, "ncaab_analyzed_games.json"), "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2, ensure_ascii=False)
    print(f"Saved ncaab_analyzed_games.json ({len(games)} games)")

    # Archive
    history_dir = os.path.join(engine_dir, "history")
    os.makedirs(history_dir, exist_ok=True)
    import shutil
    shutil.copy2(
        os.path.join(engine_dir, "ncaab_analyzed_games.json"),
        os.path.join(history_dir, f"ncaab_analyzed_games_{target_date}.json")
    )
    print("Archived to history/")

    print("\nDone!")


if __name__ == "__main__":
    main()
