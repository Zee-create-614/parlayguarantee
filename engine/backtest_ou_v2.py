"""
Backtest O/U v2 engine against last 2-3 weeks of NBA results.
Uses Odds API historical endpoint for posted totals + ESPN for actual scores.
"""

import requests
import json
import logging
import sys
import statistics
import time
from datetime import date, timedelta, datetime
from pathlib import Path
from totals_engine_v2 import TotalsEngineV2, LEAGUE_AVG_PPG, LEAGUE_AVG_PACE

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"


def fetch_historical_odds(target_date: date):
    """Fetch historical totals from Odds API for a given date."""
    # Use noon UTC of that day to get pre-game lines
    dt_str = f"{target_date.isoformat()}T17:00:00Z"  # 5PM UTC = noon EST
    url = "https://api.the-odds-api.com/v4/historical/sports/basketball_nba/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "totals,spreads",
        "date": dt_str,
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        remaining = resp.headers.get("x-requests-remaining", "?")
        if resp.status_code != 200:
            logger.warning(f"Odds API {resp.status_code} for {target_date}")
            return []
        
        data = resp.json()
        games = []
        for g in data.get("data", []):
            commence = g.get("commence_time", "")
            # Parse game date from commence time
            if commence:
                utc_dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                est_dt = utc_dt - timedelta(hours=5)
                game_date = est_dt.date()
            else:
                game_date = target_date
            
            # Only games on target date (EST)
            if game_date != target_date:
                continue
            
            home = g["home_team"]
            away = g["away_team"]
            
            totals = []
            spreads = []
            for bookie in g.get("bookmakers", []):
                for market in bookie.get("markets", []):
                    if market["key"] == "totals":
                        for outcome in market["outcomes"]:
                            if outcome["name"] == "Over":
                                totals.append(outcome.get("point", 0))
                    elif market["key"] == "spreads":
                        for outcome in market["outcomes"]:
                            if outcome["name"] == home:
                                spreads.append(outcome.get("point", 0))
            
            if not totals:
                continue
            
            games.append({
                "home_team": home,
                "away_team": away,
                "posted_total": round(statistics.mean(totals), 1),
                "spread": round(statistics.mean(spreads), 1) if spreads else 0,
                "game_date": target_date.isoformat(),
            })
        
        logger.info(f"Historical odds: {len(games)} games for {target_date}, API remaining: {remaining}")
        return games
    except Exception as e:
        logger.error(f"Historical odds error: {e}")
        return []


def fetch_espn_scores(target_date: date):
    """Fetch actual final scores from ESPN."""
    dt_str = target_date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt_str}"
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
    except Exception as e:
        return {}

    scores = {}
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            continue

        competitors = comp.get("competitors", [])
        home_data = away_data = None
        for c in competitors:
            if c.get("homeAway") == "home":
                home_data = c
            else:
                away_data = c

        if not home_data or not away_data:
            continue

        home_name = home_data["team"].get("displayName", "")
        away_name = away_data["team"].get("displayName", "")
        home_score = int(home_data.get("score", 0))
        away_score = int(away_data.get("score", 0))

        key = f"{away_name}@{home_name}"
        scores[key] = {
            "home_team": home_name,
            "away_team": away_name,
            "home_score": home_score,
            "away_score": away_score,
            "actual_total": home_score + away_score,
        }
    return scores


def match_team(name1, name2):
    """Fuzzy match team names between Odds API and ESPN."""
    # Normalize
    mapping = {
        "LA Clippers": "Los Angeles Clippers",
        "L.A. Clippers": "Los Angeles Clippers",
        "LA Lakers": "Los Angeles Lakers",
        "L.A. Lakers": "Los Angeles Lakers",
    }
    n1 = mapping.get(name1, name1).lower()
    n2 = mapping.get(name2, name2).lower()
    return n1 == n2 or n1 in n2 or n2 in n1


def run_backtest(days_back=21):
    engine = TotalsEngineV2()
    engine.fetch_team_stats()
    engine.fetch_advanced_stats()
    engine.fetch_home_away_splits()
    engine.fetch_recent_form()

    all_results = []
    daily_results = {}
    api_calls = 0

    for i in range(1, days_back + 1):
        d = date.today() - timedelta(days=i)
        
        # Fetch historical odds (costs 1 API call each)
        odds_games = fetch_historical_odds(d)
        api_calls += 1
        time.sleep(0.5)  # Be nice to API
        
        if not odds_games:
            continue

        # Fetch actual scores
        scores = fetch_espn_scores(d)
        if not scores:
            continue

        day_picks = []
        for g in odds_games:
            home = engine._map_team_name(g["home_team"])
            away = engine._map_team_name(g["away_team"])
            posted = g["posted_total"]
            spread = g["spread"]

            # Match with actual score
            actual = None
            for key, sc in scores.items():
                sc_home = engine._map_team_name(sc["home_team"])
                sc_away = engine._map_team_name(sc["away_team"])
                if match_team(home, sc_home) and match_team(away, sc_away):
                    actual = sc["actual_total"]
                    break

            if actual is None:
                continue

            # Run prediction
            pred = engine.predict_total(home, away, posted, spread)

            if pred["pick"] == "PASS":
                continue

            if actual == posted:
                continue  # Push

            actual_result = "OVER" if actual > posted else "UNDER"
            hit = pred["pick"] == actual_result

            result = {
                "date": d.isoformat(),
                "matchup": f"{away} @ {home}",
                "pick": pred["pick"],
                "posted": posted,
                "predicted": pred["predicted_total"],
                "actual": actual,
                "edge": pred["edge"],
                "confidence": pred["confidence"],
                "tier": pred["tier"],
                "hit": hit,
            }
            day_picks.append(result)
            all_results.append(result)

        if day_picks:
            hits = sum(1 for r in day_picks if r["hit"])
            daily_results[d.isoformat()] = {
                "total": len(day_picks),
                "hits": hits,
                "pct": round(100 * hits / len(day_picks), 1),
            }
            logger.info(f"  {d}: {hits}/{len(day_picks)} ({daily_results[d.isoformat()]['pct']}%)")

    logger.info(f"Used {api_calls} historical API calls")
    return all_results, daily_results


def print_report(all_results, daily_results, days_back):
    print(f"\n{'='*80}")
    print(f"  O/U V2 ENGINE BACKTEST — Last {days_back} Days (NBA)")
    print(f"{'='*80}")

    if not all_results:
        print("  No results to report.")
        return 0

    # Daily breakdown
    print(f"\n  {'Date':<14} {'Picks':>6} {'Hits':>6} {'Accuracy':>10}")
    print(f"  {'-'*40}")
    for d in sorted(daily_results.keys()):
        dr = daily_results[d]
        marker = " [PASS]" if dr["pct"] >= 55 else " [FAIL]" if dr["pct"] < 45 else ""
        print(f"  {d:<14} {dr['total']:>6} {dr['hits']:>6} {dr['pct']:>9.1f}%{marker}")

    total = len(all_results)
    hits = sum(1 for r in all_results if r["hit"])
    pct = 100 * hits / total
    print(f"\n  {'OVERALL':<14} {total:>6} {hits:>6} {pct:>9.1f}%")
    print(f"  {'='*40}")

    # By tier
    print(f"\n  BY TIER:")
    for tier in ["STRONG", "VALUE", "LEAN"]:
        subset = [r for r in all_results if r["tier"] == tier]
        if subset:
            h = sum(1 for r in subset if r["hit"])
            p = 100 * h / len(subset)
            print(f"    {tier:<10} {h}/{len(subset)} ({p:.1f}%)")

    # By edge threshold
    print(f"\n  BY EDGE THRESHOLD:")
    for threshold in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        subset = [r for r in all_results if abs(r["edge"]) >= threshold]
        if subset:
            h = sum(1 for r in subset if r["hit"])
            p = 100 * h / len(subset)
            print(f"    Edge >= {threshold:<4} {h}/{len(subset)} ({p:.1f}%)")

    # Over vs Under
    print(f"\n  OVER vs UNDER:")
    for direction in ["OVER", "UNDER"]:
        subset = [r for r in all_results if r["pick"] == direction]
        if subset:
            h = sum(1 for r in subset if r["hit"])
            p = 100 * h / len(subset)
            print(f"    {direction:<10} {h}/{len(subset)} ({p:.1f}%)")

    # Avg edge on hits vs misses
    hit_edges = [abs(r["edge"]) for r in all_results if r["hit"]]
    miss_edges = [abs(r["edge"]) for r in all_results if not r["hit"]]
    if hit_edges:
        print(f"\n  Avg edge on HITS: {statistics.mean(hit_edges):.1f}")
    if miss_edges:
        print(f"  Avg edge on MISSES: {statistics.mean(miss_edges):.1f}")

    # Verdict
    print(f"\n  {'='*40}")
    if pct >= 55:
        print(f"  PASS — {pct:.1f}% overall accuracy meets 55% threshold")
    elif pct >= 52:
        print(f"  MARGINAL — {pct:.1f}% close but below 55%")
    else:
        print(f"  FAIL — {pct:.1f}% below 55% threshold")
    print(f"  {'='*40}")
    return pct


def main():
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 21
    print(f"Running O/U v2 backtest over {days_back} days...")
    all_results, daily_results = run_backtest(days_back)
    pct = print_report(all_results, daily_results, days_back)

    out_path = Path(__file__).parent / "backtest_ou_v2_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "days_back": days_back,
            "overall_pct": round(pct, 1) if pct else 0,
            "total_picks": len(all_results),
            "total_hits": sum(1 for r in all_results if r["hit"]),
            "daily": daily_results,
            "picks": all_results,
        }, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
