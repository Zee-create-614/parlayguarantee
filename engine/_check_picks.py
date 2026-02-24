import json
d = json.load(open('picks_2026-02-21/nba_ml_spread.json'))
for p in d['picks']:
    same = p['ml_pick'] == p['spread_pick']
    print(p['ml_pick'], '|', f"ML:{p['ml_prob']:.3f}", '| spread_pick:', p['spread_pick'], '| same:', same, '| line:', p['spread_line'])
