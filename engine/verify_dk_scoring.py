"""Verify DraftKings scoring against real box score data"""
from nba_api.stats.endpoints import boxscoretraditionalv3

bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id='0022400305')
d = bs.get_dict()

all_players = []
for team_key in ['homeTeam', 'awayTeam']:
    team = d['boxScoreTraditional'][team_key]
    team_name = team['teamName']
    for p in team['players']:
        s = p['statistics']
        pts = s.get('points', 0) or 0
        if pts >= 15:
            tpm = s.get('threePointersMade', 0) or 0
            reb = s.get('reboundsTotal', 0) or 0
            ast = s.get('assists', 0) or 0
            stl = s.get('steals', 0) or 0
            blk = s.get('blocks', 0) or 0
            to = s.get('turnovers', 0) or 0
            
            doubles = sum(1 for x in [pts, reb, ast, stl, blk] if x >= 10)
            dd = 1 if doubles >= 2 else 0
            td = 1 if doubles >= 3 else 0
            
            dk = pts + tpm*0.5 + reb*1.25 + ast*1.5 + stl*2 + blk*2 + to*(-0.5) + dd*1.5 + td*3
            fd = pts + reb*1.2 + ast*1.5 + stl*3 + blk*3 + to*(-1)
            
            name = p['firstName'] + ' ' + p['familyName']
            pos = p.get('position', '?')
            print(f"{name} ({team_name}, {pos}): PTS={pts} 3PM={tpm} REB={reb} AST={ast} STL={stl} BLK={blk} TO={to} | DK={dk:.1f} FD={fd:.1f}")
            all_players.append(dk)

print(f"\nTop 8 DK scores sum: {sum(sorted(all_players, reverse=True)[:8]):.1f}")
print(f"Top 9 DK scores sum (FD proxy): {sum(sorted(all_players, reverse=True)[:9]):.1f}")
