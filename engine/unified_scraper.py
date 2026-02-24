"""
Unified Scraper — Combines API scrapers (FanDuel, Odds API) with 
Playwright scrapers (DraftKings, Caesars, BetMGM) and builds consensus.

Usage:
    python unified_scraper.py [sport] [--save] [--no-playwright]
    
    sport: ncaab (default), nba, nhl
    --save: save results to JSON
    --no-playwright: skip Playwright scrapers (API only)
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from sportsbook_scraper import FanDuelScraper, OddsAPIScraper, GameLine
from playwright_scrapers import scrape_draftkings, scrape_caesars, scrape_betmgm
from consensus_engine import build_consensus
from team_name_mapper import normalize_team

logger = logging.getLogger("unified_scraper")


async def scrape_all_sources(sport: str = "ncaab", use_playwright: bool = True) -> dict[str, list[GameLine]]:
    """
    Scrape all available sources. API scrapers run concurrently,
    Playwright scrapers run sequentially (browser resource limits).
    """
    results = {}

    # Phase 1: API scrapers (fast, concurrent)
    logger.info("Phase 1: API scrapers...")
    api_tasks = []

    # FanDuel (sport-aware)
    fd = FanDuelScraper(sport=sport)
    api_tasks.append(("fanduel", fd.scrape()))

    # Odds API (sport-aware)
    oa = OddsAPIScraper(sport=sport)
    api_tasks.append(("odds_api", oa.scrape()))

    if api_tasks:
        api_results = await asyncio.gather(*[t[1] for t in api_tasks], return_exceptions=True)
        for (name, _), result in zip(api_tasks, api_results):
            if isinstance(result, Exception):
                logger.error(f"{name} failed: {result}")
                results[name] = []
            else:
                results[name] = result
                logger.info(f"{name}: {len(result)} games")

    # Phase 2: Playwright scrapers (sequential)
    if use_playwright:
        logger.info("Phase 2: Playwright scrapers...")

        # DraftKings
        try:
            dk_games = await scrape_draftkings(sport=sport)
            results["draftkings"] = dk_games
            logger.info(f"draftkings: {len(dk_games)} games")
        except Exception as e:
            logger.error(f"draftkings failed: {e}")
            results["draftkings"] = []

        # Caesars (may not work yet due to WAF)
        try:
            czr_games = await scrape_caesars(sport=sport)
            results["caesars"] = czr_games
            if czr_games:
                logger.info(f"caesars: {len(czr_games)} games")
            else:
                logger.warning("caesars: 0 games (WAF blocked)")
        except Exception as e:
            logger.error(f"caesars failed: {e}")
            results["caesars"] = []

        # BetMGM (may not work yet due to redirect loop)
        try:
            mgm_games = await scrape_betmgm(sport=sport)
            results["betmgm"] = mgm_games
            if mgm_games:
                logger.info(f"betmgm: {len(mgm_games)} games")
            else:
                logger.warning("betmgm: 0 games (redirect blocked)")
        except Exception as e:
            logger.error(f"betmgm failed: {e}")
            results["betmgm"] = []

    return results


async def run_consensus(sport: str = "ncaab", use_playwright: bool = True, save: bool = False):
    """Full pipeline: scrape → consensus → output."""
    
    # Scrape all sources
    all_games = await scrape_all_sources(sport=sport, use_playwright=use_playwright)

    # Filter out empty sources
    active_sources = {k: v for k, v in all_games.items() if v}
    
    if not active_sources:
        logger.error("No sources returned data!")
        return []

    # Build consensus
    logger.info(f"Building consensus from {len(active_sources)} sources: {list(active_sources.keys())}")
    consensus = build_consensus(active_sources, sport=sport)

    # Summary
    total_games = len(consensus)
    with_spread = sum(1 for g in consensus if g.spread_home is not None)
    with_total = sum(1 for g in consensus if g.total is not None)
    with_ml = sum(1 for g in consensus if g.moneyline_home is not None)
    multi_source = sum(1 for g in consensus if len(g.sources) >= 2)
    triple_source = sum(1 for g in consensus if len(g.sources) >= 3)
    flagged = sum(1 for g in consensus if g.flags)

    print(f"\n{'='*70}")
    print(f"CONSENSUS REPORT — {sport.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    print(f"Sources: {', '.join(active_sources.keys())}")
    for src, games in active_sources.items():
        print(f"  {src}: {len(games)} games")
    print(f"\nTotal games: {total_games}")
    print(f"  With spread: {with_spread}")
    print(f"  With total: {with_total}")
    print(f"  With ML: {with_ml}")
    print(f"  Multi-source (2+): {multi_source}")
    print(f"  Triple-source (3+): {triple_source}")
    print(f"  Flagged discrepancies: {flagged}")

    # Show top games by confidence
    print(f"\n{'-'*70}")
    print(f"TOP GAMES (by confidence)")
    print(f"{'-'*70}")
    for g in consensus[:15]:
        src_str = "/".join(s[:2].upper() for s in g.sources)
        flag_str = " [!]" if g.flags else ""
        spread_str = f"spread={g.spread_home}" if g.spread_home is not None else "no spread"
        total_str = f"total={g.total}" if g.total is not None else ""
        ml_str = f"ML={g.moneyline_home}/{g.moneyline_away}" if g.moneyline_home is not None else ""
        print(f"  [{g.confidence:.0%}] {g.away_team} @ {g.home_team} | {spread_str} {total_str} {ml_str} [{src_str}]{flag_str}")

    # Show flagged games
    if flagged:
        print(f"\n{'-'*70}")
        print(f"FLAGGED DISCREPANCIES ({flagged})")
        print(f"{'-'*70}")
        for g in consensus:
            if g.flags:
                print(f"  {g.away_team} @ {g.home_team}")
                for f in g.flags:
                    print(f"    [!] {f}")

    # Save if requested
    if save:
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"consensus_{sport}_{date_str}.json"
        output = {
            "sport": sport,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {k: len(v) for k, v in active_sources.items()},
            "summary": {
                "total_games": total_games,
                "with_spread": with_spread,
                "with_total": with_total,
                "with_ml": with_ml,
                "multi_source": multi_source,
                "triple_source": triple_source,
                "flagged": flagged,
            },
            "games": [g.to_dict() for g in consensus],
        }
        with open(filename, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nSaved to {filename}")

    return consensus


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    sport = "ncaab"
    save = False
    use_pw = True

    for arg in sys.argv[1:]:
        if arg in ("ncaab", "nba", "nhl", "mlb"):
            sport = arg
        elif arg == "--save":
            save = True
        elif arg == "--no-playwright":
            use_pw = False

    asyncio.run(run_consensus(sport=sport, use_playwright=use_pw, save=save))
