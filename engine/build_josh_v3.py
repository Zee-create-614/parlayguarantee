import json, os

base = 'picks_2026-02-21'
nba_picks = []
ncaab_picks = []

for fname, sport in [('nba_ml_spread.json','NBA'),('ncaab_ml_spread.json','NCAAB')]:
    with open(os.path.join(base, fname), encoding='utf-8') as f:
        data = json.load(f)
    for p in data['picks']:
        entry = {
            'sport': sport, 'away': p['away'], 'home': p['home'],
            'pick': p['ml_pick'], 'prob': p['ml_prob'], 'books': p['books_used']
        }
        if 'draftkings' not in p['books_used']:
            continue
        if 'Texas A&M Aggies' in p['away'] or 'Texas A&M Aggies' in p['home']:
            continue
        if sport == 'NBA':
            nba_picks.append(entry)
        else:
            ncaab_picks.append(entry)

nba_picks.sort(key=lambda x: x['prob'], reverse=True)
ncaab_picks.sort(key=lambda x: x['prob'], reverse=True)

print(f"{len(nba_picks)} NBA picks, {len(ncaab_picks)} NCAAB picks on DK")

# Strategy: distribute NBA picks across all 7 parlays
# Parlay sizes: 3, 5, 5, 5, 5, 14, 14 = 51 total legs
# 6 NBA picks → at least 1 per parlay (assign best NBA to biggest parlays first for variety)
# Assign NBA: 14-leggers get 1 each, 5-leggers get 1 each (4), 3-legger gets 0 if short... 
# Actually 6 NBA for 7 parlays. Give 3-legger 1 NBA, each 5-legger 1 NBA, one 14-legger 1 NBA

parlay_specs = [
    ('3-LEG', 3, 1),        # 1 NBA + 2 NCAAB
    ('5-LEG #1', 5, 1),     # 1 NBA + 4 NCAAB
    ('5-LEG #2', 5, 1),     # 1 NBA + 4 NCAAB
    ('5-LEG #3', 5, 1),     # 1 NBA + 4 NCAAB
    ('5-LEG #4', 5, 1),     # 1 NBA + 4 NCAAB
    ('14-LEG #1', 14, 1),   # 1 NBA + 13 NCAAB
    ('14-LEG #2', 14, 0),   # 0 NBA (ran out) + 14 NCAAB
]

nba_idx = 0
ncaab_idx = 0
parlays = []

for name, size, nba_count in parlay_specs:
    legs = []
    # Add NBA legs
    for _ in range(nba_count):
        if nba_idx < len(nba_picks):
            legs.append(nba_picks[nba_idx])
            nba_idx += 1
    # Fill rest with NCAAB
    ncaab_needed = size - len(legs)
    for _ in range(ncaab_needed):
        if ncaab_idx < len(ncaab_picks):
            legs.append(ncaab_picks[ncaab_idx])
            ncaab_idx += 1
    parlays.append((name, legs))

for name, legs in parlays:
    combined = 1.0
    for l in legs:
        combined *= l['prob']
    nba_count = sum(1 for l in legs if l['sport'] == 'NBA')
    ncaab_count = sum(1 for l in legs if l['sport'] == 'NCAAB')
    print(f"\n{'='*50}")
    print(f"{name} ({combined*100:.1f}% combined) - {nba_count} NBA, {ncaab_count} NCAAB")
    print(f"{'='*50}")
    for i, p in enumerate(legs, 1):
        tag = '[NBA]' if p['sport'] == 'NBA' else '[NCAAB]'
        print(f"  {i}. {tag} {p['pick']} ({p['prob']*100:.1f}%) | {p['away']} @ {p['home']}")
