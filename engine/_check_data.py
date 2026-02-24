import json

data = json.load(open('results_raw.json'))
nba_teams = ['Thunder','Cavaliers','Warriors','Lakers','Celtics','Hawks','Nets','Bucks','Raptors','Nuggets','Mavericks','Pacers','Hornets','Wizards','76ers','Timberwolves','Knicks','Bulls','Suns','Clippers','Magic','Kings','Heat','Rockets','Spurs','Grizzlies','Pelicans','Jazz','Pistons','Trail Blazers']

nba = [g for g in data if any(t in str(g.get('home','')) for t in nba_teams)]
ncaab = [g for g in data if g not in nba]

print(f"Total: {len(data)}, NBA: {len(nba)}, NCAAB: {len(ncaab)}")

if nba:
    print("\nSample NBA game:")
    print(json.dumps(nba[0], indent=2))
    
    scored = sum(1 for g in nba if g.get('actual_home_score') is not None)
    print(f"\nNBA with actual scores: {scored}/{len(nba)}")
    
    # Check spread data
    has_spread = sum(1 for g in nba if g.get('spread_line') is not None or g.get('spread_pick'))
    print(f"NBA with spread data: {has_spread}/{len(nba)}")
