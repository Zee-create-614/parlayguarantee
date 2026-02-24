"""
Live/In-Game Adjustments Engine for ParlayGuarantee
Compares pre-game model predictions vs live state, flags favorable line moves,
and generates mid-game value picks.
"""

import sys
import json
import logging
import argparse
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from moneyline_parlay import american_to_decimal, implied_probability, kelly_criterion

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE_URL = "https://api.the-odds-api.com/v4"


def fetch_live_odds(sport: str = "basketball_nba") -> List[Dict]:
    """Fetch live/in-play odds from Odds API."""
    url = f"{BASE_URL}/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch live odds: {e}")
        return []


def fetch_espn_live_scores(sport: str = "nba") -> List[Dict]:
    """Fetch live scores from ESPN API as fallback."""
    sport_map = {
        "nba": "basketball/nba",
        "basketball_nba": "basketball/nba",
        "nhl": "hockey/nhl",
        "mlb": "baseball/mlb",
    }
    espn_sport = sport_map.get(sport, "basketball/nba")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/scoreboard"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        games = []
        for event in data.get("events", []):
            competition = event["competitions"][0]
            teams = competition["competitors"]
            
            home = away = None
            for t in teams:
                info = {
                    "team": t["team"]["displayName"],
                    "abbreviation": t["team"]["abbreviation"],
                    "score": int(t.get("score", 0)),
                    "home_away": t["homeAway"],
                }
                if t["homeAway"] == "home":
                    home = info
                else:
                    away = info

            status = competition.get("status", {})
            period = status.get("period", 0)
            clock = status.get("displayClock", "")
            state = status.get("type", {}).get("name", "")  # STATUS_SCHEDULED, STATUS_IN_PROGRESS, STATUS_FINAL

            if home and away:
                games.append({
                    "home_team": home["team"],
                    "away_team": away["team"],
                    "home_score": home["score"],
                    "away_score": away["score"],
                    "period": period,
                    "clock": clock,
                    "status": state,
                    "score_diff": home["score"] - away["score"],
                })
        return games
    except Exception as e:
        logger.error(f"Failed to fetch ESPN scores: {e}")
        return []


def compare_pregame_vs_live(analyzed_games: List[Dict], live_odds: List[Dict],
                             live_scores: List[Dict]) -> List[Dict]:
    """
    Compare pre-game model predictions against current live state.
    Flag games where line has moved favorably.
    """
    alerts = []
    
    # Index live odds by teams
    live_odds_lookup = {}
    for event in live_odds:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        live_odds_lookup[f"{away} @ {home}"] = event
        live_odds_lookup[home] = event
        live_odds_lookup[away] = event

    # Index live scores
    scores_lookup = {}
    for score in live_scores:
        scores_lookup[score["home_team"]] = score
        scores_lookup[score["away_team"]] = score

    for game in analyzed_games:
        home = game.get("home_team", game.get("home", ""))
        away = game.get("away_team", game.get("away", ""))
        predicted_winner = game.get("predicted_winner", game.get("pick", ""))
        
        if "ml_home_prob" in game:
            pregame_prob = game["ml_home_prob"] if predicted_winner == home else game["ml_away_prob"]
        else:
            pregame_prob = game.get("win_prob", game.get("confidence", 50) / 100)
        if pregame_prob > 1:
            pregame_prob /= 100
        
        game_key = f"{away} @ {home}"
        live_event = live_odds_lookup.get(game_key) or live_odds_lookup.get(home)
        live_score = scores_lookup.get(home) or scores_lookup.get(away)

        if not live_event:
            continue

        # Get current live moneyline for our predicted winner
        current_ml = None
        current_book = ""
        for bm in live_event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] != "h2h":
                    continue
                for outcome in mkt.get("outcomes", []):
                    if outcome["name"] == predicted_winner:
                        current_ml = outcome["price"]
                        current_book = bm["title"]
                        break

        if current_ml is None:
            continue

        current_decimal = american_to_decimal(current_ml)
        current_implied = implied_probability(current_ml)

        # Compare: is live line better than our pre-game model?
        line_value = pregame_prob - current_implied  # positive = favorable
        
        alert_type = None
        urgency = "low"
        
        if line_value >= 0.10:
            alert_type = "STRONG_VALUE"
            urgency = "high"
        elif line_value >= 0.05:
            alert_type = "VALUE"
            urgency = "medium"
        elif line_value >= 0.03:
            alert_type = "SLIGHT_VALUE"
            urgency = "low"

        # Check if game is live and score supports our pick
        game_state = "pre-game"
        score_context = None
        if live_score and live_score["status"] == "STATUS_IN_PROGRESS":
            game_state = f"Q{live_score['period']} {live_score['clock']}"
            score_context = {
                "home_score": live_score["home_score"],
                "away_score": live_score["away_score"],
                "score_diff": live_score["score_diff"],
                "predicted_winning": (
                    (predicted_winner == home and live_score["score_diff"] > 0) or
                    (predicted_winner == away and live_score["score_diff"] < 0)
                ),
            }
            
            # If our pick is trailing but line is favorable, it's a BET NOW moment
            if score_context and not score_context["predicted_winning"] and line_value >= 0.05:
                alert_type = "BET_NOW"
                urgency = "critical"

        if alert_type:
            alerts.append({
                "game": game_key,
                "predicted_winner": predicted_winner,
                "pregame_model_prob": round(pregame_prob, 4),
                "current_live_odds": current_ml,
                "current_implied_prob": round(current_implied, 4),
                "line_value": round(line_value, 4),
                "line_value_pct": f"{round(line_value * 100, 1)}%",
                "alert_type": alert_type,
                "urgency": urgency,
                "game_state": game_state,
                "score": score_context,
                "bookmaker": current_book,
                "kelly_size": round(kelly_criterion(pregame_prob, current_decimal), 4),
                "commence_time": live_event.get("commence_time", ""),
            })

    alerts.sort(key=lambda x: x["line_value"], reverse=True)
    return alerts


def generate_live_picks(alerts: List[Dict]) -> List[Dict]:
    """Generate actionable mid-game picks from alerts."""
    picks = []
    for alert in alerts:
        if alert["urgency"] in ("high", "critical"):
            picks.append({
                "action": "BET" if alert["alert_type"] == "BET_NOW" else "CONSIDER",
                "team": alert["predicted_winner"],
                "game": alert["game"],
                "odds": alert["current_live_odds"],
                "model_edge": alert["line_value_pct"],
                "urgency": alert["urgency"],
                "game_state": alert["game_state"],
                "score": alert.get("score"),
                "recommended_size": f"{round(alert['kelly_size'] * 100, 1)}% bankroll",
            })
    return picks


def run(analyzed_games: List[Dict] = None, sport: str = "basketball_nba") -> Dict:
    """Full live adjustments pipeline."""
    logger.info("Starting live adjustments engine...")
    analyzed_games = analyzed_games or []
    
    live_odds = fetch_live_odds(sport)
    
    espn_sport = sport.replace("basketball_", "").replace("icehockey_", "").replace("baseball_", "")
    live_scores = fetch_espn_live_scores(espn_sport)
    
    alerts = compare_pregame_vs_live(analyzed_games, live_odds, live_scores)
    picks = generate_live_picks(alerts)
    
    critical = [a for a in alerts if a["urgency"] == "critical"]
    high = [a for a in alerts if a["urgency"] == "high"]

    return {
        "generated_at": datetime.now().isoformat(),
        "sport": sport,
        "games_analyzed": len(analyzed_games),
        "live_games": len([s for s in live_scores if s["status"] == "STATUS_IN_PROGRESS"]),
        "total_alerts": len(alerts),
        "critical_alerts": len(critical),
        "high_alerts": len(high),
        "alerts": alerts,
        "live_picks": picks,
        "live_scores": live_scores,
    }


def main():
    parser = argparse.ArgumentParser(description="Live Adjustments Engine")
    parser.add_argument("--sport", default="basketball_nba")
    parser.add_argument("--games-file", default="analyzed_games.json")
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

    result = run(analyzed_games, args.sport)
    output = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        logger.info(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
