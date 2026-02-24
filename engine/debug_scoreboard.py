from nba_api.stats.endpoints import scoreboardv2
import time, json, pandas as pd
time.sleep(1)
sb = scoreboardv2.ScoreboardV2(game_date='01/01/2026', timeout=60)
data = sb.get_dict()
result_sets = data['resultSets']
print(f'Number of result sets: {len(result_sets)}')
for rs in result_sets:
    rows = rs.get('rowSet', [])
    headers = rs.get('headers', [])
    print(f"  {rs['name']}: {len(rows)} rows, headers={headers[:8]}")
    if rows and len(rows) > 0:
        print(f"    first row: {rows[0][:8]}")
