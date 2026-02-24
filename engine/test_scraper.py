"""
Test suite for the sportsbook scraper system.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sportsbook_scraper import DraftKingsScraper, FanDuelScraper, OddsAPIScraper, GameLine
from team_name_mapper import normalize_team, are_same_team, fuzzy_match
from consensus_engine import build_consensus, ConsensusGame


def test_team_name_mapper():
    print("=== Team Name Mapper Tests ===")
    cases = [
        ("UConn", "UConn"),
        ("Connecticut", "UConn"),
        ("UCONN Huskies", "UConn"),
        ("Duke Blue Devils", "Duke"),
        ("Duke", "Duke"),
        ("NC State", "NC State"),
        ("North Carolina State", "NC State"),
        ("Michigan St", "Michigan State"),
        ("St. John's Red Storm", "St. John's"),
        ("Saint John's", "St. John's"),
        ("Gonzaga Bulldogs", "Gonzaga"),
    ]
    passed = 0
    for input_name, expected in cases:
        result = normalize_team(input_name)
        ok = result == expected
        status = "✅" if ok else "❌"
        print(f"  {status} normalize('{input_name}') = '{result}' (expected '{expected}')")
        if ok:
            passed += 1

    # Test are_same_team
    assert are_same_team("UConn", "Connecticut Huskies"), "UConn == Connecticut Huskies"
    assert are_same_team("Duke Blue Devils", "Duke"), "Duke variants"
    assert not are_same_team("Duke", "UNC"), "Duke != UNC"
    print(f"  ✅ are_same_team assertions passed")
    passed += 1

    print(f"  {passed}/{len(cases)+1} passed\n")
    return passed == len(cases) + 1


def test_consensus_logic():
    print("=== Consensus Logic Tests ===")

    # Mock data: 3 sources agree closely
    games = {
        "draftkings": [
            GameLine("Duke", "North Carolina", "2025-02-21T19:00:00Z", -3.5, 3.5, 145.5, -160, 140, "draftkings"),
        ],
        "fanduel": [
            GameLine("Duke Blue Devils", "UNC", "2025-02-21T19:00:00Z", -3.0, 3.0, 146.0, -155, 135, "fanduel"),
        ],
        "odds_api": [
            GameLine("Duke Blue Devils", "North Carolina Tar Heels", "2025-02-21T19:00:00Z", -3.5, 3.5, 145.5, -158, 138, "odds_api"),
        ],
    }

    result = build_consensus(games)
    assert len(result) == 1, f"Expected 1 game, got {len(result)}"
    g = result[0]
    assert g.home_team == "Duke", f"Home team should be Duke, got {g.home_team}"
    assert len(g.sources) == 3, f"Expected 3 sources, got {len(g.sources)}"
    assert g.spread_home is not None, "Spread should exist"
    assert abs(g.spread_home - (-3.5)) <= 0.5, f"Spread should be ~-3.5, got {g.spread_home}"
    print(f"  ✅ 3-source consensus: spread={g.spread_home} total={g.total} conf={g.confidence}")

    # Test disagreement flagging
    games_disagree = {
        "draftkings": [
            GameLine("Duke", "UNC", None, -3.5, 3.5, 145.5, -160, 140, "draftkings"),
        ],
        "fanduel": [
            GameLine("Duke", "North Carolina", None, -7.0, 7.0, 145.5, -155, 135, "fanduel"),
        ],
    }
    result2 = build_consensus(games_disagree)
    assert len(result2) == 1
    assert len(result2[0].flags) > 0, "Should have flags for disagreement"
    print(f"  ✅ Disagreement flagged: {result2[0].flags}")

    print(f"  All consensus tests passed\n")
    return True


async def test_live_scrapers():
    print("=== Live Scraper Tests ===")
    results = {}

    # DraftKings
    try:
        dk = DraftKingsScraper()
        dk_games = await dk.scrape()
        results["draftkings"] = len(dk_games)
        print(f"  DraftKings: {len(dk_games)} games")
        if dk_games:
            g = dk_games[0]
            print(f"    Sample: {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total}")
    except Exception as e:
        print(f"  ❌ DraftKings failed: {e}")
        results["draftkings"] = 0

    # FanDuel
    try:
        fd = FanDuelScraper()
        fd_games = await fd.scrape()
        results["fanduel"] = len(fd_games)
        print(f"  FanDuel: {len(fd_games)} games")
        if fd_games:
            g = fd_games[0]
            print(f"    Sample: {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total}")
    except Exception as e:
        print(f"  ❌ FanDuel failed: {e}")
        results["fanduel"] = 0

    # Odds API
    try:
        oa = OddsAPIScraper()
        oa_games = await oa.scrape()
        results["odds_api"] = len(oa_games)
        print(f"  OddsAPI: {len(oa_games)} games")
        if oa_games:
            g = oa_games[0]
            print(f"    Sample: {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total}")
    except Exception as e:
        print(f"  ❌ OddsAPI failed: {e}")
        results["odds_api"] = 0

    total = sum(results.values())
    print(f"\n  Total across sources: {total}")
    print(f"  Results: {results}")
    return results


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("NCAAB Scraper System — Test Suite")
    print("=" * 60 + "\n")

    # Unit tests
    mapper_ok = test_team_name_mapper()
    consensus_ok = test_consensus_logic()

    # Live tests
    live_results = asyncio.run(test_live_scrapers())

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Team mapper:  {'✅' if mapper_ok else '❌'}")
    print(f"  Consensus:    {'✅' if consensus_ok else '❌'}")
    print(f"  DraftKings:   {live_results.get('draftkings', 0)} games")
    print(f"  FanDuel:      {live_results.get('fanduel', 0)} games")
    print(f"  OddsAPI:      {live_results.get('odds_api', 0)} games")
