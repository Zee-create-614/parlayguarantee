import requests, json, time

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://api.draftkings.com/draftgroups/v1/draftgroups/142014/draftables', headers=headers, timeout=15)
raw = r.json()

slate_teams = {'IND','WAS','HOU','CHA','BKN','CLE','ATL','PHI','DET','NYK','TOR','CHI','PHX','SAS'}
EXCLUDE = {'Trae Young', 'Josh Giddey', 'Tre Jones'}

seen = {}
for p in raw.get('draftables', []):
    pid = p.get('playerDkId')
    if pid in seen: continue
    team = p.get('teamAbbreviation', '')
    if team not in slate_teams: continue
    sal = p.get('salary', 0)
    if not sal: continue
    fppg = 0
    for attr in p.get('draftStatAttributes', []):
        if attr['id'] == 219:
            try: fppg = float(attr['value'])
            except: pass
    if fppg <= 0: continue
    name = p['displayName']
    status = p.get('status', 'None')
    if status in ('O', 'OUT') or name in EXCLUDE: continue
    seen[pid] = {
        'name': name, 'team': team, 'pos': p.get('position', ''),
        'salary': sal, 'fppg': fppg, 'value': round(fppg / (sal / 1000), 2),
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

slots_order = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']

def top(slot, n=10):
    return sorted([p for p in players if elig(p['pos'], slot)], key=lambda x: x['fppg'], reverse=True)[:n]

def build(min_sal=4500):
    pool = [p for p in players if p['salary'] >= min_sal]
    def fill(locked):
        rem_slots = [s for s in slots_order if s not in locked]
        lineup = dict(locked)
        used = {p['name'] for p in locked.values()}
        rem = 50000 - sum(p['salary'] for p in locked.values())
        for slot in rem_slots:
            cands = [p for p in pool if elig(p['pos'], slot) and p['name'] not in used]
            sl = len(rem_slots) - (len(lineup) - len(locked)) - 1
            if sl < 0: sl = 0
            best = None
            for c in cands:
                if c['salary'] <= rem - sl * min_sal:
                    if best is None or c['fppg'] > best['fppg']:
                        best = c
            if best:
                lineup[slot] = best; used.add(best['name']); rem -= best['salary']
        if len(lineup) == 8:
            return lineup, sum(p['fppg'] for p in lineup.values())
        return None, 0

    pg_c = [p for p in top('PG', 10) if p['salary'] >= min_sal]
    sg_c = [p for p in top('SG', 10) if p['salary'] >= min_sal]
    sf_c = [p for p in top('SF', 8) if p['salary'] >= min_sal]
    pf_c = [p for p in top('PF', 8) if p['salary'] >= min_sal]
    c_c = [p for p in top('C', 8) if p['salary'] >= min_sal]
    best_lu = None; best_fp = 0
    for pg in pg_c:
        for sg in sg_c:
            if sg['name'] == pg['name']: continue
            for sf in sf_c:
                if sf['name'] in (pg['name'], sg['name']): continue
                for pf in pf_c:
                    if pf['name'] in (pg['name'], sg['name'], sf['name']): continue
                    for c in c_c:
                        if c['name'] in (pg['name'], sg['name'], sf['name'], pf['name']): continue
                        lsal = pg['salary'] + sg['salary'] + sf['salary'] + pf['salary'] + c['salary']
                        if lsal > 50000 - 3*min_sal: continue
                        locked = {'PG': pg, 'SG': sg, 'SF': sf, 'PF': pf, 'C': c}
                        lu, fp = fill(locked)
                        if lu and fp > best_fp:
                            best_fp = fp; best_lu = lu
    return best_lu, best_fp

t0 = time.time()
lu, fp = build(4500)
print(f"Done in {time.time()-t0:.1f}s\n")
print(f"=== BEST LINEUP — NO Q/OUT ({fp:.1f} proj FP) ===\n")
tot = 0
print(f"{'SLOT':6s} {'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'OPP':12s} {'FPPG':>6s} {'SAL':>8s}")
print("-" * 75)
for slot in slots_order:
    p = lu[slot]
    tot += p['salary']
    print(f"{slot:6s} {p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['game']:12s} {p['fppg']:>6.1f} ${p['salary']:>7,}")
print(f"\n{'':40s} TOTAL: {fp:>6.1f} ${tot:>7,}  (${50000-tot:,} left)")
