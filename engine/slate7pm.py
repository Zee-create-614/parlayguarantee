import json

with open('engine/dfs_output.json') as f:
    data = json.load(f)

# 7pm slate teams (7:10 + 7:40)
slate = {'CLE','BKN','HOU','CHA','IND','WAS','ATL','PHI','NYK','DET','MIN','DAL'}

all_players = {}
for platform in ['draftkings','fanduel']:
    for lineup in data.get('lineups',{}).get(platform,[]):
        for p in lineup['players']:
            if p['team'] in slate:
                key = p['name']
                if key not in all_players or p['projected'] > all_players[key]['projected']:
                    all_players[key] = p

ranked = sorted(all_players.values(), key=lambda x: x['projected'], reverse=True)
print("=== ALL 7PM SLATE PLAYERS IN ENGINE ===")
for p in ranked:
    print(f"{p.get('position',''):6s} {p['name']:28s} {p.get('team',''):5s} ${p.get('salary',0):>6}  {p.get('projected',0):>6.1f}fp  {p.get('value',0):.2f}x")

print(f"\nTotal players on slate: {len(ranked)}")
