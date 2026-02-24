from nba_api.stats.endpoints import teamgamelog
import time
time.sleep(1)
gl = teamgamelog.TeamGameLog(team_id=1610612738, season='2024-25', timeout=60)
data = gl.get_dict()
rs = data['resultSets'][0]
print(f"Headers: {rs['headers']}")
print(f"Rows: {len(rs['rowSet'])}")
if rs['rowSet']:
    print(f"First: {rs['rowSet'][0]}")
