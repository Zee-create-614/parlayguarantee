import json

with open('engine/dk_slate_full.json') as f:
    players = json.load(f)

def eligible(pos, slot):
    if slot == 'PG': return 'PG' in pos
    if slot == 'SG': return 'SG' in pos
    if slot == 'SF': return 'SF' in pos
    if slot == 'PF': return 'PF' in pos
    if slot == 'C': return pos == 'C' or (pos == 'PF/C')
    if slot == 'G': return 'PG' in pos or 'SG' in pos
    if slot == 'F': return 'SF' in pos or 'PF' in pos
    if slot == 'UTIL': return True
    return False

slots = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']

# Better approach: try multiple lineup combos by varying stud/value allocation
# Key insight: spend big on 4-5 spots, find mid-range value for the rest

from itertools import product

# Tier players
studs = [p for p in players if p['salary'] >= 8000]  # $8K+
mid = [p for p in players if 5500 <= p['salary'] < 8000]
value = [p for p in players if 3000 <= p['salary'] < 5500]

print(f"Studs: {len(studs)}, Mid: {len(mid)}, Value: {len(value)}")

# Brute force best lineup with constraint solver
# Since 8 slots with 211 players is too many combos, use smart greedy with backtracking

best_lineup = None
best_fp = 0

# Try different stud combinations for PG/SG/SF slots, then fill rest optimally
import time
start = time.time()

# Get top candidates per slot
def top_for_slot(slot, n=15):
    cands = [p for p in players if eligible(p['pos'], slot)]
    return sorted(cands, key=lambda x: x['fppg'], reverse=True)[:n]

# Try combos of PG + SG + SF (the 3 named position slots that have the most studs)
pg_cands = top_for_slot('PG', 8)
sg_cands = top_for_slot('SG', 8)
sf_cands = top_for_slot('SF', 8)

for pg in pg_cands:
    for sg in sg_cands:
        if sg['name'] == pg['name']:
            continue
        for sf in sf_cands:
            if sf['name'] in (pg['name'], sg['name']):
                continue
            
            used = {pg['name'], sg['name'], sf['name']}
            spent = pg['salary'] + sg['salary'] + sf['salary']
            fp = pg['fppg'] + sg['fppg'] + sf['fppg']
            remaining_cap = 50000 - spent
            remaining_slots = ['PF', 'C', 'G', 'F', 'UTIL']
            
            # Greedily fill remaining 5 slots
            lineup = {'PG': pg, 'SG': sg, 'SF': sf}
            rem = remaining_cap
            
            for slot in remaining_slots:
                cands = [p for p in players if eligible(p['pos'], slot) and p['name'] not in used]
                slots_left = len(remaining_slots) - len([s for s in remaining_slots if s in lineup])  - 1
                min_left = slots_left * 3000
                
                best = None
                for c in cands:
                    if c['salary'] <= rem - min_left:
                        if best is None or c['fppg'] > best['fppg']:
                            best = c
                if best:
                    lineup[slot] = best
                    used.add(best['name'])
                    rem -= best['salary']
                    fp += best['fppg']
            
            if len(lineup) == 8 and fp > best_fp:
                best_fp = fp
                best_lineup = dict(lineup)

elapsed = time.time() - start
print(f"Optimized in {elapsed:.1f}s\n")

if best_lineup:
    print(f"=== BEST LINEUP ({best_fp:.1f} projected FP) ===\n")
    tot_sal = 0
    all_slots = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']
    print(f"{'SLOT':6s} {'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'OPP':12s} {'FPPG':>6s} {'SALARY':>8s}")
    print("-" * 75)
    for slot in all_slots:
        p = best_lineup[slot]
        tot_sal += p['salary']
        print(f"{slot:6s} {p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['game']:12s} {p['fppg']:>6.1f} ${p['salary']:>7,}")
    print(f"\n{'':40s} TOTAL: {best_fp:>6.1f} ${tot_sal:>7,}  (${50000-tot_sal:,} left)")
