import json
picks = json.load(open('ncaab_picks_2026-02-20.json'))
print(f'Total NCAAB picks: {len(picks)}')
for p in picks:
    away = p.get('away_team','')
    home = p.get('home_team','')
    winner = p.get('predicted_winner','')
    conf = p.get('confidence',0)
    print(f'  {away} @ {home} -> {winner} ({conf})')
