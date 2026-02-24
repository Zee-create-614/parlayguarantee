"""
Live Odds Monitor — Continuously scrapes all sources and detects line movements.
Runs on a loop, saves snapshots, tracks changes.

Usage:
  python live_odds_monitor.py                     # Both sports, 5 min interval
  python live_odds_monitor.py --sport nba         # NBA only
  python live_odds_monitor.py --interval 120      # Every 2 min
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import asyncio
import json
import logging
import time
import argparse
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, List, Optional

ENGINE_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(ENGINE_DIR / 'live_monitor.log', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("live_monitor")


def load_previous_snapshot(sport: str) -> Dict:
    """Load the most recent snapshot for comparison."""
    path = ENGINE_DIR / f"live_snapshot_{sport}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_snapshot(sport: str, games: List[Dict], sources: Dict[str, int]):
    """Save current snapshot."""
    path = ENGINE_DIR / f"live_snapshot_{sport}.json"
    snapshot = {
        "sport": sport,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "games": {
            f"{g['away_team']}@{g['home_team']}": {
                "home_team": g["home_team"],
                "away_team": g["away_team"],
                "spread": g.get("spread"),
                "total": g.get("total"),
                "home_odds": g.get("home_odds"),
                "away_odds": g.get("away_odds"),
                "books": g.get("available_books", []),
            }
            for g in games
        }
    }
    with open(path, 'w') as f:
        json.dump(snapshot, f, indent=2)
    return snapshot


def detect_movements(prev: Dict, curr: Dict, sport: str) -> List[Dict]:
    """Compare two snapshots and find significant line movements."""
    movements = []
    prev_games = prev.get("games", {})
    curr_games = curr.get("games", {})

    for key, cg in curr_games.items():
        pg = prev_games.get(key)
        if not pg:
            continue  # New game, no movement

        # Spread movement
        if pg.get("spread") is not None and cg.get("spread") is not None:
            diff = abs(cg["spread"] - pg["spread"])
            if diff >= 0.5:
                movements.append({
                    "type": "spread",
                    "game": key,
                    "home": cg["home_team"],
                    "away": cg["away_team"],
                    "old": pg["spread"],
                    "new": cg["spread"],
                    "diff": round(cg["spread"] - pg["spread"], 1),
                    "sport": sport,
                })

        # Total movement
        if pg.get("total") is not None and cg.get("total") is not None:
            diff = abs(cg["total"] - pg["total"])
            if diff >= 1.0:
                movements.append({
                    "type": "total",
                    "game": key,
                    "home": cg["home_team"],
                    "away": cg["away_team"],
                    "old": pg["total"],
                    "new": cg["total"],
                    "diff": round(cg["total"] - pg["total"], 1),
                    "sport": sport,
                })

        # ML movement
        if pg.get("home_odds") is not None and cg.get("home_odds") is not None:
            diff = abs(cg["home_odds"] - pg["home_odds"])
            if diff >= 10:
                movements.append({
                    "type": "moneyline",
                    "game": key,
                    "home": cg["home_team"],
                    "away": cg["away_team"],
                    "old": pg["home_odds"],
                    "new": cg["home_odds"],
                    "diff": cg["home_odds"] - pg["home_odds"],
                    "sport": sport,
                })

    return movements


def save_movements(movements: List[Dict]):
    """Append movements to daily log."""
    if not movements:
        return
    today = date.today().isoformat()
    path = ENGINE_DIR / f"line_movements_{today}.json"
    existing = []
    if path.exists():
        try:
            with open(path) as f:
                existing = json.load(f)
        except Exception:
            pass

    ts = datetime.now(timezone.utc).isoformat()
    for m in movements:
        m["detected_at"] = ts
    existing.extend(movements)

    with open(path, 'w') as f:
        json.dump(existing, f, indent=2)

    logger.info(f"Logged {len(movements)} line movements to {path.name}")


async def run_cycle(sports: List[str], use_playwright: bool = False):
    """Run one scrape cycle for all sports."""
    from consensus_fetcher import fetch_consensus_games
    today = date.today()

    for sport in sports:
        try:
            logger.info(f"--- {sport.upper()} scrape ---")
            prev = load_previous_snapshot(sport)

            games = fetch_consensus_games(
                target_date=today,
                sport=sport,
                use_cache=False,
                use_playwright=use_playwright,
            )

            if not games:
                logger.warning(f"{sport}: 0 games returned")
                continue

            # Determine source counts
            from collections import Counter
            src_counts = Counter()
            for g in games:
                for b in g.get("available_books", []):
                    src_counts[b] += 1

            snapshot = save_snapshot(sport, games, dict(src_counts))

            # Detect movements
            if prev:
                movements = detect_movements(prev, snapshot, sport)
                if movements:
                    save_movements(movements)
                    for m in movements:
                        logger.info(
                            f"  LINE MOVE [{m['sport'].upper()}] {m['away']} @ {m['home']}: "
                            f"{m['type']} {m['old']} -> {m['new']} ({m['diff']:+})"
                        )
                else:
                    logger.info(f"  No significant movements")

            logger.info(f"  {sport.upper()}: {len(games)} games, sources: {dict(src_counts)}")

        except Exception as e:
            logger.error(f"{sport} cycle failed: {e}")


async def monitor_loop(sports: List[str], interval: int = 300, use_playwright: bool = False):
    """Main monitoring loop."""
    logger.info(f"Starting live odds monitor: sports={sports}, interval={interval}s, playwright={use_playwright}")

    while True:
        try:
            await run_cycle(sports, use_playwright)
        except Exception as e:
            logger.error(f"Cycle error: {e}")

        logger.info(f"Next scrape in {interval}s...")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", nargs="+", default=["ncaab", "nba"])
    parser.add_argument("--interval", type=int, default=300, help="Seconds between scrapes")
    parser.add_argument("--playwright", action="store_true", help="Use Playwright for DK/BetMGM")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_cycle(args.sport, args.playwright))
    else:
        asyncio.run(monitor_loop(args.sport, args.interval, args.playwright))
