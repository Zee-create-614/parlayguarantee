import os, time, random
os.environ['PYTHONIOENCODING'] = 'utf-8'
from nba_api.stats.endpoints import boxscoretraditionalv2
from nba_api.stats.library.http import NBAStatsHTTP
from dfs_backtest_comprehensive import Player, DFSBacktester

# Get a 4-game night
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

print(f"Games: {game_ids}")
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
bt = DFSBacktester([])
lineups, strategies = bt.generate_lineups(players, 'draftkings')
print(f"DK lineups: {len(lineups)}")
for i, (lu, s) in enumerate(zip(lineups, strategies)):
    score = sum(p.dk_score for p in lu)
    sal = sum(p.estimated_salary for p in lu)
    print(f"  {i+1} ({s}): {score:.1f} pts, ${sal}")

lineups2, strats2 = bt.generate_lineups(players, 'fanduel')
print(f"FD lineups: {len(lineups2)}")
