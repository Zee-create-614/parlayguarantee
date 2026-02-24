import requests, json, time

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://api.draftkings.com/draftgroups/v1/draftgroups/142014/draftables', headers=headers, timeout=15)
raw = r.json()

seen = {}
for p in raw.get('draftables', []):
    pid = p.get('playerDkId')
    if pid in seen:
        continue
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
print(f"{len(players)} players loaded")

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

def top(slot, n=10):
    return sorted([p for p in players if elig(p['pos'], slot)], key=lambda x: x['fppg'], reverse=True)[:n]

best_lineup = None
best_fp = 0
t0 = time.time()

pg_c = top('PG', 8)
sg_c = top('SG', 8)
sf_c = top('SF', 8)

for pg in pg_c:
    for sg in sg_c:
        if sg['name'] == pg['name']: continue
        for sf in sf_c:
            if sf['name'] in (pg['name'], sg['name']): continue
            used = {pg['name'], sg['name'], sf['name']}
            spent = pg['salary'] + sg['salary'] + sf['salary']
            fp = pg['fppg'] + sg['fppg'] + sf['fppg']
            lineup = {'PG': pg, 'SG': sg, 'SF': sf}
            rem = 50000 - spent
            
            for slot in ['PF', 'C', 'G', 'F', 'UTIL']:
                cands = [p for p in players if elig(p['pos'], slot) and p['name'] not in used]
                slots_left = 5 - (len(lineup) - 3) - 1
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
                    fp += best['fppg']
            
            if len(lineup) == 8 and fp > best_fp:
                best_fp = fp
                best_lineup = dict(lineup)

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
