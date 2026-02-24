"""Generate optimal DFS lineup for 7PM DraftKings slate (7 games)"""
import json

# 7PM slate teams
SLATE_TEAMS = {'IND','WAS','HOU','CHA','BKN','CLE','ATL','PHI','DET','NYK','TOR','CHI','PHX','SAS'}

d = json.load(open('dfs_output.json'))

# Get all players
players = d.get('player_pool', [])
if players:
    slate = [p for p in players if p.get('team','') in SLATE_TEAMS]
    slate.sort(key=lambda x: x.get('projected',0), reverse=True)
    print(f"Found {len(slate)} players in 7PM slate\n")
    for p in slate[:40]:
        print(f"{p.get('position',''):6s} {p['name']:25s} {p.get('team',''):5s} ${p.get('salary',0):>6} {p.get('projected',0):>6.1f}fp  val:{p.get('value',0):.2f}")
else:
    print("No player pool found. Showing lineup players filtered to slate teams:")
    all_p = []
    for lineup in d.get('lineups',{}).get('draftkings',[]):
        for p in lineup.get('players',[]):
            if p.get('team','') in SLATE_TEAMS:
                all_p.append(p)
    seen = set()
    for p in all_p:
        if p['name'] not in seen:
            seen.add(p['name'])
            print(f"{p.get('position',''):6s} {p['name']:25s} {p.get('team',''):5s} ${p.get('salary',0):>6} {p.get('projected',0):>6.1f}fp")
