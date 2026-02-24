import json, os, itertools

base = 'picks_2026-02-21'
all_picks = []

for fname, sport in [('nba_ml_spread.json','NBA'),('ncaab_ml_spread.json','NCAAB')]:
    with open(os.path.join(base, fname), encoding='utf-8') as f:
        data = json.load(f)
    for p in data['picks']:
        all_picks.append({
            'sport': sport,
            'away': p['away'],
            'home': p['home'],
            'pick': p['ml_pick'],
            'prob': p['ml_prob'],
            'spread_pick': p['spread_pick'],
            'spread_line': p['spread_line'],
            'spread_side': p['spread_side'],
            'books': p['books_used']
        })

# Filter: DK only, exclude Texas A&M
dk_picks = []
for p in all_picks:
    if 'draftkings' not in p['books']:
        continue
    if 'Texas A&M' in p['away'] or 'Texas A&M' in p['home']:
        continue
    # Exclude Texas A&M-CC too? No, Josh said Texas A&M (the SEC team vs Oklahoma)
    if p['away'] == 'Texas A&M Aggies' or p['home'] == 'Texas A&M Aggies':
        continue
    dk_picks.append(p)

# Sort by confidence
dk_picks.sort(key=lambda x: x['prob'], reverse=True)

print(f"DK picks available (excl Texas A&M): {len(dk_picks)}")
print(f"Top 20 by confidence:")
for i, p in enumerate(dk_picks[:20], 1):
    print(f"  {i}. {p['pick']} ({p['prob']*100:.1f}%) | {p['away']} @ {p['home']} [{p['sport']}]")

# Build parlays - pick unique games, highest confidence
# For spread picks, show the spread line
def format_leg(p):
    pick = p['spread_pick']
    if p['spread_side'] == 'home':
        line = p['spread_line']
    else:
        line = p['spread_line']
    # Determine if pick is home or away
    if pick == p['home']:
        spread_val = p['spread_line']
    else:
        spread_val = -p['spread_line'] if p['spread_side'] == 'home' else p['spread_line']
    return f"{pick} ({p['prob']*100:.1f}%) [{p['sport']}]"

def calc_parlay_prob(legs):
    prob = 1.0
    for l in legs:
        prob *= l['prob']
    return prob

# Best 3-leg: top 3
parlay_3 = dk_picks[:3]

# Best 5-legs: need 4 unique sets
# Strategy: top picks, varying to get 4 different parlays
used_in_5 = set()
parlays_5 = []

# First 5-leg: picks 1-5
parlays_5.append(dk_picks[:5])

# Second: picks 1-3 + 6-7 (swap bottom 2)
parlays_5.append(dk_picks[:3] + [dk_picks[5], dk_picks[6]])

# Third: picks 1-2 + 4 + 7-8
parlays_5.append([dk_picks[0], dk_picks[1], dk_picks[3], dk_picks[7], dk_picks[8]])

# Fourth: picks 1 + 5-8 + 9
parlays_5.append([dk_picks[0], dk_picks[4], dk_picks[9], dk_picks[10], dk_picks[11]])

# 14-leg parlays: top 14 and next best 14
parlay_14_a = dk_picks[:14]
parlay_14_b = dk_picks[:7] + dk_picks[14:21]

print("\n" + "="*60)
print("JOSH'S PARLAYS - DraftKings Only")
print("="*60)

print(f"\n--- 3-LEG PARLAY (Combined: {calc_parlay_prob(parlay_3)*100:.1f}%) ---")
for i, p in enumerate(parlay_3, 1):
    print(f"  {i}. {format_leg(p)} | {p['away']} @ {p['home']}")

for j, par in enumerate(parlays_5, 1):
    print(f"\n--- 5-LEG PARLAY #{j} (Combined: {calc_parlay_prob(par)*100:.1f}%) ---")
    for i, p in enumerate(par, 1):
        print(f"  {i}. {format_leg(p)} | {p['away']} @ {p['home']}")

print(f"\n--- 14-LEG PARLAY #1 (Combined: {calc_parlay_prob(parlay_14_a)*100:.2f}%) ---")
for i, p in enumerate(parlay_14_a, 1):
    print(f"  {i}. {format_leg(p)} | {p['away']} @ {p['home']}")

print(f"\n--- 14-LEG PARLAY #2 (Combined: {calc_parlay_prob(parlay_14_b)*100:.2f}%) ---")
for i, p in enumerate(parlay_14_b, 1):
    print(f"  {i}. {format_leg(p)} | {p['away']} @ {p['home']}")
