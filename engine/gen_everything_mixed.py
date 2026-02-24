#!/usr/bin/env python3
"""Generate mixed everything (spread+O/U) parlays, capped at 5 legs."""
import json, math, sys, time
from itertools import combinations
from pathlib import Path
import heapq

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SIM_DIR = Path(__file__).parent / 'sim'
with open(Path(__file__).parent / 'analyzed_games.json', encoding='utf-8') as f:
    ALL_GAMES = json.load(f)

def prob_to_american(prob):
    if prob <= 0 or prob >= 1: return 0
    return round(-prob / (1 - prob) * 100) if prob >= 0.5 else round((1 - prob) / prob * 100)

def make_spread_leg(g):
    return {'team': g['pick'], 'pick': f"{g['pick']} {g['spread_str']}", 'line': g.get('spread',0),
            'odds': prob_to_american(g.get('enhanced_prob', g.get('cover_prob',0.5))),
            'prob': g.get('enhanced_prob', g.get('cover_prob',0.5)),
            'sport': g['sport'], 'bet_type': 'spread', 'home': g['home'], 'away': g['away']}

def make_ou_leg(g):
    v3 = g.get('ou_model_v3', {})
    conf = v3.get('confidence', g.get('ou_prob', 0.5))
    return {'team': f"{g['home']} vs {g['away']}", 'pick': f"{v3['pick']} {g.get('total_line',0)}",
            'line': g.get('total_line',0), 'odds': prob_to_american(conf), 'prob': conf,
            'sport': g['sport'], 'bet_type': 'over_under', 'home': g['home'], 'away': g['away']}

ou_games = [g for g in ALL_GAMES if g.get('ou_model_v3', {}).get('pick', 'PASS') != 'PASS']
spread_legs = [make_spread_leg(g) for g in ALL_GAMES]
ou_legs = [make_ou_leg(g) for g in ou_games]
everything_legs = spread_legs + ou_legs
spread_count = len(spread_legs)
probs = [l['prob'] for l in everything_legs]
legs_clean = [{k:v for k,v in l.items() if k != 'prob'} for l in everything_legs]
n = len(everything_legs)

print(f'{n} total legs ({spread_count} spread + {len(ou_legs)} O/U)')

all_parlays = []
for size in range(2, 6):  # 2-5 legs (6-7 too expensive with 54 items)
    tc = math.comb(n, size)
    max_per = 10000
    need_sample = tc > max_per * 2

    if need_sample:
        print(f'  {size}-leg: {tc:,} combos -> sampling top {max_per:,}', flush=True)
        heap = []
        cnt = 0
        for combo in combinations(range(n), size):
            has_spread = any(i < spread_count for i in combo)
            has_ou = any(i >= spread_count for i in combo)
            if not (has_spread and has_ou): continue
            cp = 1.0
            for i in combo: cp *= probs[i]
            cnt += 1
            if len(heap) < max_per:
                heapq.heappush(heap, (cp, cnt, combo))
            elif cp > heap[0][0]:
                heapq.heapreplace(heap, (cp, cnt, combo))
        for cp, _, combo in heap:
            all_parlays.append((list(combo), round(cp,8), prob_to_american(cp), size))
        print(f'    -> {len(heap):,} kept (from {cnt:,} valid)', flush=True)
    else:
        cnt = 0
        for combo in combinations(range(n), size):
            has_spread = any(i < spread_count for i in combo)
            has_ou = any(i >= spread_count for i in combo)
            if not (has_spread and has_ou): continue
            cp = 1.0
            for i in combo: cp *= probs[i]
            all_parlays.append((list(combo), round(cp,8), prob_to_american(cp), size))
            cnt += 1
        print(f'  {size}-leg: {cnt:,} parlays', flush=True)

output = {'legs_index': legs_clean, 'parlays': [{'l':p[0],'p':p[1],'o':p[2],'n':p[3]} for p in all_parlays]}
path = SIM_DIR / 'feb22_everything_mixed.json'
with open(path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, separators=(',',':'))
print(f'\nEverything Mixed: {len(all_parlays):,} parlays -> {path.stat().st_size/1024/1024:.1f}MB')
