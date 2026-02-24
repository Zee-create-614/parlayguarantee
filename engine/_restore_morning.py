"""Restore analyzed_games.json from the morning's correct spread picks."""
import json

ncaab = json.load(open(r'picks_2026-02-22/ncaab_spread_picks.json'))
nba = json.load(open(r'picks_2026-02-22/nba_spread_picks.json'))

all_games = ncaab + nba
json.dump(all_games, open('analyzed_games.json', 'w'), indent=2)
print(f"Restored {len(all_games)} games to analyzed_games.json")
print(f"  NCAAB: {len(ncaab)}, NBA: {len(nba)}")
