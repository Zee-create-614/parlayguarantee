import json, os

base = 'picks_2026-02-21'
all_picks = []

for fname, sport in [('nba_ml_spread.json','NBA'),('ncaab_ml_spread.json','NCAAB')]:
    with open(os.path.join(base, fname), encoding='utf-8') as f:
        data = json.load(f)
    for p in data['picks']:
        all_picks.append({
            'sport': sport, 'away': p['away'], 'home': p['home'],
            'pick': p['ml_pick'], 'prob': p['ml_prob'], 'books': p['books_used']
        })

# Filter: DK only, exclude Texas A&M Aggies
dk = [p for p in all_picks if 'draftkings' in p['books'] 
      and 'Texas A&M Aggies' not in p['away'] and 'Texas A&M Aggies' not in p['home']]
dk.sort(key=lambda x: x['prob'], reverse=True)

print(f"{len(dk)} DK picks available")

# Build 7 UNIQUE parlays: 1x3, 4x5, 2x14 = 3+20+28 = 51 unique legs needed
# Take top 51 picks, assign them uniquely
used = set()
parlays = []

def take_next(n):
    legs = []
    for p in dk:
        key = p['pick'] + p['away'] + p['home']
        if key not in used:
            legs.append(p)
            used.add(key)
            if len(legs) == n:
                break
    return legs

# 3-leg (top 3)
p3 = take_next(3)
parlays.append(('3-LEG', p3))

# 4x 5-leg (next 20)
for i in range(4):
    p5 = take_next(5)
    parlays.append((f'5-LEG #{i+1}', p5))

# 2x 14-leg (next 28)
for i in range(2):
    p14 = take_next(14)
    parlays.append((f'14-LEG #{i+1}', p14))

for name, legs in parlays:
    combined = 1.0
    for l in legs:
        combined *= l['prob']
    print(f"\n--- {name} ({combined*100:.1f}% combined) ---")
    for i, p in enumerate(legs, 1):
        print(f"  {i}. {p['pick']} ({p['prob']*100:.1f}%) | {p['away']} @ {p['home']} [{p['sport']}]")
