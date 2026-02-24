import json, os
os.chdir(os.path.join(os.path.dirname(__file__), 'picks_2026-02-21'))

for fname, label in [('nba_ml_spread.json','NBA'), ('ncaab_ml_spread.json','NCAAB')]:
    data = json.load(open(fname))
    picks = data['picks']
    picks.sort(key=lambda x: -x.get('ml_prob',0))
    print(f'\n=== {label} MONEYLINE + SPREAD ({len(picks)} games) ===')
    for p in picks:
        ml_prob = p.get('ml_prob',0)
        cover = p.get('cover_prob',0)
        upset = p.get('upset_composite',0)
        print(f"  {p['away']} @ {p['home']}")
        print(f"    ML: {p.get('ml_pick','?')} ({ml_prob*100:.0f}%) | Spread: {p.get('spread_pick','?')} {p.get('spread_line','')} ({cover*100:.0f}%) | Upset: {upset:.2f}")

for fname, label in [('nba_ou.json','NBA O/U'), ('ncaab_ou.json','NCAAB O/U')]:
    data = json.load(open(fname))
    picks = data['picks']
    picks.sort(key=lambda x: -x.get('ou_prob',0))
    print(f'\n=== {label} ({len(picks)} games) ===')
    for p in picks:
        ou_prob = p.get('ou_prob',0)
        print(f"  {p['away']} @ {p['home']} | {p.get('ou_pick','')} {p.get('total_line','')} ({ou_prob*100:.0f}%)")
