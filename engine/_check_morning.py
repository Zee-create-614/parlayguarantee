import json

ncaab = json.load(open(r'picks_2026-02-22/ncaab_spread_picks.json'))
nba = json.load(open(r'picks_2026-02-22/nba_spread_picks.json'))

print("NCAAB (morning picks):")
for g in sorted(ncaab, key=lambda x: -x['confidence']):
    print(f"  {g['away_team']} vs {g['home_team']}: {g['confidence']}% {'UPSET' if g.get('is_upset_play') else ''}")

print("\nNBA (morning picks):")
for g in sorted(nba, key=lambda x: -x['confidence']):
    print(f"  {g['away_team']} vs {g['home_team']}: {g['confidence']}% {'UPSET' if g.get('is_upset_play') else ''}")

print("\n--- Now check analyzed_games.json (overwritten at 4pm) ---")
ag = json.load(open('analyzed_games.json'))
print(f"analyzed_games.json has {len(ag)} games")
for g in ag[:3]:
    print(f"  Keys: {list(g.keys())[:10]}")
    print(f"  confidence key? {'confidence' in g}")
