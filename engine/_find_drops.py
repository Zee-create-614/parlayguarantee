import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from team_name_mapper import normalize_team
from consensus_engine import build_consensus
from sportsbook_scraper import FanDuelScraper, OddsAPIScraper
import asyncio

async def main():
    fd = await FanDuelScraper(sport='ncaab').scrape()
    oa = await OddsAPIScraper(sport='ncaab').scrape()
    print(f"FD: {len(fd)}, OA: {len(oa)}")

    # Build index for each source
    fd_idx = {}
    for g in fd:
        key = (normalize_team(g.home_team), normalize_team(g.away_team))
        fd_idx[key] = g
    
    oa_idx = {}
    for g in oa:
        key = (normalize_team(g.home_team), normalize_team(g.away_team))
        oa_idx[key] = g

    # Find FD games not in OA
    fd_only = []
    for key, g in fd_idx.items():
        if key not in oa_idx and (key[1], key[0]) not in oa_idx:
            fd_only.append((key, g))
    
    oa_only = []
    for key, g in oa_idx.items():
        if key not in fd_idx and (key[1], key[0]) not in fd_idx:
            oa_only.append((key, g))

    print(f"\nFD-only ({len(fd_only)}):")
    for (h, a), g in fd_only:
        print(f"  {g.away_team:30s} @ {g.home_team:30s} -> ({a} @ {h})")
    
    print(f"\nOA-only ({len(oa_only)}):")
    for (h, a), g in oa_only:
        print(f"  {g.away_team:30s} @ {g.home_team:30s} -> ({a} @ {h})")

asyncio.run(main())
