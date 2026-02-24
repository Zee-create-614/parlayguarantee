import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from team_name_mapper import normalize_team

with open('consensus_ncaab_2026-02-21.json') as f:
    data = json.load(f)

# Get all team names per source
source_teams = {}
for g in data['games']:
    for src, lines in g.get('source_lines', {}).items():
        if src not in source_teams:
            source_teams[src] = set()
        source_teams[src].add((lines.get('home_team',''), lines.get('away_team','')))

# Find single-source games and their raw names
singles = [g for g in data['games'] if len(g['sources']) == 1]
print(f"Single-source games: {len(singles)}")
for g in singles:
    src = g['sources'][0]
    raw = g['source_lines'][src]
    raw_home = raw.get('home_team','')
    raw_away = raw.get('away_team','')
    norm_home = normalize_team(raw_home)
    norm_away = normalize_team(raw_away)
    changed_h = raw_home != norm_home
    changed_a = raw_away != norm_away
    print(f"  [{src}] {raw_away} @ {raw_home}")
    print(f"    -> {norm_away} @ {norm_home} {'*' if changed_h or changed_a else ''}")
