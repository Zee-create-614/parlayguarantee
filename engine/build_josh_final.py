import json, os

base = 'picks_2026-02-21'
all_picks = []

for fname, sport in [('nba_ml_spread.json','NBA'),('ncaab_ml_spread.json','NCAAB')]:
    with open(os.path.join(base, fname), encoding='utf-8') as f:
        data = json.load(f)
    for p in data['picks']:
        if 'draftkings' not in p['books_used']:
            continue
        if 'Texas A&M Aggies' in p['away'] or 'Texas A&M Aggies' in p['home']:
            continue
        
        uc = p.get('upset_composite', 0)
        UPSET_THRESHOLD = 0.40
        
        if uc >= UPSET_THRESHOLD:
            # FLIP to underdog
            dog = p['away'] if p['ml_side'] == 'home' else p['home']
            # Use upset_composite as the "edge confidence"
            all_picks.append({
                'sport': sport, 'away': p['away'], 'home': p['home'],
                'pick': dog, 'prob': uc, 'books': p['books_used'],
                'is_upset': True, 'edge': uc - (1 - p['ml_prob'])
            })
        else:
            all_picks.append({
                'sport': sport, 'away': p['away'], 'home': p['home'],
                'pick': p['ml_pick'], 'prob': p['ml_prob'], 'books': p['books_used'],
                'is_upset': False, 'edge': 0
            })

all_picks.sort(key=lambda x: x['prob'], reverse=True)

upsets = [p for p in all_picks if p['is_upset']]
favs = [p for p in all_picks if not p['is_upset']]
print(f"{len(all_picks)} total picks ({len(upsets)} upset flips, {len(favs)} favorites)")

# Build parlays: 1x3, 4x5, 2x14
used = set()

def take_next(n, pool):
    legs = []
    for p in pool:
        key = p['pick'] + p['away'] + p['home']
        if key not in used:
            legs.append(p)
            used.add(key)
            if len(legs) == n:
                break
    return legs

parlays = []

# 3-leg: top 3 overall
p3 = take_next(3, all_picks)
parlays.append(('3-LEG', p3))

# 5-leggers: each one gets mix of favorites + at least 1 upset
for i in range(4):
    # grab 1 upset first, then fill with best available
    upset_legs = take_next(1, [p for p in all_picks if p['is_upset'] and p['pick']+p['away']+p['home'] not in used])
    remaining = take_next(5 - len(upset_legs), [p for p in all_picks if p['pick']+p['away']+p['home'] not in used])
    parlays.append((f'5-LEG #{i+1}', upset_legs + remaining))

# 14-leggers: mix upsets throughout
for i in range(2):
    # grab 3-4 upsets, fill rest with favorites
    upset_legs = take_next(3, [p for p in all_picks if p['is_upset'] and p['pick']+p['away']+p['home'] not in used])
    remaining = take_next(14 - len(upset_legs), [p for p in all_picks if p['pick']+p['away']+p['home'] not in used])
    parlays.append((f'14-LEG #{i+1}', upset_legs + remaining))

for name, legs in parlays:
    combined = 1.0
    for l in legs:
        combined *= l['prob']
    nba_ct = sum(1 for l in legs if l['sport'] == 'NBA')
    ncaab_ct = sum(1 for l in legs if l['sport'] == 'NCAAB')
    upset_ct = sum(1 for l in legs if l['is_upset'])
    print(f"\n{'='*55}")
    print(f"{name} ({combined*100:.1f}%) - {nba_ct} NBA, {ncaab_ct} NCAAB, {upset_ct} UPSETS")
    print(f"{'='*55}")
    for j, p in enumerate(legs, 1):
        tag = '[NBA]' if p['sport'] == 'NBA' else '[CBB]'
        upset_tag = ' ** UPSET **' if p['is_upset'] else ''
        print(f"  {j}. {tag} {p['pick']} ({p['prob']:.0%}) | {p['away']} @ {p['home']}{upset_tag}")
