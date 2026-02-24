import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('picks_output.json', encoding='utf-8') as f:
    data = json.load(f)

# Collect all unique games
all_games = {}
for k, v in data.items():
    if k.startswith('_'): continue
    for pick in v.get('picks', []):
        for g in pick.get('games', []):
            key = g['away'] + ' @ ' + g['home']
            if key not in all_games or g['win_prob'] > all_games[key]['win_prob']:
                all_games[key] = g

tonight = {k:v for k,v in all_games.items() if v['game_date'] == '2026-02-19'}
tomorrow = {k:v for k,v in all_games.items() if v['game_date'] == '2026-02-20'}

print('=== TONIGHT (Feb 19) ===')
for matchup, g in sorted(tonight.items(), key=lambda x: -x[1]['win_prob']):
    print(f"  {matchup} -> {g['pick']} ({g['win_prob']:.0%})")

print(f'\n=== TOMORROW (Feb 20) ===')
for matchup, g in sorted(tomorrow.items(), key=lambda x: -x[1]['win_prob']):
    print(f"  {matchup} -> {g['pick']} ({g['win_prob']:.0%})")

# Collect all parlays by leg count, pick best by combined_prob
best_by_legs = {}
for k, v in data.items():
    if k.startswith('_'): continue
    for pick in v.get('picks', []):
        legs = pick.get('legs', len(pick.get('games', [])))
        prob = pick.get('combined_prob', 0)
        if legs not in best_by_legs or prob > best_by_legs[legs]['combined_prob']:
            best_by_legs[legs] = pick

print('\n=== BEST PARLAYS BY LEG COUNT ===')
for leg_count in [2, 3, 5, 7]:
    if leg_count in best_by_legs:
        pick = best_by_legs[leg_count]
        prob = pick.get('combined_prob', 0)
        payout = pick.get('implied_payout', '?')
        print(f"\n{leg_count}-LEG PARLAY ({prob:.1%} combined prob, {payout} payout)")
        for g in pick.get('games', []):
            print(f"  {g['away']} @ {g['home']} -> {g['pick']} ({g['win_prob']:.0%})")
    else:
        print(f"\n{leg_count}-LEG: Not generated")
