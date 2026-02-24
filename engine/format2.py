import json, os
base = 'picks_2026-02-21'
picks = []
for fname, sport in [('nba_ml_spread.json','NBA'),('ncaab_ml_spread.json','NCAAB')]:
    with open(os.path.join(base, fname), encoding='utf-8') as f:
        data = json.load(f)
    for p in data['picks']:
        covers = p['ml_pick'] == p['spread_pick']
        picks.append({
            'sport': sport, 'away': p['away'], 'home': p['home'],
            'pick': p['ml_pick'], 'prob': p['ml_prob'],
            'spread': p['spread_line'], 'side': p['spread_side'], 'covers': covers
        })

nba = sorted([p for p in picks if p['sport']=='NBA'], key=lambda x: x['prob'], reverse=True)
ncaab = sorted([p for p in picks if p['sport']=='NCAAB'], key=lambda x: x['prob'], reverse=True)
covers = sum(1 for p in picks if p['covers'])
ml_only = len(picks) - covers

lines = []
lines.append(f"ALL PICKS - Feb 21 (1 PM Run)")
lines.append(f"{len(picks)} total | Covers: {covers} | ML Only: {ml_only}")
lines.append(f"DK/FanDuel/BetMGM only | 10 started games filtered out")
lines.append("")
lines.append(f"NBA ({len(nba)} picks)")
for i,p in enumerate(nba,1):
    icon = "\u2705\u2705" if p['covers'] else "\u2705\u274c"
    lines.append(f"{i}. {icon} {p['pick']} ({p['prob']*100:.1f}%) | {p['away']} @ {p['home']}")
lines.append("")
lines.append(f"NCAAB ({len(ncaab)} picks)")
for i,p in enumerate(ncaab,1):
    icon = "\u2705\u2705" if p['covers'] else "\u2705\u274c"
    lines.append(f"{i}. {icon} {p['pick']} ({p['prob']*100:.1f}%) | {p['away']} @ {p['home']}")

with open('picks_out.json', 'w', encoding='utf-8') as f:
    json.dump(lines, f, ensure_ascii=False)
print(f"Done: {len(picks)} picks, {len(lines)} lines")
