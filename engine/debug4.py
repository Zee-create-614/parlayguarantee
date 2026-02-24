import os, time, random
os.environ['PYTHONIOENCODING'] = 'utf-8'
from nba_api.stats.endpoints import boxscoretraditionalv2
from nba_api.stats.library.http import NBAStatsHTTP
from dfs_backtest_comprehensive import Player, DFSBacktester

http = NBAStatsHTTP()
time.sleep(1)
resp = http.send_api_request(endpoint='scoreboardv2',
    parameters={'GameDate': '2024-10-24', 'LeagueID': '00', 'DayOffset': '0'})
data = resp.get_dict()
game_ids = []
for rs in data.get('resultSets', []):
    if rs.get('name') == 'GameHeader':
        headers = rs['headers']
        rows = rs['rowSet']
        gid_idx = headers.index('GAME_ID')
        game_ids = [row[gid_idx] for row in rows]

players = []
for gid in game_ids:
    time.sleep(1)
    bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=gid)
    d = bs.get_normalized_dict()
    for pd in d['PlayerStats']:
        mins = pd.get('MIN', '')
        if not mins or mins == '0:00' or mins is None:
            continue
        stats = {k: pd.get(k, 0) for k in ['PTS','FG3M','REB','AST','STL','BLK','TO']}
        p = Player(person_id=str(pd.get('PLAYER_ID', '')), name=pd.get('PLAYER_NAME', ''),
                   position=pd.get('START_POSITION', '') or '', team=pd.get('TEAM_ABBREVIATION', ''), stats=stats)
        if p.name and p.dk_score > 0:
            players.append(p)

print(f"{len(players)} players")

# Manual DK lineup build with debug
positions = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']
salary_cap = 50000
min_salary = 3500
sort_key = lambda p: p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0
available = sorted(players, key=sort_key, reverse=True)
lineup, used, remaining = [], set(), salary_cap

for i, pos in enumerate(positions):
    slots_left = len(positions) - i - 1
    max_for_slot = remaining - (slots_left * min_salary)
    best = None
    for p in available:
        if p.person_id in used or p.estimated_salary > max_for_slot:
            continue
        if pos in p.get_position_eligibility():
            best = p
            break
    if best:
        lineup.append(best)
        used.add(best.person_id)
        remaining -= best.estimated_salary
        print(f"  {pos}: {best.name} (pos='{best.position}', sal=${best.estimated_salary}, max_for_slot=${max_for_slot}, remaining=${remaining})")
    else:
        print(f"  {pos}: FAILED! max_for_slot=${max_for_slot}, remaining=${remaining}")
        # Check what's available
        avail_for_pos = [p for p in available if p.person_id not in used and pos in p.get_position_eligibility()]
        print(f"    {len(avail_for_pos)} players eligible for {pos}")
        if avail_for_pos:
            cheapest = min(avail_for_pos, key=lambda p: p.estimated_salary)
            print(f"    Cheapest: {cheapest.name} ${cheapest.estimated_salary}")
        break
