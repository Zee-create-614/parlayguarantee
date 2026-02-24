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
        
        spread_line = p.get('spread_line', 0)
        spread_pick = p.get('spread_pick', p['ml_pick'])
        cover_prob = p.get('cover_prob', p['ml_prob'])
        
        if uc >= UPSET_THRESHOLD:
            # FLIP to underdog side of spread
            dog = p['away'] if p['ml_side'] == 'home' else p['home']
            # Dog gets the opposite spread
            dog_spread = -spread_line if spread_pick != dog else spread_line
            all_picks.append({
                'sport': sport, 'away': p['away'], 'home': p['home'],
                'pick': dog, 'spread': abs(dog_spread), 'prob': uc,
                'books': p['books_used'], 'is_upset': True,
                'spread_display': f"+{abs(dog_spread)}"
            })
        else:
            all_picks.append({
                'sport': sport, 'away': p['away'], 'home': p['home'],
                'pick': spread_pick, 'spread': spread_line, 'prob': cover_prob,
                'books': p['books_used'], 'is_upset': False,
                'spread_display': f"{spread_line}"
            })

all_picks.sort(key=lambda x: x['prob'], reverse=True)

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

p3 = take_next(3, all_picks)
parlays.append(('3-LEG', p3))

for i in range(4):
    upset_legs = take_next(1, [p for p in all_picks if p['is_upset'] and p['pick']+p['away']+p['home'] not in used])
    remaining = take_next(5 - len(upset_legs), [p for p in all_picks if p['pick']+p['away']+p['home'] not in used])
    parlays.append((f'5-LEG #{i+1}', upset_legs + remaining))

for i in range(2):
    upset_legs = take_next(3, [p for p in all_picks if p['is_upset'] and p['pick']+p['away']+p['home'] not in used])
    remaining = take_next(14 - len(upset_legs), [p for p in all_picks if p['pick']+p['away']+p['home'] not in used])
    parlays.append((f'14-LEG #{i+1}', upset_legs + remaining))

# Output formatted
for name, legs in parlays:
    upset_ct = sum(1 for l in legs if l['is_upset'])
    print(f"\n{name}")
    for j, p in enumerate(legs, 1):
        upset_tag = ' UPSET' if p['is_upset'] else ''
        print(f"  {p['pick']} ({p['spread_display']}){upset_tag} | {p['away']} @ {p['home']} [{p['sport']}]")
