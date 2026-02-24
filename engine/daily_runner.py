"""
Autonomous Daily Runner — Scrapes all sources, builds consensus, saves to SQLite.
Can be called from cron/scheduler.
"""

import asyncio
import json
import logging
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add engine dir to path
sys.path.insert(0, str(Path(__file__).parent))

from sportsbook_scraper import scrape_all, FanDuelScraper, OddsAPIScraper, GameLine
from consensus_engine import build_consensus, ConsensusGame
from playwright_scrapers import scrape_draftkings, scrape_betmgm
from consensus_fetcher import fetch_consensus_games

DB_PATH = Path(__file__).parent / "ncaab_consensus.db"
LOG_PATH = Path(__file__).parent / "scraper.log"
MAX_RETRIES = 3
BACKOFF_BASE = 5  # seconds

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("daily_runner")


def init_db(db_path: Path = DB_PATH):
    """Create tables if they don't exist."""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS consensus_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            start_time TEXT,
            spread_home REAL,
            spread_away REAL,
            total REAL,
            moneyline_home INTEGER,
            moneyline_away INTEGER,
            confidence REAL,
            sources TEXT,
            flags TEXT,
            source_lines TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            dk_count INTEGER DEFAULT 0,
            fd_count INTEGER DEFAULT 0,
            oa_count INTEGER DEFAULT 0,
            consensus_count INTEGER DEFAULT 0,
            flagged_count INTEGER DEFAULT 0,
            errors TEXT,
            duration_sec REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS raw_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            home_team TEXT,
            away_team TEXT,
            start_time TEXT,
            spread_home REAL,
            spread_away REAL,
            total REAL,
            moneyline_home INTEGER,
            moneyline_away INTEGER,
            raw_json TEXT
        )
    """)

    conn.commit()
    conn.close()


async def scrape_with_retry(scraper, name: str) -> list[GameLine]:
    """Scrape a single source with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"[{name}] Attempt {attempt}/{MAX_RETRIES}")
            result = await scraper.scrape()
            if result:
                logger.info(f"[{name}] Success: {len(result)} games")
                return result
            else:
                logger.warning(f"[{name}] Returned 0 games on attempt {attempt}")
        except Exception as e:
            logger.error(f"[{name}] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE * (2 ** (attempt - 1))
                logger.info(f"[{name}] Retrying in {wait}s...")
                await asyncio.sleep(wait)

    logger.error(f"[{name}] ALL {MAX_RETRIES} attempts failed")
    return []


async def run():
    """Main daily run."""
    start_time = time.time()
    run_ts = datetime.now(timezone.utc).isoformat()
    errors = []

    logger.info("=" * 60)
    logger.info(f"Starting scrape run at {run_ts}")

    init_db()

    # Scrape all sources with retry
    # DraftKings: use Playwright (their API is geo-blocked)
    logger.info("[DraftKings] Using Playwright scraper...")
    dk_games = []
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            dk_games = await scrape_draftkings(sport="ncaab")
            if dk_games:
                logger.info(f"[DraftKings] Success: {len(dk_games)} games")
                break
            logger.warning(f"[DraftKings] 0 games on attempt {attempt}")
        except Exception as e:
            logger.error(f"[DraftKings] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

    # BetMGM: Playwright (headless=False, needs display)
    logger.info("[BetMGM] Using Playwright scraper...")
    mgm_games = []
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            mgm_games = await scrape_betmgm(sport="ncaab")
            if mgm_games:
                logger.info(f"[BetMGM] Success: {len(mgm_games)} games")
                break
            logger.warning(f"[BetMGM] 0 games on attempt {attempt}")
        except Exception as e:
            logger.error(f"[BetMGM] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

    # FanDuel & OddsAPI: use HTTP API scrapers
    fd_games = await scrape_with_retry(FanDuelScraper(), "FanDuel")
    oa_games = await scrape_with_retry(OddsAPIScraper(), "OddsAPI")

    active_sources = 0
    all_games = {}
    if dk_games:
        all_games["draftkings"] = dk_games
        active_sources += 1
    else:
        errors.append("DraftKings returned 0 games")
        logger.warning("DraftKings returned no data")

    if mgm_games:
        all_games["betmgm"] = mgm_games
        active_sources += 1
    else:
        errors.append("BetMGM returned 0 games")
        logger.warning("BetMGM returned no data")

    if fd_games:
        all_games["fanduel"] = fd_games
        active_sources += 1
    else:
        errors.append("FanDuel returned 0 games")
        logger.warning("FanDuel returned no data")

    if oa_games:
        all_games["odds_api"] = oa_games
        active_sources += 1
    else:
        errors.append("OddsAPI returned 0 games")
        logger.warning("OddsAPI returned no data")

    if active_sources == 0:
        logger.critical("ALL sources failed! No data to process.")
        errors.append("ALL SOURCES FAILED")
        _save_run(run_ts, 0, 0, 0, 0, 0, errors, time.time() - start_time)
        return []

    if active_sources < 2:
        logger.warning(f"Only {active_sources} source(s) available — consensus will be low confidence")

    # Build consensus
    consensus = build_consensus(all_games)
    flagged = [g for g in consensus if g.flags]

    logger.info(f"Consensus: {len(consensus)} games, {len(flagged)} flagged")

    # Save to DB
    _save_to_db(run_ts, consensus, all_games)
    _save_run(run_ts, len(dk_games), len(fd_games), len(oa_games),
              len(consensus), len(flagged), errors, time.time() - start_time)

    # Summary
    duration = time.time() - start_time
    logger.info(f"Run complete in {duration:.1f}s")
    logger.info(f"  DK: {len(dk_games)} | FD: {len(fd_games)} | OA: {len(oa_games)}")
    logger.info(f"  Consensus: {len(consensus)} | Flagged: {len(flagged)}")

    if flagged:
        logger.warning("Flagged games:")
        for g in flagged:
            logger.warning(f"  {g.away_team} @ {g.home_team}: {g.flags}")

    return consensus


def _save_to_db(run_ts: str, consensus: list[ConsensusGame], all_games: dict):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # Save consensus
    for g in consensus:
        c.execute("""
            INSERT INTO consensus_games
            (run_timestamp, home_team, away_team, start_time, spread_home, spread_away,
             total, moneyline_home, moneyline_away, confidence, sources, flags, source_lines)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_ts, g.home_team, g.away_team, g.start_time,
            g.spread_home, g.spread_away, g.total,
            g.moneyline_home, g.moneyline_away, g.confidence,
            json.dumps(g.sources), json.dumps(g.flags), json.dumps(g.source_lines),
        ))

    # Save raw lines
    for source, games in all_games.items():
        for g in games:
            c.execute("""
                INSERT INTO raw_lines
                (run_timestamp, source, home_team, away_team, start_time,
                 spread_home, spread_away, total, moneyline_home, moneyline_away, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_ts, source, g.home_team, g.away_team, g.start_time,
                g.spread_home, g.spread_away, g.total,
                g.moneyline_home, g.moneyline_away, json.dumps(g.to_dict()),
            ))

    conn.commit()
    conn.close()


def _save_run(run_ts, dk, fd, oa, consensus, flagged, errors, duration):
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        INSERT INTO scrape_runs
        (timestamp, dk_count, fd_count, oa_count, consensus_count, flagged_count, errors, duration_sec)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_ts, dk, fd, oa, consensus, flagged, json.dumps(errors), duration))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    consensus = asyncio.run(run())
    print(f"\n{'='*60}")
    print(f"Total consensus games: {len(consensus)}")
    for g in consensus[:10]:
        flag_str = " ⚠️" if g.flags else " ✅"
        print(f"  {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} | "
              f"conf={g.confidence} sources={g.sources}{flag_str}")
