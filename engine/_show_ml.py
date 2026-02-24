import json
with open('analyzed_games.json') as f:
    games = json.load(f)
nba = [g for g in games if g.get('sport') == 'NBA']
for g in nba:
    home = g['home']
    away = g['away']
    spread = g['spread']
    pick = g['pick']
    hml = g.get('ml_home_prob', 0)
    aml = g.get('ml_away_prob', 0)
    print(f"{away:20s} @ {home:20s} | spd={spread:+5.1f} | pick={pick:20s} | ML: H={hml:.2f} A={aml:.2f}")
