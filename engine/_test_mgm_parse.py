"""Test BetMGM fixture parsing against captured data"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
from playwright_scrapers import _parse_betmgm_fixture

with open("mgm_fixtures.json") as f:
    data = json.load(f)

fixtures = data["fixtures"]
print(f"Total fixtures: {len(fixtures)}")

# Check sport distribution
sports = {}
for fix in fixtures:
    sport = fix.get("sport", {})
    if isinstance(sport, dict):
        sport = sport.get("name", {})
        if isinstance(sport, dict):
            sport = sport.get("value", "?")
    sports[sport] = sports.get(sport, 0) + 1
print(f"Sports: {sports}")

# Parse all
parsed = 0
failed = 0
for fix in fixtures:
    result = _parse_betmgm_fixture(fix)
    if result and result.home_team and result.away_team:
        parsed += 1
        has_odds = result.moneyline_home is not None or result.spread_home is not None
        print(f"  {result.away_team} @ {result.home_team} | ML={result.moneyline_away}/{result.moneyline_home} spread={result.spread_home} total={result.total} {'OK' if has_odds else 'NO ODDS'}")
    else:
        name = fix.get("name", {})
        if isinstance(name, dict):
            name = name.get("value", "?")
        failed += 1
        if failed <= 5:
            print(f"  FAILED: {name}")

print(f"\nParsed: {parsed}, Failed: {failed}")
