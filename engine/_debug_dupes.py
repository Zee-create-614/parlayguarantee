import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open('consensus_ncaab_2026-02-21.json') as f:
    data = json.load(f)

games = data['games']
print(f"Total consensus games: {len(games)}")

# Count by source count
from collections import Counter
src_counts = Counter()
for g in games:
    src_counts[len(g['sources'])] += 1
print(f"By source count: {dict(src_counts)}")

# Find single-source games (likely dupes or mismatches)
singles = [g for g in games if len(g['sources']) == 1]
print(f"\nSingle-source games ({len(singles)}):")
for g in singles[:20]:
    print(f"  {g['away_team']} @ {g['home_team']} [{g['sources'][0]}]")

# Check for near-duplicate team names
all_teams = set()
for g in games:
    all_teams.add(g['home_team'].lower())
    all_teams.add(g['away_team'].lower())

# Find similar teams
teams_list = sorted(all_teams)
from difflib import SequenceMatcher
print(f"\nSimilar team names (potential dupes):")
for i, t1 in enumerate(teams_list):
    for t2 in teams_list[i+1:]:
        ratio = SequenceMatcher(None, t1, t2).ratio()
        if ratio > 0.7 and ratio < 1.0:
            print(f"  '{t1}' vs '{t2}' ({ratio:.0%})")
