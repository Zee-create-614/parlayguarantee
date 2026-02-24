from nba_api.stats.endpoints import scoreboardv2
import time
time.sleep(1)
sb = scoreboardv2.ScoreboardV2(game_date='01/01/2026', timeout=60)
data = sb.get_dict()
ls = data['resultSets'][1]
print(f"LineScore headers: {ls['headers']}")
print(f"First row: {ls['rowSet'][0]}")
