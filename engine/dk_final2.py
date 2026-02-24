import requests, json, time

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://api.draftkings.com/draftgroups/v1/draftgroups/142014/draftables', headers=headers, timeout=15)
raw = r.json()

seen = {}
for p in raw.get('draftables', []):
    pid = p.get('playerDkId')
    if pid in seen: continue
    sal = p.get('salary', 0)
    if not sal: continue
    fppg = 0
    for attr in p.get('draftStatAttributes', []):
        if attr['id'] == 219:
            try: fppg = float(attr['value'])
            except: pass
    if fppg <= 0: continue
    status = p.get('status', 'None')
    if status in ('O', 'OUT'): continue
    seen[pid] = {
        'name': p['displayName'], 'team': p['teamAbbreviation'],
        'pos': p.get('position', ''), 'salary': sal, 'fppg': fppg,
        'value': round(fppg / (sal / 1000), 2),
        'game': p.get('competition', {}).get('name', ''),
    }

players = list(seen.values())

def elig(pos, slot):
    if slot == 'PG': return 'PG' in pos
    if slot == 'SG': return 'SG' in pos
    if slot == 'SF': return 'SF' in pos
    if slot == 'PF': return 'PF' in pos
    if slot == 'C': return 'C' in pos
    if slot == 'G': return 'PG' in pos or 'SG' in pos
    if slot == 'F': return 'SF' in pos or 'PF' in pos
    if slot == 'UTIL': return True

slots = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']

def fill_remaining(locked, used_names, used_salary):
    """Fill remaining slots greedily by fppg"""
    remaining_slots = [s for s in slots if s not in locked]
    lineup = dict(locked)
    used = set(used_names)
    rem = 50000 - used_salary
    
    for slot in remaining_slots:
        cands = [p for p in players if elig(p['pos'], slot) and p['name'] not in used]
        slots_left = len(remaining_slots) - (len(lineup) - len(locked)) - 1
        if slots_left < 0: slots_left = 0
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
    
    if len(lineup) == 8:
        return lineup, sum(p['fppg'] for p in lineup.values())
    return None, 0

# Try all combos of 4 anchor players across PG, SG, PF, C (most impactful slots)
def top(slot, n=8):
    return sorted([p for p in players if elig(p['pos'], slot)], key=lambda x: x['fppg'], reverse=True)[:n]

best_lineup = None
best_fp = 0
t0 = time.time()

# 4-anchor approach: lock PG + SG + PF + C, fill SF/G/F/UTIL
for pg in top('PG', 8):
    for sg in top('SG', 8):
        if sg['name'] == pg['name']: continue
        for pf in top('PF', 8):
            if pf['name'] in (pg['name'], sg['name']): continue
            for c in top('C', 8):
                if c['name'] in (pg['name'], sg['name'], pf['name']): continue
                locked = {'PG': pg, 'SG': sg, 'PF': pf, 'C': c}
                used_names = {pg['name'], sg['name'], pf['name'], c['name']}
                used_salary = pg['salary'] + sg['salary'] + pf['salary'] + c['salary']
                if used_salary > 50000 - 4*3000: continue
                
                lu, fp = fill_remaining(locked, used_names, used_salary)
                if lu and fp > best_fp:
                    best_fp = fp
                    best_lineup = lu

print(f"Optimized in {time.time()-t0:.1f}s\n")

if best_lineup:
    print(f"=== OPTIMAL DK LINEUP ({best_fp:.1f} proj FP) ===\n")
    tot_sal = 0
    print(f"{'SLOT':6s} {'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'OPP':12s} {'FPPG':>6s} {'SAL':>8s}")
    print("-" * 75)
    for slot in slots:
        p = best_lineup[slot]
        tot_sal += p['salary']
        print(f"{slot:6s} {p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['game']:12s} {p['fppg']:>6.1f} ${p['salary']:>7,}")
    print(f"\n{'':40s} TOTAL: {best_fp:>6.1f} ${tot_sal:>7,}  (${50000-tot_sal:,} left)")

# Also show a "balanced" version with no player under $4K
print("\n\n=== BALANCED (no player under $4K) ===\n")
players_4k = [p for p in players if p['salary'] >= 4000]
best2 = None; best2_fp = 0
for pg in top('PG', 6):
    if pg['salary'] < 4000: continue
    for sg in top('SG', 6):
        if sg['salary'] < 4000 or sg['name'] == pg['name']: continue
        for pf in top('PF', 6):
            if pf['salary'] < 4000 or pf['name'] in (pg['name'], sg['name']): continue
            for c in [p for p in players_4k if elig(p['pos'], 'C')][:6]:
                if c['name'] in (pg['name'], sg['name'], pf['name']): continue
                locked = {'PG': pg, 'SG': sg, 'PF': pf, 'C': c}
                used_names = {pg['name'], sg['name'], pf['name'], c['name']}
                used_salary = pg['salary'] + sg['salary'] + pf['salary'] + c['salary']
                if used_salary > 50000 - 4*4000: continue
                
                # Fill from 4K+ pool
                remaining_slots = ['SF', 'G', 'F', 'UTIL']
                lineup = dict(locked)
                used = set(used_names)
                rem = 50000 - used_salary
                for slot in remaining_slots:
                    cands = [p for p in players_4k if elig(p['pos'], slot) and p['name'] not in used]
                    sl = len(remaining_slots) - (len(lineup) - 4) - 1
                    if sl < 0: sl = 0
                    ml = sl * 4000
                    best = None
                    for cc in cands:
                        if cc['salary'] <= rem - ml:
                            if best is None or cc['fppg'] > best['fppg']:
                                best = cc
                    if best:
                        lineup[slot] = best
                        used.add(best['name'])
                        rem -= best['salary']
                
                if len(lineup) == 8:
                    fp = sum(p['fppg'] for p in lineup.values())
                    if fp > best2_fp:
                        best2_fp = fp
                        best2 = dict(lineup)

if best2:
    tot_sal = 0
    print(f"{'SLOT':6s} {'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'OPP':12s} {'FPPG':>6s} {'SAL':>8s}")
    print("-" * 75)
    for slot in slots:
        p = best2[slot]
        tot_sal += p['salary']
        print(f"{slot:6s} {p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['game']:12s} {p['fppg']:>6.1f} ${p['salary']:>7,}")
    print(f"\n{'':40s} TOTAL: {best2_fp:>6.1f} ${tot_sal:>7,}  (${50000-tot_sal:,} left)")
