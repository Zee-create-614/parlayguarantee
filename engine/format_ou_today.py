import json, sys
sys.stdout.reconfigure(encoding='utf-8')
picks = json.load(open('picks_2026-02-22/ncaab_ou_picks.json'))
picks.sort(key=lambda x: x['confidence'], reverse=True)
for p in picks:
    arrow = '\u2b06' if p['ou_pick'] == 'Over' else '\u2b07'
    conf = int(p['confidence'] * 100)
    away = p['away_team']
    home = p['home_team']
    total = p['total']
    direction = p['ou_pick']
    print(f"{arrow} {away} @ {home} \u2014 {direction} {total} ({conf}%) [NCAAB]")
