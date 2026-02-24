import os, time, random
os.environ['PYTHONIOENCODING'] = 'utf-8'
from nba_api.stats.endpoints import boxscoretraditionalv2

time.sleep(1)
bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id='0022400061')
data = bs.get_normalized_dict()
positions = {}
for p in data['PlayerStats']:
    pos = p.get('START_POSITION', '')
    positions[pos] = positions.get(pos, 0) + 1
    if pos:
        print(f"{p['PLAYER_NAME']}: pos={pos}")
print(f"\nPosition counts: {positions}")

# Now test lineup generation
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

print(f"\n{len(players)} players")
for p in players[:5]:
    print(f"  {p.name}: pos='{p.position}', elig={p.get_position_eligibility()}, dk={p.dk_score:.1f}")

bt = DFSBacktester([])
lineups, strategies = bt.generate_lineups(players, 'draftkings')
print(f"\nDK lineups generated: {len(lineups)}")
for i, (lu, s) in enumerate(zip(lineups, strategies)):
    score = sum(p.dk_score for p in lu)
    print(f"  Lineup {i+1} ({s}): {score:.1f} pts")
