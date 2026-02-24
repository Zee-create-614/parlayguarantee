"""
Live Game Monitor — Continuous in-game tracker for ParlayGuarantee
Runs every N minutes, fetches live odds + scores, runs value detection,
saves snapshots and maintains an alerts log.

Usage:
  python live_game_monitor.py --date 2026-02-20 --interval 600
  python live_game_monitor.py --date 2026-02-20 --once   # single snapshot, no loop
"""
import sys, os, json, time, argparse, requests, logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DIR = os.path.dirname(os.path.abspath(__file__))
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE_URL = "https://api.the-odds-api.com/v4"
EST = timezone(timedelta(hours=-5))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def fetch_live_odds(sport="basketball_nba"):
    """Fetch live odds from Odds API, all bookmakers."""
    try:
        r = requests.get(f"{BASE_URL}/sports/{sport}/odds/", params={
            "apiKey": ODDS_API_KEY, "regions": "us",
            "markets": "h2h,spreads,totals", "oddsFormat": "american",
        }, timeout=20)
        r.raise_for_status()
        remaining = r.headers.get("x-requests-remaining", "?")
        logger.info(f"Odds API: {len(r.json())} events, {remaining} calls remaining")
        return r.json()
    except Exception as e:
        logger.error(f"Odds API error: {e}")
        return []


def fetch_dk_odds(sport="basketball_nba"):
    """Fetch DraftKings-specific odds."""
    try:
        r = requests.get(f"{BASE_URL}/sports/{sport}/odds/", params={
            "apiKey": ODDS_API_KEY, "regions": "us",
            "markets": "h2h,spreads,totals", "oddsFormat": "american",
            "bookmakers": "draftkings",
        }, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"DK odds error: {e}")
        return []


def fetch_espn_scores(sport="nba"):
    """Fetch live scores from ESPN."""
    sport_path = {
        "nba": "basketball/nba",
        "ncaab": "basketball/mens-college-basketball",
    }.get(sport, "basketball/nba")
    try:
        r = requests.get(
            f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard",
            timeout=10)
        r.raise_for_status()
        data = r.json()
        games = []
        for ev in data.get("events", []):
            comp = ev["competitions"][0]
            teams = comp["competitors"]
            home = away = None
            for t in teams:
                info = {
                    "team": t["team"]["displayName"],
                    "abbr": t["team"]["abbreviation"],
                    "score": int(t.get("score", 0)),
                }
                if t["homeAway"] == "home":
                    home = info
                else:
                    away = info
            status = comp.get("status", {})
            period = status.get("period", 0)
            clock = status.get("displayClock", "")
            state = status.get("type", {}).get("name", "")
            if home and away:
                games.append({
                    "home_team": home["team"], "away_team": away["team"],
                    "home_abbr": home["abbr"], "away_abbr": away["abbr"],
                    "home_score": home["score"], "away_score": away["score"],
                    "period": period, "clock": clock, "status": state,
                })
        return games
    except Exception as e:
        logger.error(f"ESPN error: {e}")
        return []


def extract_dk_lines(dk_events):
    """Extract DraftKings lines into a lookup dict keyed by home_team."""
    dk = {}
    for ev in dk_events:
        home = ev.get("home_team", "")
        entry = {"home_team": home, "away_team": ev.get("away_team", ""), "markets": {}}
        for bm in ev.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                outcomes = {}
                for o in mkt.get("outcomes", []):
                    outcomes[o["name"]] = {"price": o.get("price"), "point": o.get("point")}
                entry["markets"][mkt["key"]] = outcomes
        dk[home] = entry
    return dk


def load_pregame_picks(date_str):
    """Load pre-game analyzed picks for comparison."""
    paths = [
        os.path.join(DIR, "analyzed_games.json"),
        os.path.join(DIR, f"snapshot_closing_{date_str}.json"),
    ]
    for p in paths:
        try:
            with open(p) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            # snapshot format
            if "nba_upset" in data:
                return data["nba_upset"]
            if "nba_pure" in data:
                return data["nba_pure"]
        except:
            continue
    return []


def find_value_alerts(pregame_picks, live_odds, scores):
    """Compare pre-game picks vs live state to find value."""
    alerts = []
    # Index scores by team name
    score_map = {}
    for s in scores:
        score_map[s["home_team"]] = s
        score_map[s["away_team"]] = s

    # Index live odds by home team
    odds_map = {}
    for ev in live_odds:
        odds_map[ev.get("home_team", "")] = ev

    for pick in pregame_picks:
        home = pick.get("home_team", pick.get("home", ""))
        away = pick.get("away_team", pick.get("away", ""))
        predicted = pick.get("predicted_winner", pick.get("pick", ""))
        pregame_prob = pick.get("win_prob", pick.get("confidence", 50))
        if isinstance(pregame_prob, (int, float)) and pregame_prob > 1:
            pregame_prob /= 100

        ev = odds_map.get(home)
        if not ev:
            continue

        # Find current ML for our pick
        current_ml = None
        for bm in ev.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] != "h2h":
                    continue
                for o in mkt.get("outcomes", []):
                    if o["name"] == predicted:
                        current_ml = o["price"]
                        break
                if current_ml:
                    break
            if current_ml:
                break

        if current_ml is None:
            continue

        # Implied prob
        if current_ml < 0:
            implied = abs(current_ml) / (abs(current_ml) + 100)
        else:
            implied = 100 / (current_ml + 100)

        edge = pregame_prob - implied
        score = score_map.get(home)

        if edge >= 0.03:
            alert = {
                "timestamp": datetime.now(EST).isoformat(),
                "game": f"{away} @ {home}",
                "alert_type": "STRONG_VALUE" if edge >= 0.10 else "VALUE" if edge >= 0.05 else "SLIGHT_VALUE",
                "pre_game_pick": predicted,
                "pre_game_prob": round(pregame_prob, 4),
                "live_line": current_ml,
                "live_implied": round(implied, 4),
                "edge": round(edge, 4),
                "dk_line": None,  # filled below
                "recommended_action": "BET" if edge >= 0.08 else "WATCH",
            }
            if score:
                alert["score"] = f"{score['away_team']} {score['away_score']} - {score['home_team']} {score['home_score']}"
                alert["period"] = score.get("period")
                alert["clock"] = score.get("clock")
                alert["game_status"] = score.get("status")
                # Trailing pick = extra value
                if score["status"] == "STATUS_IN_PROGRESS":
                    our_team_home = predicted == home
                    trailing = (our_team_home and score["home_score"] < score["away_score"]) or \
                               (not our_team_home and score["away_score"] < score["home_score"])
                    if trailing and edge >= 0.05:
                        alert["alert_type"] = "BET_NOW_TRAILING"
                        alert["recommended_action"] = "BET"
            alerts.append(alert)

    return alerts


def fill_dk_lines(alerts, dk_lookup):
    """Fill DK-specific lines into alerts."""
    for alert in alerts:
        game = alert["game"]
        # Extract home team from "AWAY @ HOME"
        parts = game.split(" @ ")
        if len(parts) == 2:
            home = parts[1]
            dk = dk_lookup.get(home, {})
            h2h = dk.get("markets", {}).get("h2h", {})
            pick_data = h2h.get(alert["pre_game_pick"])
            if pick_data:
                alert["dk_line"] = pick_data.get("price")


def take_snapshot(date_str, once=False):
    """Take a single snapshot: odds + scores + value alerts."""
    now = datetime.now(EST)
    ts = now.strftime("%Y%m%d_%H%M%S")
    snap_dir = ensure_dir(os.path.join(DIR, "live_data", date_str))

    logger.info(f"--- Snapshot {ts} ---")

    # Fetch data
    live_odds = fetch_live_odds("basketball_nba")
    dk_events = fetch_dk_odds("basketball_nba")
    scores = fetch_espn_scores("nba")
    pregame = load_pregame_picks(date_str)

    dk_lookup = extract_dk_lines(dk_events)

    # Value alerts
    alerts = find_value_alerts(pregame, live_odds, scores)
    fill_dk_lines(alerts, dk_lookup)

    # Build snapshot
    snapshot = {
        "timestamp": now.isoformat(),
        "date": date_str,
        "odds_events": len(live_odds),
        "scores_count": len(scores),
        "pregame_picks_loaded": len(pregame),
        "odds": [],
        "scores": scores,
        "value_alerts": alerts,
        "dk_lines": {},
    }

    # Summarize odds per game (all books + highlight DK)
    for ev in live_odds:
        home = ev.get("home_team", "")
        away = ev.get("away_team", "")
        game_odds = {"home": home, "away": away, "bookmakers": {}}
        for bm in ev.get("bookmakers", []):
            book_data = {}
            for mkt in bm.get("markets", []):
                book_data[mkt["key"]] = [
                    {"name": o["name"], "price": o.get("price"), "point": o.get("point")}
                    for o in mkt.get("outcomes", [])
                ]
            game_odds["bookmakers"][bm["title"]] = book_data
        # DK highlight
        dk = dk_lookup.get(home)
        if dk:
            game_odds["draftkings"] = dk.get("markets", {})
        snapshot["odds"].append(game_odds)

    # Pregame comparison
    snapshot["pregame_picks"] = [
        {"pick": p.get("pick", p.get("predicted_winner")),
         "home": p.get("home", p.get("home_team")),
         "away": p.get("away", p.get("away_team")),
         "win_prob": p.get("win_prob")}
        for p in pregame
    ]

    # Save snapshot
    snap_path = os.path.join(snap_dir, f"snapshot_{ts}.json")
    with open(snap_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    logger.info(f"Saved: {snap_path} ({len(alerts)} alerts)")

    # Append alerts to running log
    if alerts:
        alerts_path = os.path.join(snap_dir, "alerts_log.json")
        existing = []
        if os.path.exists(alerts_path):
            try:
                with open(alerts_path) as f:
                    existing = json.load(f)
            except:
                existing = []
        existing.extend(alerts)
        with open(alerts_path, "w") as f:
            json.dump(existing, f, indent=2, default=str)
        logger.info(f"Alerts log: {len(existing)} total alerts")

    # Print summary
    print(f"\n  [{now.strftime('%I:%M %p')}] Games: {len(scores)} | "
          f"Odds events: {len(live_odds)} | Alerts: {len(alerts)}")
    for a in alerts:
        emoji = "🚨" if "BET" in a["recommended_action"] else "👀"
        print(f"    {emoji} {a['alert_type']}: {a['game']} — "
              f"Pick {a['pre_game_pick']} edge {a['edge']:.1%} "
              f"(live ML {a['live_line']}, DK {a.get('dk_line', '?')})")

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Live Game Monitor")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--interval", type=int, default=600, help="Seconds between snapshots")
    parser.add_argument("--once", action="store_true", help="Single snapshot, no loop")
    parser.add_argument("--until-hour", type=int, default=1,
                        help="Stop after this hour (EST, next day). Default 1 AM")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  LIVE GAME MONITOR — {args.date}")
    print(f"  Interval: {args.interval}s | Once: {args.once}")
    print(f"{'='*60}")

    if args.once:
        take_snapshot(args.date, once=True)
        return

    # Loop until --until-hour
    while True:
        now = datetime.now(EST)
        # Stop if past until-hour on the next day (or same day if until > current)
        if now.hour >= args.until_hour and now.hour < 12:
            logger.info(f"Past {args.until_hour} AM EST, stopping.")
            break

        try:
            take_snapshot(args.date)
        except Exception as e:
            logger.error(f"Snapshot error: {e}")

        logger.info(f"Next snapshot in {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
