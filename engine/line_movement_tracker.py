"""
Line Movement Tracker — Tracks spread & moneyline changes throughout the day.
Snapshots odds at multiple intervals, computes CLV (Closing Line Value),
and recommends optimal bet timing.

Usage:
  python line_movement_tracker.py snapshot        # Take a snapshot now
  python line_movement_tracker.py analyze         # Analyze today's movements
  python line_movement_tracker.py analyze 2026-02-20  # Analyze specific date
  python line_movement_tracker.py report          # Full CLV + timing report
  python line_movement_tracker.py history         # Show all historical CLV data
"""

import requests
import json
import sqlite3
import logging
import sys
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "line_movement.db"
API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE_URL = "https://api.the-odds-api.com/v4"

SPORT_KEYS = {
    "nba": "basketball_nba",
    "ncaab": "basketball_ncaab",
    "nhl": "icehockey_nhl",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "mma": "mma_mixed_martial_arts",
}


def init_db():
    """Create tables for spread/moneyline snapshots and CLV tracking."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS spread_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sport TEXT,
        game_id TEXT,
        game_date DATE,
        commence_time TEXT,
        home_team TEXT,
        away_team TEXT,
        bookmaker TEXT,
        home_spread REAL,
        away_spread REAL,
        home_spread_odds REAL,
        away_spread_odds REAL,
        home_ml REAL,
        away_ml REAL,
        over_under REAL,
        snapshot_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS line_movement_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sport TEXT,
        game_id TEXT,
        game_date DATE,
        home_team TEXT,
        away_team TEXT,
        opening_spread REAL,
        closing_spread REAL,
        spread_movement REAL,
        opening_ml_home REAL,
        opening_ml_away REAL,
        closing_ml_home REAL,
        closing_ml_away REAL,
        opening_total REAL,
        closing_total REAL,
        num_snapshots INTEGER,
        first_snapshot DATETIME,
        last_snapshot DATETIME,
        UNIQUE(game_id, game_date)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bet_timing_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date DATE,
        sport TEXT,
        game_id TEXT,
        home_team TEXT,
        away_team TEXT,
        our_pick TEXT,
        our_spread REAL,
        opening_spread REAL,
        closing_spread REAL,
        spread_at_bet_time REAL,
        bet_time TEXT,
        clv_vs_close REAL,
        clv_vs_open REAL,
        result TEXT,
        covered INTEGER,
        notes TEXT,
        UNIQUE(game_id, game_date, our_pick)
    )''')

    conn.commit()
    conn.close()


def fetch_odds_snapshot(sport: str = "nba") -> List[Dict]:
    """Fetch current spreads + moneylines + totals from Odds API."""
    sport_key = SPORT_KEYS.get(sport, sport)

    params = {
        "apiKey": API_KEY,
        "regions": "us",
        "markets": "spreads,h2h,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }

    url = f"{BASE_URL}/sports/{sport_key}/odds"
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.error(f"Odds API {resp.status_code}: {resp.text[:200]}")
            return []
        remaining = resp.headers.get("x-requests-remaining", "?")
        logger.info(f"Odds API requests remaining: {remaining}")
        return resp.json()
    except Exception as e:
        logger.error(f"Odds fetch error: {e}")
        return []


def store_snapshot(games: List[Dict], sport: str = "nba"):
    """Parse and store a snapshot of all games' spreads/ML/totals."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    now = datetime.now().isoformat()
    count = 0

    for game in games:
        game_id = game.get("id", "")
        home = game["home_team"]
        away = game["away_team"]
        commence = game.get("commence_time", "")
        game_date = commence[:10] if commence else date.today().isoformat()

        for bookie in game.get("bookmakers", []):
            bookie_name = bookie["title"]
            spreads = {}
            mls = {}
            total = None

            for market in bookie.get("markets", []):
                if market["key"] == "spreads":
                    for o in market["outcomes"]:
                        spreads[o["name"]] = (o.get("point", 0), o.get("price", 0))
                elif market["key"] == "h2h":
                    for o in market["outcomes"]:
                        mls[o["name"]] = o.get("price", 0)
                elif market["key"] == "totals":
                    for o in market["outcomes"]:
                        if o["name"] == "Over":
                            total = o.get("point")

            home_spread, home_spread_odds = spreads.get(home, (None, None))
            away_spread, away_spread_odds = spreads.get(away, (None, None))
            home_ml = mls.get(home)
            away_ml = mls.get(away)

            c.execute('''INSERT INTO spread_snapshots
                (sport, game_id, game_date, commence_time, home_team, away_team,
                 bookmaker, home_spread, away_spread, home_spread_odds, away_spread_odds,
                 home_ml, away_ml, over_under, snapshot_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (sport, game_id, game_date, commence, home, away,
                 bookie_name, home_spread, away_spread, home_spread_odds, away_spread_odds,
                 home_ml, away_ml, total, now))
            count += 1

    conn.commit()
    conn.close()
    return count


def take_snapshot(sport: str = "nba"):
    """Take a snapshot right now."""
    init_db()
    print(f"Fetching {sport.upper()} odds...")
    games = fetch_odds_snapshot(sport)
    if not games:
        print("No games returned.")
        return

    count = store_snapshot(games, sport)
    print(f"Stored {count} bookmaker entries across {len(games)} games.")

    # Show current spreads (consensus)
    print(f"\n{'='*70}")
    print(f"  {sport.upper()} SPREAD SNAPSHOT — {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    print(f"{'='*70}")

    for game in games:
        home = game["home_team"]
        away = game["away_team"]
        spreads_home = []
        spreads_away = []
        mls_home = []
        mls_away = []

        for bookie in game.get("bookmakers", []):
            for market in bookie.get("markets", []):
                if market["key"] == "spreads":
                    for o in market["outcomes"]:
                        if o["name"] == home:
                            spreads_home.append(o.get("point", 0))
                        elif o["name"] == away:
                            spreads_away.append(o.get("point", 0))
                elif market["key"] == "h2h":
                    for o in market["outcomes"]:
                        if o["name"] == home:
                            mls_home.append(o.get("price", 0))
                        elif o["name"] == away:
                            mls_away.append(o.get("price", 0))

        avg_home_spread = sum(spreads_home) / len(spreads_home) if spreads_home else 0
        avg_away_spread = sum(spreads_away) / len(spreads_away) if spreads_away else 0
        avg_home_ml = sum(mls_home) / len(mls_home) if mls_home else 0
        avg_away_ml = sum(mls_away) / len(mls_away) if mls_away else 0

        fav = home if avg_home_spread < 0 else away
        spread_val = avg_home_spread if avg_home_spread < 0 else avg_away_spread

        print(f"\n  {away} @ {home}")
        print(f"    Spread: {fav} {spread_val:+.1f}")
        print(f"    ML: {home} {avg_home_ml:+.0f} / {away} {avg_away_ml:+.0f}")


def analyze_movements(target_date: str = None, sport: str = "nba"):
    """Analyze spread movement for a given date."""
    init_db()
    if target_date is None:
        target_date = date.today().isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Get distinct games for this date
    c.execute('''SELECT DISTINCT game_id, home_team, away_team
                 FROM spread_snapshots
                 WHERE game_date = ? AND sport = ?''', (target_date, sport))
    games = c.fetchall()

    if not games:
        print(f"No snapshot data for {target_date}. Take snapshots first!")
        conn.close()
        return

    print(f"\n{'='*70}")
    print(f"  LINE MOVEMENT REPORT — {target_date}")
    print(f"{'='*70}")

    for game_id, home, away in games:
        # Get earliest and latest consensus spread
        c.execute('''SELECT home_spread, away_spread, home_ml, away_ml, over_under, snapshot_time
                     FROM spread_snapshots
                     WHERE game_id = ? AND game_date = ? AND bookmaker = 'FanDuel'
                     ORDER BY snapshot_time ASC''', (game_id, target_date))
        rows = c.fetchall()

        if not rows:
            # Fall back to any bookmaker
            c.execute('''SELECT AVG(home_spread), AVG(away_spread), AVG(home_ml), AVG(away_ml),
                                AVG(over_under), snapshot_time
                         FROM spread_snapshots
                         WHERE game_id = ? AND game_date = ?
                         GROUP BY snapshot_time
                         ORDER BY snapshot_time ASC''', (game_id, target_date))
            rows = c.fetchall()

        if len(rows) < 1:
            continue

        opening = rows[0]
        closing = rows[-1]

        open_spread = opening[0] if opening[0] is not None else 0
        close_spread = closing[0] if closing[0] is not None else 0
        spread_move = close_spread - open_spread

        open_ml_h = opening[2] if opening[2] else 0
        open_ml_a = opening[3] if opening[3] else 0
        close_ml_h = closing[2] if closing[2] else 0
        close_ml_a = closing[3] if closing[3] else 0

        open_total = opening[4]
        close_total = closing[4]

        num_snaps = len(rows)
        first_time = rows[0][5][:16] if rows[0][5] else "?"
        last_time = rows[-1][5][:16] if rows[-1][5] else "?"

        # Store summary
        c.execute('''INSERT OR REPLACE INTO line_movement_summary
            (sport, game_id, game_date, home_team, away_team,
             opening_spread, closing_spread, spread_movement,
             opening_ml_home, opening_ml_away, closing_ml_home, closing_ml_away,
             opening_total, closing_total, num_snapshots, first_snapshot, last_snapshot)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (sport, game_id, target_date, home, away,
             open_spread, close_spread, spread_move,
             open_ml_h, open_ml_a, close_ml_h, close_ml_a,
             open_total, close_total, num_snaps, first_time, last_time))

        # Display
        direction = "→" if spread_move == 0 else ("↑" if spread_move > 0 else "↓")
        moved = abs(spread_move)

        print(f"\n  {away} @ {home}")
        print(f"    Spread: {open_spread:+.1f} {direction} {close_spread:+.1f}  (moved {moved:.1f} pts)")
        if open_total and close_total:
            total_move = close_total - open_total
            print(f"    Total:  {open_total:.1f} → {close_total:.1f}  ({total_move:+.1f})")
        print(f"    ML: {home} {open_ml_h:+.0f}→{close_ml_h:+.0f} / {away} {open_ml_a:+.0f}→{close_ml_a:+.0f}")
        print(f"    Snapshots: {num_snaps} ({first_time} to {last_time})")

        if moved >= 1.0:
            print(f"    ⚠️  SIGNIFICANT MOVEMENT ({moved:.1f} pts)")
        if moved >= 0.5 and spread_move != 0:
            # Determine who benefited
            if spread_move > 0:
                print(f"    💡 Home spread got worse (moved toward away) — bet EARLY if picking home")
            else:
                print(f"    💡 Home spread improved — bet LATE if picking home")

    conn.commit()
    conn.close()


def get_line_movement_score(home_team: str, away_team: str, current_spread: float,
                            target_date: str = None, sport: str = "nba") -> Dict:
    """
    Calculate line movement score for a game.
    Returns dict with:
      - opening_spread: first recorded spread (home perspective)
      - current_spread: current spread passed in
      - movement: how much the line moved (positive = moved toward home dog / away fav got bigger)
      - movement_toward_dog: True if line moved toward the underdog
      - score: float, positive means sharp action on underdog
    """
    init_db()
    if target_date is None:
        target_date = date.today().isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Find the opening spread for this game
    c.execute('''SELECT home_spread, snapshot_time
                 FROM spread_snapshots
                 WHERE home_team = ? AND away_team = ? AND game_date = ? AND sport = ?
                 AND home_spread IS NOT NULL
                 ORDER BY snapshot_time ASC LIMIT 1''',
              (home_team, away_team, target_date, sport))
    row = c.fetchone()

    if not row:
        # Try with swapped names or partial match
        c.execute('''SELECT home_spread, snapshot_time
                     FROM spread_snapshots
                     WHERE game_date = ? AND sport = ?
                     AND home_spread IS NOT NULL
                     AND (home_team LIKE ? OR away_team LIKE ?)
                     ORDER BY snapshot_time ASC LIMIT 1''',
                  (target_date, sport, f'%{home_team.split()[-1]}%', f'%{away_team.split()[-1]}%'))
        row = c.fetchone()

    conn.close()

    if not row:
        # No prior snapshot — take one now and return neutral
        return {
            'opening_spread': current_spread,
            'current_spread': current_spread,
            'movement': 0.0,
            'movement_toward_dog': False,
            'score': 0.0,
        }

    opening_spread = row[0]
    movement = current_spread - opening_spread  # positive = home spread got bigger (worse for home)

    # Determine if movement is toward the dog
    # If home is underdog (spread > 0) and spread decreased, line moved toward dog (good for dog)
    # If home is favorite (spread < 0) and spread increased (less negative), line moved toward away dog
    if opening_spread > 0:
        # Home is dog. Movement toward dog = spread decreased (line tightened)
        movement_toward_dog = movement < 0
        dog_movement = -movement  # positive = good for dog
    elif opening_spread < 0:
        # Away is dog. Movement toward dog = spread increased (home fav lost points)
        movement_toward_dog = movement > 0
        dog_movement = movement
    else:
        movement_toward_dog = False
        dog_movement = 0.0

    # Score: how much the line moved toward the dog
    score = 0.0
    abs_move = abs(dog_movement)
    if movement_toward_dog:
        if abs_move >= 3.0:
            score = 0.5   # MAJOR sharp action
        elif abs_move >= 1.5:
            score = 0.3   # Significant movement
        elif abs_move >= 0.5:
            score = 0.15  # Moderate
    else:
        # Moved toward favorite — slight negative
        if abs_move >= 1.5:
            score = -0.15
        elif abs_move >= 0.5:
            score = -0.05

    return {
        'opening_spread': opening_spread,
        'current_spread': current_spread,
        'movement': round(movement, 1),
        'movement_toward_dog': movement_toward_dog,
        'dog_movement_pts': round(dog_movement, 1),
        'score': round(score, 3),
    }


def record_bet(game_id: str, game_date: str, our_pick: str, our_spread: float,
               sport: str = "nba", bet_time: str = None):
    """Record what spread we actually got when we placed the bet."""
    init_db()
    if bet_time is None:
        bet_time = datetime.now().isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Get opening/closing from summary
    c.execute('''SELECT opening_spread, closing_spread, home_team, away_team
                 FROM line_movement_summary
                 WHERE game_id = ? AND game_date = ?''', (game_id, game_date))
    row = c.fetchone()

    opening = row[0] if row else our_spread
    closing = row[1] if row else our_spread
    home = row[2] if row else ""
    away = row[3] if row else ""

    # CLV: positive = we got a better number than close
    # For spread bets: if we picked the home team and got -3.5 but it closed at -4.5, CLV = +1.0
    clv_vs_close = our_spread - closing if our_pick == home else -(our_spread - closing)
    clv_vs_open = our_spread - opening if our_pick == home else -(our_spread - opening)

    c.execute('''INSERT OR REPLACE INTO bet_timing_analysis
        (game_date, sport, game_id, home_team, away_team, our_pick,
         our_spread, opening_spread, closing_spread, spread_at_bet_time,
         bet_time, clv_vs_close, clv_vs_open)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (game_date, sport, game_id, home, away, our_pick,
         our_spread, opening, closing, our_spread, bet_time,
         clv_vs_close, clv_vs_open))

    conn.commit()
    conn.close()
    print(f"Recorded bet: {our_pick} {our_spread:+.1f} (CLV vs close: {clv_vs_close:+.1f})")


def timing_report():
    """Generate a report on whether early or late betting is better."""
    init_db()
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute('''SELECT COUNT(*), 
                        AVG(clv_vs_close),
                        AVG(clv_vs_open),
                        SUM(CASE WHEN covered = 1 THEN 1 ELSE 0 END),
                        SUM(CASE WHEN covered = 0 THEN 1 ELSE 0 END)
                 FROM bet_timing_analysis
                 WHERE clv_vs_close IS NOT NULL''')
    row = c.fetchone()
    conn.close()

    if not row or row[0] == 0:
        print("No bet timing data yet. Record bets and results to build this report.")
        print("As data accumulates, we'll see whether early or late betting gives better CLV.")
        return

    total, avg_clv_close, avg_clv_open, wins, losses = row
    print(f"\n{'='*70}")
    print(f"  BET TIMING ANALYSIS — {total} bets tracked")
    print(f"{'='*70}")
    print(f"  Avg CLV vs Closing Line: {avg_clv_close:+.2f} pts")
    print(f"  Avg CLV vs Opening Line: {avg_clv_open:+.2f} pts")
    if wins is not None and losses is not None:
        total_decided = (wins or 0) + (losses or 0)
        if total_decided > 0:
            print(f"  Cover Rate: {wins}/{total_decided} ({100*wins/total_decided:.1f}%)")

    if avg_clv_close and avg_clv_close > 0.3:
        print(f"\n  ✅ You're beating the closing line — your timing is GOOD")
    elif avg_clv_close and avg_clv_close < -0.3:
        print(f"\n  ⚠️  You're getting worse numbers than close — consider adjusting timing")
    else:
        print(f"\n  📊 Neutral CLV — need more data to determine optimal timing")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    sport = "nba"

    # Check for sport flag
    for arg in sys.argv[1:]:
        if arg in SPORT_KEYS:
            sport = arg

    if cmd == "snapshot":
        take_snapshot(sport)
    elif cmd == "analyze":
        target = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2] in SPORT_KEYS else None
        analyze_movements(target, sport)
    elif cmd == "report":
        timing_report()
    elif cmd == "history":
        init_db()
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT game_date, home_team, away_team, opening_spread, closing_spread,
                            spread_movement, num_snapshots
                     FROM line_movement_summary ORDER BY game_date DESC LIMIT 50''')
        rows = c.fetchall()
        conn.close()
        if not rows:
            print("No movement history yet.")
        else:
            print(f"\n{'Date':<12} {'Matchup':<40} {'Open':>6} {'Close':>6} {'Move':>6} {'Snaps':>5}")
            print("-" * 75)
            for r in rows:
                matchup = f"{r[2]} @ {r[1]}"[:38]
                print(f"{r[0]:<12} {matchup:<40} {r[3]:>+6.1f} {r[4]:>+6.1f} {r[5]:>+6.1f} {r[6]:>5}")
    else:
        print(__doc__)
