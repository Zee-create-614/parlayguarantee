import os, time, random
os.environ['PYTHONIOENCODING'] = 'utf-8'
from nba_api.stats.endpoints import boxscoretraditionalv2

time.sleep(1)
bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id='0022400061')
data = bs.get_normalized_dict()

from dfs_backtest_comprehensive import Player, DFSBacktester

players = []
for pd in data['PlayerStats']:
    mins = pd.get('MIN', '')
    if not mins or mins == '0:00' or mins is None:
        continue
    stats = {k: pd.get(k, 0) for k in ['PTS','FG3M','REB','AST','STL','BLK','TO']}
    p = Player(
        person_id=str(pd.get('PLAYER_ID', '')),
        name=pd.get('PLAYER_NAME', ''),
        position=pd.get('START_POSITION', '') or '',
        team=pd.get('TEAM_ABBREVIATION', ''),
        stats=stats
    )
    if p.name and p.dk_score > 0:
        players.append(p)

print(f"{len(players)} players")

# Manual build
positions = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']
salary_cap = 50000
available = sorted(players, key=lambda p: p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0, reverse=True)

used = set()
remaining = salary_cap

for pos in positions:
    found = False
    for p in available:
        if p.person_id in used or p.estimated_salary > remaining:
            continue
        elig = p.get_position_eligibility()
        if pos in elig:
            print(f"  {pos}: {p.name} (pos='{p.position}', elig={elig}, sal=${p.estimated_salary}, dk_proj={p.projected_dk:.1f})")
            used.add(p.person_id)
            remaining -= p.estimated_salary
            found = True
            break
    if not found:
        print(f"  {pos}: FAILED TO FILL! remaining_sal=${remaining}")
        # Show who's left
        for p in available:
            if p.person_id not in used:
                elig = p.get_position_eligibility()
                print(f"    Available: {p.name} pos='{p.position}' elig={elig} sal=${p.estimated_salary}")
        break
