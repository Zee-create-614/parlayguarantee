#!/usr/bin/env python3
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open(Path(__file__).parent / 'analyzed_games.json', encoding='utf-8') as f:
    ALL_GAMES = json.load(f)

spreads = []
for g in ALL_GAMES:
    p = g.get('enhanced_prob', g.get('cover_prob', 0.5))
    spreads.append({'team': g['pick'], 'spread': g.get('spread_str',''), 'prob': p,
                    'sport': g['sport'], 'home': g['home'], 'away': g['away'], 'type': 'spread'})

ous = []
for g in ALL_GAMES:
    v3 = g.get('ou_model_v3', {})
    if v3.get('pick','PASS') != 'PASS':
        total = v3.get('posted_total', g.get('total_line', 0))
        ous.append({'team': f"{g['home']} vs {g['away']}", 
                    'spread': f"{v3['pick']} {total}",
                    'prob': v3.get('confidence', 0.5), 'sport': g['sport'],
                    'home': g['home'], 'away': g['away'], 'type': 'ou',
                    'edge': v3.get('edge', 0)})

ncaab_sp = sorted([s for s in spreads if s['sport'] == 'NCAAB'], key=lambda x: x['prob'], reverse=True)
nba_sp = sorted([s for s in spreads if s['sport'] == 'NBA'], key=lambda x: x['prob'], reverse=True)
ous.sort(key=lambda x: x['prob'], reverse=True)

hm = []
used = set()

# 5 best NCAAB spreads
for s in ncaab_sp:
    if len([x for x in hm if x['type'] == 'spread' and x['sport'] == 'NCAAB']) >= 5:
        break
    if s['home'] not in used:
        hm.append(s)
        used.add(s['home'])

# 3 NBA spreads
for s in nba_sp:
    if len([x for x in hm if x['type'] == 'spread' and x['sport'] == 'NBA']) >= 3:
        break
    if s['home'] not in used:
        hm.append(s)
        used.add(s['home'])

# 5 O/U on different games
for o in ous:
    if len([x for x in hm if x['type'] == 'ou']) >= 5:
        break
    if o['home'] not in used:
        hm.append(o)
        used.add(o['home'])

# Fill to 14 with remaining spreads
for s in ncaab_sp + nba_sp:
    if len(hm) >= 14:
        break
    if s['home'] not in used:
        hm.append(s)
        used.add(s['home'])

cp = 1.0
for l in hm:
    cp *= l['prob']
american = round((1 - cp) / cp * 100)
payout = round(10 * (american / 100 + 1), 2)

sp_c = sum(1 for l in hm if l['type'] == 'spread')
ou_c = sum(1 for l in hm if l['type'] == 'ou')
nba_c = sum(1 for l in hm if l['sport'] == 'NBA')
ncaab_c = sum(1 for l in hm if l['sport'] == 'NCAAB')

print(f"TICKET #8 — 14-LEG HAIL MARY (+{american:,} | $10 → ${payout:,.2f})")
print(f"Mix: {sp_c} spreads + {ou_c} O/U | {nba_c} NBA + {ncaab_c} NCAAB")
print(f"Combined: {cp:.4%}")
print("─" * 60)
for i, l in enumerate(hm, 1):
    if l['type'] == 'ou':
        print(f"  {i:2d}. 📊 {l['spread']} [{l['sport']}] — {l['prob']:.0%} | edge {l.get('edge',0):+.1f}")
    else:
        print(f"  {i:2d}. 🏀 {l['team']} {l['spread']} [{l['sport']}] — {l['prob']:.1%}")
