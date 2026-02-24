"""
Closing Line Value (CLV) Tracker for ParlayGuarantee
Stores opening odds when picks are generated, captures closing odds before tip,
calculates CLV — the #1 indicator of long-term profitability.
"""

import sys
import json
import logging
import argparse
import sqlite3
import os
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from moneyline_parlay import american_to_decimal, implied_probability, ODDS_API_KEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://api.the-odds-api.com/v4"
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "clv.db")


def get_db() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS picks_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_date DATE NOT NULL,
            game_key TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            predicted_winner TEXT NOT NULL,
            model_prob REAL,
            opening_odds_american INTEGER,
            opening_odds_decimal REAL,
            opening_implied_prob REAL,
            closing_odds_american INTEGER,
            closing_odds_decimal REAL,
            closing_implied_prob REAL,
            clv_cents REAL,
            clv_implied REAL,
            beat_closing_line INTEGER,
            commence_time TEXT,
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closing_recorded_at DATETIME,
            UNIQUE(pick_date, game_key, predicted_winner)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clv_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_date DATE NOT NULL UNIQUE,
            total_picks INTEGER,
            picks_beat_cl INTEGER,
            beat_cl_pct REAL,
            avg_clv_cents REAL,
            avg_clv_implied REAL,
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def store_opening_odds(picks: List[Dict], pick_date: str = None) -> int:
    """
    Store opening odds when picks are generated (typically 3 PM daily).
    picks: list of dicts with predicted_winner, home_team, away_team, 
           model_prob, opening_odds (american), commence_time
    """
    if not pick_date:
        pick_date = date.today().isoformat()
    
    conn = get_db()
    stored = 0
    
    for pick in picks:
        home = pick.get("home_team", "")
        away = pick.get("away_team", "")
        winner = pick.get("predicted_winner", "")
        game_key = f"{away} @ {home}"
        
        opening_american = pick.get("opening_odds", pick.get("american_odds"))
        if opening_american is None:
            continue
        
        opening_decimal = american_to_decimal(opening_american)
        opening_implied = implied_probability(opening_american)
        model_prob = pick.get("model_prob", pick.get("win_prob", pick.get("confidence", 50) / 100))
        if model_prob > 1:
            model_prob /= 100

        try:
            conn.execute("""
                INSERT OR REPLACE INTO picks_odds 
                (pick_date, game_key, home_team, away_team, predicted_winner,
                 model_prob, opening_odds_american, opening_odds_decimal, 
                 opening_implied_prob, commence_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pick_date, game_key, home, away, winner,
                  model_prob, opening_american, opening_decimal,
                  opening_implied, pick.get("commence_time", "")))
            stored += 1
        except Exception as e:
            logger.error(f"Error storing pick: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Stored opening odds for {stored} picks")
    return stored


def capture_closing_odds(sport: str = "basketball_nba", pick_date: str = None) -> int:
    """
    Capture closing odds just before game time.
    Should be run close to tip-off for most accurate CLV.
    """
    if not pick_date:
        pick_date = date.today().isoformat()
    
    # Fetch current odds
    url = f"{BASE_URL}/sports/{sport}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h",
        "oddsFormat": "american",
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch closing odds: {e}")
        return 0
    
    # Build lookup
    odds_lookup = {}
    for event in events:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        
        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] != "h2h":
                    continue
                for outcome in mkt.get("outcomes", []):
                    team = outcome["name"]
                    price = outcome["price"]
                    key = (f"{away} @ {home}", team)
                    # Use consensus/first available
                    if key not in odds_lookup:
                        odds_lookup[key] = price

    conn = get_db()
    updated = 0
    
    # Get picks that need closing odds
    rows = conn.execute("""
        SELECT id, game_key, predicted_winner, opening_odds_american
        FROM picks_odds
        WHERE pick_date = ? AND closing_odds_american IS NULL
    """, (pick_date,)).fetchall()
    
    for row in rows:
        key = (row["game_key"], row["predicted_winner"])
        closing_american = odds_lookup.get(key)
        if closing_american is None:
            continue
        
        closing_decimal = american_to_decimal(closing_american)
        closing_implied = implied_probability(closing_american)
        opening_implied = row["opening_odds_american"]
        opening_implied_prob = implied_probability(opening_implied)
        
        # CLV in cents: difference in implied probability
        clv_implied = opening_implied_prob - closing_implied  # negative = we got better odds
        # CLV in cents: we want to have gotten BETTER odds than closing
        # If we bet at -150 and it closed at -180, we got value
        clv_cents = closing_implied - implied_probability(row["opening_odds_american"])
        # Positive clv_cents = we beat the closing line
        beat_cl = 1 if clv_cents > 0 else 0

        conn.execute("""
            UPDATE picks_odds 
            SET closing_odds_american = ?, closing_odds_decimal = ?,
                closing_implied_prob = ?, clv_cents = ?, clv_implied = ?,
                beat_closing_line = ?, closing_recorded_at = ?
            WHERE id = ?
        """, (closing_american, closing_decimal, closing_implied,
              round(clv_cents, 4), round(clv_implied, 4), beat_cl,
              datetime.now().isoformat(), row["id"]))
        updated += 1

    conn.commit()
    conn.close()
    logger.info(f"Updated closing odds for {updated} picks")
    return updated


def calculate_clv_summary(pick_date: str = None, days_back: int = 30) -> Dict:
    """
    Calculate CLV summary statistics.
    """
    conn = get_db()
    
    if pick_date:
        where = "WHERE pick_date = ? AND closing_odds_american IS NOT NULL"
        params = (pick_date,)
    else:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        where = "WHERE pick_date >= ? AND closing_odds_american IS NOT NULL"
        params = (cutoff,)
    
    rows = conn.execute(f"""
        SELECT pick_date, game_key, predicted_winner, model_prob,
               opening_odds_american, closing_odds_american,
               opening_implied_prob, closing_implied_prob,
               clv_cents, clv_implied, beat_closing_line
        FROM picks_odds {where}
        ORDER BY pick_date DESC
    """, params).fetchall()
    
    if not rows:
        conn.close()
        return {
            "total_picks": 0,
            "message": "No CLV data available yet. Picks need opening AND closing odds recorded."
        }

    total = len(rows)
    beat_cl = sum(1 for r in rows if r["beat_closing_line"])
    clv_values = [r["clv_cents"] for r in rows if r["clv_cents"] is not None]
    implied_values = [r["clv_implied"] for r in rows if r["clv_implied"] is not None]

    avg_clv = sum(clv_values) / len(clv_values) if clv_values else 0
    avg_implied = sum(implied_values) / len(implied_values) if implied_values else 0
    beat_pct = beat_cl / total * 100 if total > 0 else 0

    # Per-day breakdown
    daily = {}
    for r in rows:
        d = r["pick_date"]
        if d not in daily:
            daily[d] = {"total": 0, "beat_cl": 0, "clv_sum": 0}
        daily[d]["total"] += 1
        if r["beat_closing_line"]:
            daily[d]["beat_cl"] += 1
        if r["clv_cents"] is not None:
            daily[d]["clv_sum"] += r["clv_cents"]

    daily_stats = []
    for d, s in sorted(daily.items(), reverse=True):
        daily_stats.append({
            "date": d,
            "picks": s["total"],
            "beat_cl": s["beat_cl"],
            "beat_cl_pct": round(s["beat_cl"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            "avg_clv": round(s["clv_sum"] / s["total"], 4) if s["total"] > 0 else 0,
        })

    # Store summary
    if pick_date:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO clv_summary 
                (summary_date, total_picks, picks_beat_cl, beat_cl_pct, avg_clv_cents, avg_clv_implied)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (pick_date, total, beat_cl, beat_pct, avg_clv, avg_implied))
            conn.commit()
        except:
            pass

    conn.close()

    picks_detail = [dict(r) for r in rows[:50]]  # Last 50

    return {
        "period": f"Last {len(set(r['pick_date'] for r in rows))} days",
        "total_picks": total,
        "picks_beat_closing_line": beat_cl,
        "beat_cl_pct": round(beat_pct, 1),
        "avg_clv_cents": round(avg_clv, 4),
        "avg_clv_implied": round(avg_implied, 4),
        "interpretation": (
            "PROFITABLE LONG-TERM" if avg_clv > 0.01 else
            "BREAK-EVEN" if avg_clv > -0.005 else
            "NEEDS IMPROVEMENT"
        ),
        "daily_breakdown": daily_stats,
        "recent_picks": picks_detail,
    }


def run(action: str = "summary", analyzed_games: List[Dict] = None,
        sport: str = "basketball_nba", days_back: int = 30) -> Dict:
    """
    Main entry point.
    action: 'store_opening', 'capture_closing', 'summary'
    """
    logger.info(f"CLV Tracker: action={action}")
    
    if action == "store_opening":
        if not analyzed_games:
            return {"error": "No games provided to store"}
        # Convert analyzed games to picks format
        from moneyline_parlay import MoneylineParlay
        ml = MoneylineParlay(analyzed_games)
        odds = ml.fetch_live_moneyline_odds(sport)
        
        picks_to_store = []
        for game in analyzed_games:
            home = game.get("home_team", game.get("home", ""))
            away = game.get("away_team", game.get("away", ""))
            predicted = game.get("predicted_winner", game.get("pick", ""))
            game_key = f"{away} @ {home}"
            
            game_odds = odds.get(game_key)
            if not game_odds:
                for k, v in odds.items():
                    if v["home_team"] == home and v["away_team"] == away:
                        game_odds = v
                        break
            
            if game_odds and predicted:
                side = "home" if predicted == home else "away"
                picks_to_store.append({
                    "home_team": home,
                    "away_team": away,
                    "predicted_winner": predicted,
                    "model_prob": game.get("win_prob", game.get("confidence", 50) / 100),
                    "opening_odds": game_odds[side]["american"],
                    "commence_time": game_odds.get("commence_time", ""),
                })
        
        stored = store_opening_odds(picks_to_store)
        return {"action": "store_opening", "stored": stored}
    
    elif action == "capture_closing":
        updated = capture_closing_odds(sport)
        return {"action": "capture_closing", "updated": updated}
    
    elif action == "summary":
        return calculate_clv_summary(days_back=days_back)
    
    else:
        return {"error": f"Unknown action: {action}"}


def main():
    parser = argparse.ArgumentParser(description="CLV Tracker")
    parser.add_argument("--action", default="summary",
                        choices=["store_opening", "capture_closing", "summary"])
    parser.add_argument("--sport", default="basketball_nba")
    parser.add_argument("--games-file", default="analyzed_games.json")
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    analyzed_games = None
    if args.action == "store_opening":
        try:
            with open(args.games_file, 'r') as f:
                analyzed_games = json.load(f)
            if not isinstance(analyzed_games, list):
                analyzed_games = [analyzed_games]
        except FileNotFoundError:
            logger.error(f"No games file at {args.games_file}")
            analyzed_games = []

    result = run(args.action, analyzed_games, args.sport, args.days_back)
    output = json.dumps(result, indent=2, default=str)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        logger.info(f"Output written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
