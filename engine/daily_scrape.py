"""
daily_scrape.py — Autonomous daily runner for ParlayGuarantee NCAAB scraper.
Run from cron or CLI. Logs to console + scrape.log.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

from book_scraper import scrape_all
from consensus import build_consensus
from line_tracker import init_db, store_scrape, store_consensus

# Logging setup
logger = logging.getLogger("daily_scrape")


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    fh = logging.FileHandler("scrape.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


async def run():
    setup_logging()
    logger.info("=== Daily scrape starting ===")

    try:
        init_db()

        # Scrape
        all_games = await scrape_all()
        fd_count = len(all_games.get("fanduel", []))
        espn_count = len(all_games.get("espn", []))
        logger.info(f"Scraped: FanDuel={fd_count}, ESPN={espn_count}")

        # Store raw scrapes
        for source, games in all_games.items():
            if games:
                store_scrape(source, games)

        # Consensus
        consensus = build_consensus(all_games)
        store_consensus(consensus)

        flagged = [g for g in consensus if g.flags]
        high = sum(1 for g in consensus if g.confidence == "HIGH")
        med = sum(1 for g in consensus if g.confidence == "MEDIUM")
        espn_only = sum(1 for g in consensus if g.confidence == "ESPN_ONLY")

        summary = (
            f"SUMMARY: {fd_count} FanDuel, {espn_count} ESPN, "
            f"{len(consensus)} consensus ({high} HIGH, {med} MEDIUM, {espn_only} ESPN_ONLY), "
            f"{len(flagged)} flagged"
        )
        logger.info(summary)
        print(f"\n{'='*60}")
        print(summary)
        print(f"{'='*60}")

        if flagged:
            print(f"\nFLAGGED GAMES:")
            for g in flagged:
                print(f"  {g.away_team} @ {g.home_team}: {', '.join(g.flags)}")

        return 0

    except Exception as e:
        logger.exception(f"Daily scrape FAILED: {e}")
        return 1


def main():
    code = asyncio.run(run())
    sys.exit(code)


if __name__ == "__main__":
    main()
