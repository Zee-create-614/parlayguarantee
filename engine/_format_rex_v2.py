import json, sys
sys.stdout.reconfigure(encoding='utf-8')

with open('rex_v2_ncaab_picks_2026-02-24.json') as f:
    picks = json.load(f)

real = [p for p in picks if p.get('spread_status') == 'PICK']
real.sort(key=lambda x: x.get('spread_confidence', 0), reverse=True)

lines = []
lines.append('\U0001f996 REX V2 \u2014 NCAAB Feb 24, 2026')
lines.append('45-Factor Model | Spread Floor: 55%')
lines.append(f'{len(real)} PICKS | {len(picks)-len(real)} PASSES | {len(picks)} Games')
lines.append('')

for i, p in enumerate(real, 1):
    sp = p.get('spread_pick', '')
    sc = p.get('spread_confidence', 0)
    w = p.get('predicted_winner', '')
    mc = p.get('confidence', 0)
    away = p.get('away_team', '')
    home = p.get('home_team', '')
    uc = p.get('upset_composite', 0)
    flag = ' \U0001f525' if uc > 0.3 else ''
    lines.append(f'{i}. {away} @ {home}')
    lines.append(f'   Spread: {sp} ({sc:.0%})')
    lines.append(f'   ML: {w} ({mc:.0%}){flag}')
    lines.append('')

print('\n'.join(lines))
