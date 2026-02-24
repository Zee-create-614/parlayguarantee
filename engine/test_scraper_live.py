"""
test_scraper_live.py — Live validation test for ParlayGuarantee scrapers.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta

from book_scraper import FanDuelScraper, ESPNScraper
from consensus import build_consensus
from team_name_mapper import normalize_team

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


def fmt_odds(v):
    if v is None:
        return "---"
    return f"{v:+d}" if isinstance(v, int) else str(v)


def fmt_spread(v):
    if v is None:
        return "---"
    return f"{v:+.1f}"


async def main():
    print("=" * 80)
    print(f"  PARLAYGUARANTEE NCAAB SCRAPER — LIVE TEST")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 80)

    fd = FanDuelScraper()
    espn = ESPNScraper()

    print("\n>>> Scraping FanDuel...")
    fd_games = await fd.scrape()
    print(f"    FanDuel: {len(fd_games)} games")

    print("\n>>> Scraping ESPN...")
    espn_games = await espn.scrape()
    print(f"    ESPN: {len(espn_games)} games")

    # Show first 10 from each
    print(f"\n{'='*80}")
    print("  FANDUEL — First 10 games")
    print(f"{'='*80}")
    print(f"  {'Matchup':<45} {'Spread':>8} {'Total':>7} {'ML H':>7} {'ML A':>7}")
    print(f"  {'-'*45} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")
    for g in fd_games[:10]:
        matchup = f"{g.away_team} @ {g.home_team}"
        if len(matchup) > 44:
            matchup = matchup[:41] + "..."
        print(f"  {matchup:<45} {fmt_spread(g.spread_home):>8} {fmt_spread(g.total) if g.total else '---':>7} {fmt_odds(g.moneyline_home):>7} {fmt_odds(g.moneyline_away):>7}")

    print(f"\n{'='*80}")
    print("  ESPN — First 10 games")
    print(f"{'='*80}")
    print(f"  {'Matchup':<45} {'Spread':>8} {'Total':>7} {'ML H':>7} {'ML A':>7} {'Status'}")
    print(f"  {'-'*45} {'-'*8} {'-'*7} {'-'*7} {'-'*7} {'-'*6}")
    for g in espn_games[:10]:
        matchup = f"{g.away_team} @ {g.home_team}"
        if len(matchup) > 44:
            matchup = matchup[:41] + "..."
        status = g.status or ""
        print(f"  {matchup:<45} {fmt_spread(g.spread_home):>8} {fmt_spread(g.total) if g.total else '---':>7} {fmt_odds(g.moneyline_home):>7} {fmt_odds(g.moneyline_away):>7} {status}")

    # Consensus
    print(f"\n{'='*80}")
    print("  CONSENSUS RESULTS")
    print(f"{'='*80}")
    consensus = build_consensus({"fanduel": fd_games, "espn": espn_games})

    high = [g for g in consensus if g.confidence == "HIGH"]
    med = [g for g in consensus if g.confidence == "MEDIUM"]
    espn_only = [g for g in consensus if g.confidence == "ESPN_ONLY"]
    flagged = [g for g in consensus if g.flags]

    print(f"\n  Total: {len(consensus)} games")
    print(f"  HIGH confidence (both sources): {len(high)}")
    print(f"  MEDIUM (FanDuel only):          {len(med)}")
    print(f"  ESPN_ONLY:                      {len(espn_only)}")
    print(f"  Flagged discrepancies:          {len(flagged)}")

    if high:
        print(f"\n  --- HIGH CONFIDENCE (first 10) ---")
        print(f"  {'Matchup':<45} {'Spread':>8} {'Total':>7} {'ML H':>7} {'ML A':>7}")
        print(f"  {'-'*45} {'-'*8} {'-'*7} {'-'*7} {'-'*7}")
        for g in high[:10]:
            matchup = f"{g.away_team} @ {g.home_team}"
            if len(matchup) > 44:
                matchup = matchup[:41] + "..."
            print(f"  {matchup:<45} {fmt_spread(g.spread_home):>8} {fmt_spread(g.total) if g.total else '---':>7} {fmt_odds(g.moneyline_home):>7} {fmt_odds(g.moneyline_away):>7}")

    if flagged:
        print(f"\n  --- FLAGGED DISCREPANCIES ---")
        for g in flagged:
            print(f"  [!] {g.away_team} @ {g.home_team}")
            for f in g.flags:
                print(f"      {f}")

    print(f"\n{'='*80}")
    print("  TEST COMPLETE [OK]")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
