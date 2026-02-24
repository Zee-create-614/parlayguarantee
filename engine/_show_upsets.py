import json
d = json.load(open('picks_2026-02-21/nba_ml_spread.json'))
for p in d['picks']:
    uc = p.get('upset_composite', 0)
    flip = uc >= 0.40
    print(f"{'*** FLIP ***' if flip else '            '} {p['away']} @ {p['home']} | fav: {p['ml_pick']} ({p['ml_prob']:.0%}) | upset: {uc:.0%}")
