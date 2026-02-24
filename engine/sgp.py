"""
Same Game Parlay (SGP) Engine for ParlayGuarantee
Combines spread/moneyline picks with correlated player props from the same game.
Accounts for correlation adjustments.
"""

import sys
import json
import logging
import argparse
import math
from datetime import datetime
from typing import Dict, List, Optional, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from moneyline_parlay import MoneylineParlay, american_to_decimal, decimal_to_american, implied_probability, kelly_criterion, ODDS_API_KEY
from player_props import fetch_player_props, score_props

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Correlation factors: how correlated are prop outcomes with game outcomes
# Positive = if team wins/covers, this prop is more likely to hit over
CORRELATION_MATRIX = {
    # (team_wins, player_on_winning_team)
    ("win", "POINTS", True): 0.35,      # Star on winning team likely scores more
    ("win", "ASSISTS", True): 0.25,
    ("win", "REBOUNDS", True): 0.10,     # Weak correlation
    ("win", "THREES", True): 0.30,
    ("win", "PRA", True): 0.35,
    ("win", "STEALS", True): 0.15,
    ("win", "BLOCKS", True): 0.10,
    ("win", "TURNOVERS", True): -0.10,   # Winners have fewer turnovers
    # Player on losing team
    ("win", "POINTS", False): -0.15,     # Loser's star may score in garbage time though
    ("win", "ASSISTS", False): -0.20,
    ("win", "REBOUNDS", False): 0.05,    # Losing team gets more defensive rebounds sometimes
    ("win", "THREES", False): -0.15,
    ("win", "PRA", False): -0.10,
    ("win", "STEALS", False): -0.10,
    ("win", "BLOCKS", False): 0.0,
    ("win", "TURNOVERS", False): 0.15,   # Losers turn it over more
}


def adjust_prop_probability(base_prob: float, game_outcome_prob: float,
                            market: str, player_on_predicted_winner: bool,
                            direction: str = "OVER") -> float:
    """
    Adjust prop probability based on correlation with game outcome.
    
    base_prob: base over/under probability from prop line
    game_outcome_prob: model probability that predicted team wins
    market: POINTS, REBOUNDS, etc.
    player_on_predicted_winner: is this player on the team we think wins?
    direction: OVER or UNDER
    """
    corr_key = ("win", market, player_on_predicted_winner)
    correlation = CORRELATION_MATRIX.get(corr_key, 0.0)
    
    if direction == "UNDER":
        correlation = -correlation
    
    # Bayesian-ish adjustment: shift probability based on correlation and game certainty
    game_certainty = abs(game_outcome_prob - 0.5) * 2  # 0 to 1
    adjustment = correlation * game_certainty * 0.15  # Scale down to keep reasonable
    
    adjusted = base_prob + adjustment
    return max(0.05, min(0.95, adjusted))


def build_sgp_for_game(game: Dict, game_odds: Dict, props: List[Dict],
                        max_props: int = 2) -> List[Dict]:
    """
    Build SGP suggestions for a single game.
    Combines the moneyline/spread pick with 1-2 correlated props.
    """
    sgps = []
    
    home = game.get("home_team", game.get("home", ""))
    away = game.get("away_team", game.get("away", ""))
    predicted_winner = game.get("predicted_winner", game.get("pick", ""))
    
    # Get win probability for predicted winner
    if "ml_home_prob" in game:
        win_prob = game["ml_home_prob"] if predicted_winner == home else game["ml_away_prob"]
    else:
        win_prob = game.get("win_prob", game.get("confidence", 50) / 100)
    if win_prob > 1:
        win_prob = win_prob / 100

    # Game-level moneyline leg
    if predicted_winner == home and game_odds:
        ml_odds = game_odds.get("home", {})
    elif game_odds:
        ml_odds = game_odds.get("away", {})
    else:
        ml_odds = {"american": -110, "decimal": 1.909}
    
    ml_leg = {
        "type": "moneyline",
        "team": predicted_winner,
        "american_odds": ml_odds.get("american", -110),
        "decimal_odds": ml_odds.get("decimal", 1.909),
        "model_prob": round(win_prob, 4),
    }

    # Find props for this game
    game_props = [p for p in props if 
                  (p.get("home_team") == home and p.get("away_team") == away) or
                  (p.get("home_team") == away and p.get("away_team") == home)]
    
    # Only use props with a recommendation
    scored_props = [p for p in game_props if p.get("recommendation") and p.get("confidence", 0) > 10]
    scored_props.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    if not scored_props:
        return []

    # Build SGPs: moneyline + 1 prop, moneyline + 2 props
    for n_props in range(1, min(max_props + 1, len(scored_props) + 1)):
        selected_props = scored_props[:n_props]
        
        sgp_legs = [ml_leg]
        combined_decimal = ml_leg["decimal_odds"]
        combined_prob = win_prob
        
        for prop in selected_props:
            is_on_winner = (predicted_winner in [prop.get("home_team"), prop.get("away_team")])
            # Determine if player is on predicted winner's team
            # This is approximate - player name doesn't directly map to team
            # We'll assume player props from the game are 50/50 split
            player_on_winner = True  # Simplified; in production, map player to team

            direction = prop["recommendation"]
            prop_odds = prop["over_odds"] if direction == "OVER" else prop["under_odds"]
            prop_decimal = american_to_decimal(prop_odds)
            
            base_prob = 1 / prop_decimal  # naive implied
            adj_prob = adjust_prop_probability(
                base_prob, win_prob, prop["market"],
                player_on_winner, direction
            )

            # SGP correlation penalty (books apply ~10-20% per correlated leg)
            correlation_penalty = 0.90  # 10% penalty per additional leg
            adj_decimal = prop_decimal * correlation_penalty
            
            sgp_legs.append({
                "type": "player_prop",
                "player": prop["player"],
                "market": prop["market"],
                "line": prop["line"],
                "direction": direction,
                "american_odds": prop_odds,
                "decimal_odds": round(adj_decimal, 3),
                "base_prob": round(base_prob, 4),
                "adjusted_prob": round(adj_prob, 4),
                "confidence": prop["confidence"],
                "edge": prop.get("edge"),
                "projected": prop.get("projected"),
                "season_avg": prop.get("season_avg"),
            })

            combined_decimal *= adj_decimal
            combined_prob *= adj_prob

        ev = combined_prob * combined_decimal - 1

        sgps.append({
            "game": f"{away} @ {home}",
            "num_legs": len(sgp_legs),
            "legs": sgp_legs,
            "sgp_decimal_odds": round(combined_decimal, 3),
            "sgp_american_odds": decimal_to_american(combined_decimal),
            "combined_prob": round(combined_prob, 4),
            "expected_value": round(ev, 4),
            "ev_percent": f"{round(ev * 100, 1)}%",
            "kelly_size": round(kelly_criterion(combined_prob, combined_decimal), 4),
            "commence_time": game_props[0].get("commence_time", "") if game_props else "",
        })

    return sgps


def run(analyzed_games: List[Dict] = None, sport: str = "basketball_nba",
        use_nba_api: bool = False) -> Dict:
    """Full SGP pipeline."""
    logger.info("Starting SGP engine...")
    
    analyzed_games = analyzed_games or []
    
    # Fetch moneyline odds
    ml_engine = MoneylineParlay(analyzed_games)
    ml_odds = ml_engine.fetch_live_moneyline_odds(sport)
    
    # Fetch player props
    raw_props = fetch_player_props(sport)
    scored_props = score_props(raw_props, use_nba_api=use_nba_api)
    
    all_sgps = []
    for game in analyzed_games:
        home = game.get("home_team", game.get("home", ""))
        away = game.get("away_team", game.get("away", ""))
        game_key = f"{away} @ {home}"
        
        game_odds = ml_odds.get(game_key)
        if not game_odds:
            for k, v in ml_odds.items():
                if v["home_team"] == home and v["away_team"] == away:
                    game_odds = v
                    break
        
        sgps = build_sgp_for_game(game, game_odds, scored_props)
        all_sgps.extend(sgps)

    # Sort by EV
    all_sgps.sort(key=lambda x: x["expected_value"], reverse=True)
    positive_ev = [s for s in all_sgps if s["expected_value"] > 0]

    return {
        "generated_at": datetime.now().isoformat(),
        "sport": sport,
        "games_analyzed": len(analyzed_games),
        "total_sgps": len(all_sgps),
        "positive_ev_sgps": len(positive_ev),
        "sgps": all_sgps,
        "top_sgps": all_sgps[:10],
    }


def main():
    parser = argparse.ArgumentParser(description="Same Game Parlay Engine")
    parser.add_argument("--sport", default="basketball_nba")
    parser.add_argument("--games-file", default="analyzed_games.json")
    parser.add_argument("--no-nba-api", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    try:
        with open(args.games_file, 'r') as f:
            analyzed_games = json.load(f)
        if not isinstance(analyzed_games, list):
            analyzed_games = [analyzed_games]
    except FileNotFoundError:
        logger.warning(f"No games file at {args.games_file}")
        analyzed_games = []

    result = run(analyzed_games, args.sport, use_nba_api=not args.no_nba_api)
    output = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        logger.info(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
