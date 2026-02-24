"""
Player Prop Integration for ParlayGuarantee
Pulls player props from Odds API and cross-references with player stats
to find over/under edges.
"""

import sys
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE_URL = "https://api.the-odds-api.com/v4"

# Prop market keys on The Odds API
PROP_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_points_rebounds_assists",
    "player_steals",
    "player_blocks",
    "player_turnovers",
]


def fetch_player_props(sport: str = "basketball_nba", event_id: str = None) -> List[Dict]:
    """Fetch player props from Odds API for all events or a specific event."""
    all_props = []
    
    # First get events
    events_url = f"{BASE_URL}/sports/{sport}/events"
    params = {"apiKey": ODDS_API_KEY}
    
    try:
        resp = requests.get(events_url, params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        return []

    event_ids = [event_id] if event_id else [e["id"] for e in events]
    
    for eid in event_ids[:12]:  # Limit to save API calls
        for market in PROP_MARKETS:
            url = f"{BASE_URL}/sports/{sport}/events/{eid}/odds"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": market,
                "oddsFormat": "american",
            }
            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                
                # Find the event info
                event_info = None
                for e in events:
                    if e["id"] == eid:
                        event_info = e
                        break
                
                for bm in data.get("bookmakers", []):
                    for mkt in bm.get("markets", []):
                        if mkt["key"] != market:
                            continue
                        for outcome in mkt.get("outcomes", []):
                            prop = {
                                "event_id": eid,
                                "home_team": data.get("home_team", ""),
                                "away_team": data.get("away_team", ""),
                                "commence_time": data.get("commence_time", ""),
                                "bookmaker": bm["title"],
                                "market": market,
                                "player": outcome.get("description", outcome.get("name", "")),
                                "name": outcome["name"],  # Over/Under
                                "line": outcome.get("point", 0),
                                "price": outcome.get("price", 0),
                            }
                            all_props.append(prop)
            except Exception as e:
                logger.debug(f"Error fetching {market} for event {eid}: {e}")
                continue

    logger.info(f"Fetched {len(all_props)} player prop lines")
    return all_props


def fetch_player_averages(player_name: str) -> Optional[Dict]:
    """
    Fetch player season averages from NBA API.
    Returns season avg and last-5, last-10 averages.
    """
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats, playergamelog
        from nba_api.stats.static import players
        import time

        # Find player
        matches = players.find_players_by_full_name(player_name)
        if not matches:
            # Try partial match
            parts = player_name.split()
            if len(parts) >= 2:
                matches = players.find_players_by_last_name(parts[-1])
                matches = [m for m in matches if m.get("is_active")]
        if not matches:
            return None

        player_id = matches[0]["id"]
        time.sleep(0.6)  # Rate limit

        # Get game log for current season
        gl = playergamelog.PlayerGameLog(
            player_id=player_id,
            season="2025-26",
            season_type_all_star="Regular Season"
        )
        df = gl.get_data_frames()[0]
        if df.empty:
            return None

        def avg_stats(df_slice):
            return {
                "points": round(df_slice["PTS"].mean(), 1),
                "rebounds": round(df_slice["REB"].mean(), 1),
                "assists": round(df_slice["AST"].mean(), 1),
                "threes": round(df_slice["FG3M"].mean(), 1),
                "steals": round(df_slice["STL"].mean(), 1),
                "blocks": round(df_slice["BLK"].mean(), 1),
                "turnovers": round(df_slice["TOV"].mean(), 1),
                "pra": round((df_slice["PTS"] + df_slice["REB"] + df_slice["AST"]).mean(), 1),
                "games": len(df_slice),
            }

        return {
            "player": player_name,
            "player_id": player_id,
            "season": avg_stats(df),
            "last_5": avg_stats(df.head(5)),
            "last_10": avg_stats(df.head(10)),
        }
    except Exception as e:
        logger.debug(f"Could not fetch stats for {player_name}: {e}")
        return None


# Map market keys to stat keys
MARKET_TO_STAT = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "threes",
    "player_steals": "steals",
    "player_blocks": "blocks",
    "player_turnovers": "turnovers",
    "player_points_rebounds_assists": "pra",
}


def score_props(props: List[Dict], use_nba_api: bool = True) -> List[Dict]:
    """
    Score each prop for over/under edge by comparing line to player averages.
    Returns scored props sorted by edge strength.
    """
    # Group props by player + market
    player_props = {}
    for p in props:
        key = (p["player"], p["market"])
        if key not in player_props:
            player_props[key] = {"over": None, "under": None, "info": p}
        if p["name"] == "Over":
            player_props[key]["over"] = p
        elif p["name"] == "Under":
            player_props[key]["under"] = p

    scored = []
    stats_cache = {}

    for (player, market), data in player_props.items():
        if not data["over"] or not data["under"]:
            continue

        line = data["over"]["line"]
        stat_key = MARKET_TO_STAT.get(market)
        if not stat_key:
            continue

        # Get player averages
        if player not in stats_cache:
            if use_nba_api:
                stats_cache[player] = fetch_player_averages(player)
            else:
                stats_cache[player] = None

        stats = stats_cache.get(player)
        
        if stats:
            season_avg = stats["season"].get(stat_key, line)
            last5_avg = stats["last_5"].get(stat_key, line)
            last10_avg = stats["last_10"].get(stat_key, line)

            # Weighted average: 40% season, 30% last10, 30% last5
            projected = 0.4 * season_avg + 0.3 * last10_avg + 0.3 * last5_avg
            edge = projected - line
            edge_pct = edge / line if line > 0 else 0

            recommendation = "OVER" if edge > 0 else "UNDER"
            confidence = min(abs(edge_pct) * 100, 95)  # Cap at 95

            scored.append({
                "player": player,
                "market": market.replace("player_", "").upper(),
                "line": line,
                "over_odds": data["over"]["price"],
                "under_odds": data["under"]["price"],
                "season_avg": season_avg,
                "last_5_avg": last5_avg,
                "last_10_avg": last10_avg,
                "projected": round(projected, 1),
                "edge": round(edge, 1),
                "edge_pct": round(edge_pct * 100, 1),
                "recommendation": recommendation,
                "confidence": round(confidence, 1),
                "home_team": data["info"]["home_team"],
                "away_team": data["info"]["away_team"],
                "commence_time": data["info"]["commence_time"],
                "bookmaker": data["info"]["bookmaker"],
                "event_id": data["info"]["event_id"],
            })
        else:
            # Without stats, just return the prop info for display
            scored.append({
                "player": player,
                "market": market.replace("player_", "").upper(),
                "line": line,
                "over_odds": data["over"]["price"],
                "under_odds": data["under"]["price"],
                "season_avg": None,
                "projected": None,
                "edge": None,
                "recommendation": None,
                "confidence": 0,
                "home_team": data["info"]["home_team"],
                "away_team": data["info"]["away_team"],
                "commence_time": data["info"]["commence_time"],
                "bookmaker": data["info"]["bookmaker"],
                "event_id": data["info"]["event_id"],
            })

    scored.sort(key=lambda x: abs(x.get("edge") or 0), reverse=True)
    logger.info(f"Scored {len(scored)} player props")
    return scored


def run(sport: str = "basketball_nba", use_nba_api: bool = True) -> Dict:
    """Full pipeline."""
    logger.info("Starting player props engine...")
    props = fetch_player_props(sport)
    scored = score_props(props, use_nba_api=use_nba_api)

    # Split into strong edges and all
    strong = [s for s in scored if s.get("confidence", 0) >= 15]

    return {
        "generated_at": datetime.now().isoformat(),
        "sport": sport,
        "total_props_fetched": len(props),
        "total_scored": len(scored),
        "strong_edges": len(strong),
        "props": scored,
        "top_picks": strong[:20],
    }


def main():
    parser = argparse.ArgumentParser(description="Player Props Engine")
    parser.add_argument("--sport", default="basketball_nba")
    parser.add_argument("--no-nba-api", action="store_true", help="Skip NBA API stats lookup")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    result = run(sport=args.sport, use_nba_api=not args.no_nba_api)
    output = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        logger.info(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
