"""
Moneyline Parlay Engine for ParlayGuarantee
Uses the 38-factor model's win probabilities + real Odds API odds
to identify moneyline value and build optimal parlays.
"""

import sys
import json
import math
import logging
import argparse
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any
from itertools import combinations

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from odds_fetcher import OddsFetcher

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"


def american_to_decimal(american: float) -> float:
    """Convert American odds to decimal odds."""
    if american > 0:
        return 1 + american / 100
    else:
        return 1 + 100 / abs(american)


def decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal odds to American odds."""
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    else:
        return round(-100 / (decimal_odds - 1))


def implied_probability(american: float) -> float:
    """Convert American odds to implied probability."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def kelly_criterion(win_prob: float, decimal_odds: float, fraction: float = 0.25) -> float:
    """
    Kelly criterion for bankroll sizing.
    fraction: fractional Kelly (0.25 = quarter Kelly, conservative)
    """
    b = decimal_odds - 1  # net payout
    q = 1 - win_prob
    kelly = (b * win_prob - q) / b
    return max(0, kelly * fraction)


def kelly_parlay(leg_probs: List[float], parlay_decimal: float, fraction: float = 0.25) -> float:
    """Kelly criterion for a parlay bet."""
    combined_prob = 1.0
    for p in leg_probs:
        combined_prob *= p
    return kelly_criterion(combined_prob, parlay_decimal, fraction)


class MoneylineParlay:
    """
    Identifies moneyline value bets and constructs optimal parlays.
    """

    def __init__(self, analyzed_games: List[Dict] = None):
        self.odds_fetcher = OddsFetcher(api_key=ODDS_API_KEY)
        self.analyzed_games = analyzed_games or []
        self.moneyline_odds = {}  # team -> {american, decimal, implied_prob, bookmaker}

    def fetch_live_moneyline_odds(self, sport: str = "basketball_nba") -> Dict:
        """Fetch current moneyline odds from Odds API."""
        endpoint = f"/sports/{sport}/odds"
        params = {
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "american"
        }
        data = self.odds_fetcher.make_request(endpoint, params)
        if not data:
            logger.warning("No odds data returned from API")
            return {}

        odds_by_game = {}
        for event in data:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            game_key = f"{away} @ {home}"
            commence = event.get("commence_time", "")

            best_home = None
            best_away = None
            best_home_book = ""
            best_away_book = ""

            for bm in event.get("bookmakers", []):
                for market in bm.get("markets", []):
                    if market["key"] != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        price = outcome["price"]
                        if outcome["name"] == home:
                            if best_home is None or price > best_home:
                                best_home = price
                                best_home_book = bm["title"]
                        elif outcome["name"] == away:
                            if best_away is None or price > best_away:
                                best_away = price
                                best_away_book = bm["title"]

            if best_home is not None and best_away is not None:
                odds_by_game[game_key] = {
                    "home_team": home,
                    "away_team": away,
                    "commence_time": commence,
                    "home": {
                        "american": best_home,
                        "decimal": american_to_decimal(best_home),
                        "implied_prob": implied_probability(best_home),
                        "bookmaker": best_home_book,
                    },
                    "away": {
                        "american": best_away,
                        "decimal": american_to_decimal(best_away),
                        "implied_prob": implied_probability(best_away),
                        "bookmaker": best_away_book,
                    },
                }
        self.moneyline_odds = odds_by_game
        logger.info(f"Fetched moneyline odds for {len(odds_by_game)} games")
        return odds_by_game

    def find_value_bets(self, min_edge: float = 0.03) -> List[Dict]:
        """
        Compare model win probabilities against market implied probabilities.
        A value bet exists when model_prob > market_implied_prob + min_edge.
        """
        value_bets = []

        for game in self.analyzed_games:
            home = game.get("home_team", game.get("home", ""))
            away = game.get("away_team", game.get("away", ""))
            game_key = f"{away} @ {home}"

            odds = self.moneyline_odds.get(game_key)
            if not odds:
                # Try reverse key
                for k, v in self.moneyline_odds.items():
                    if v["home_team"] == home and v["away_team"] == away:
                        odds = v
                        break
            if not odds:
                continue

            # Model probabilities — support both field naming conventions
            if "ml_home_prob" in game:
                model_home_prob = game["ml_home_prob"]
                model_away_prob = game["ml_away_prob"]
            elif "home_probability" in game:
                model_home_prob = game["home_probability"]
                model_away_prob = 1 - model_home_prob
            else:
                model_home_prob = game.get("win_prob", 0.5)
                model_away_prob = 1 - model_home_prob
                if game.get("predicted_winner", game.get("pick")) == away:
                    model_away_prob = model_home_prob
                    model_home_prob = 1 - model_away_prob

            # Check home value
            home_edge = model_home_prob - odds["home"]["implied_prob"]
            if home_edge >= min_edge:
                value_bets.append({
                    "team": home,
                    "opponent": away,
                    "side": "home",
                    "model_prob": round(model_home_prob, 4),
                    "market_implied": round(odds["home"]["implied_prob"], 4),
                    "edge": round(home_edge, 4),
                    "american_odds": odds["home"]["american"],
                    "decimal_odds": round(odds["home"]["decimal"], 3),
                    "bookmaker": odds["home"]["bookmaker"],
                    "kelly_size": round(kelly_criterion(model_home_prob, odds["home"]["decimal"]), 4),
                    "commence_time": odds.get("commence_time", ""),
                })

            # Check away value
            away_edge = model_away_prob - odds["away"]["implied_prob"]
            if away_edge >= min_edge:
                value_bets.append({
                    "team": away,
                    "opponent": home,
                    "side": "away",
                    "model_prob": round(model_away_prob, 4),
                    "market_implied": round(odds["away"]["implied_prob"], 4),
                    "edge": round(away_edge, 4),
                    "american_odds": odds["away"]["american"],
                    "decimal_odds": round(odds["away"]["decimal"], 3),
                    "bookmaker": odds["away"]["bookmaker"],
                    "kelly_size": round(kelly_criterion(model_away_prob, odds["away"]["decimal"]), 4),
                    "commence_time": odds.get("commence_time", ""),
                })

        value_bets.sort(key=lambda x: x["edge"], reverse=True)
        logger.info(f"Found {len(value_bets)} moneyline value bets")
        return value_bets

    def build_parlays(self, value_bets: List[Dict], max_legs: int = 4) -> Dict[str, List[Dict]]:
        """
        Build 2-leg, 3-leg, and 4-leg parlays from value bets.
        Returns dict keyed by parlay size.
        """
        results = {}
        for n in range(2, max_legs + 1):
            if len(value_bets) < n:
                results[f"{n}_leg"] = []
                continue

            parlays = []
            for combo in combinations(value_bets, n):
                # Skip if same game appears twice
                teams_used = set()
                skip = False
                for leg in combo:
                    if leg["team"] in teams_used or leg["opponent"] in teams_used:
                        skip = True
                        break
                    teams_used.add(leg["team"])
                    teams_used.add(leg["opponent"])
                if skip:
                    continue

                parlay_decimal = 1.0
                combined_prob = 1.0
                legs_info = []

                for leg in combo:
                    parlay_decimal *= leg["decimal_odds"]
                    combined_prob *= leg["model_prob"]
                    legs_info.append({
                        "team": leg["team"],
                        "opponent": leg["opponent"],
                        "american_odds": leg["american_odds"],
                        "model_prob": leg["model_prob"],
                        "edge": leg["edge"],
                    })

                ev = combined_prob * parlay_decimal - 1  # expected value per $1
                parlay_kelly = kelly_parlay(
                    [l["model_prob"] for l in combo],
                    parlay_decimal
                )

                parlays.append({
                    "legs": legs_info,
                    "num_legs": n,
                    "parlay_decimal_odds": round(parlay_decimal, 3),
                    "parlay_american_odds": decimal_to_american(parlay_decimal),
                    "combined_prob": round(combined_prob, 4),
                    "expected_value": round(ev, 4),
                    "ev_percent": f"{round(ev * 100, 1)}%",
                    "kelly_size": round(parlay_kelly, 4),
                    "payout_per_dollar": f"${round(parlay_decimal, 2)}",
                })

            # Sort by EV descending
            parlays.sort(key=lambda x: x["expected_value"], reverse=True)
            results[f"{n}_leg"] = parlays[:10]  # Top 10 for each size

        return results

    def run(self, sport: str = "basketball_nba", min_edge: float = 0.03) -> Dict:
        """Full pipeline: fetch odds, find value, build parlays."""
        logger.info("Starting moneyline parlay engine...")
        
        odds = self.fetch_live_moneyline_odds(sport)
        if not odds:
            return {"error": "Could not fetch odds", "value_bets": [], "parlays": {}}

        value_bets = self.find_value_bets(min_edge)
        parlays = self.build_parlays(value_bets)

        total_parlays = sum(len(v) for v in parlays.values())
        
        result = {
            "generated_at": datetime.now().isoformat(),
            "sport": sport,
            "games_analyzed": len(self.analyzed_games),
            "games_with_odds": len(odds),
            "value_bets": value_bets,
            "num_value_bets": len(value_bets),
            "parlays": parlays,
            "total_parlays": total_parlays,
            "min_edge_threshold": min_edge,
        }
        
        logger.info(f"Moneyline engine complete: {len(value_bets)} value bets, {total_parlays} parlays")
        return result


def main():
    parser = argparse.ArgumentParser(description="Moneyline Parlay Engine")
    parser.add_argument("--sport", default="basketball_nba")
    parser.add_argument("--min-edge", type=float, default=0.03)
    parser.add_argument("--games-file", default="analyzed_games.json",
                        help="Path to analyzed games JSON from engine_v2")
    parser.add_argument("--output", default=None, help="Output JSON file")
    args = parser.parse_args()

    # Load analyzed games
    try:
        with open(args.games_file, 'r') as f:
            analyzed_games = json.load(f)
        if not isinstance(analyzed_games, list):
            analyzed_games = [analyzed_games]
    except FileNotFoundError:
        logger.warning(f"No games file found at {args.games_file}, running with empty games")
        analyzed_games = []

    engine = MoneylineParlay(analyzed_games=analyzed_games)
    result = engine.run(sport=args.sport, min_edge=args.min_edge)

    output = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        logger.info(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
