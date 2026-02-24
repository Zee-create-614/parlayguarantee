import requests, json

headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get('https://api.draftkings.com/draftgroups/v1/draftgroups/142014/draftables', headers=headers, timeout=15)
raw = r.json()

# Dedupe players (appear once per roster slot)
seen = {}
for p in raw.get('draftables', []):
    pid = p.get('playerDkId')
    if pid in seen:
        continue
    
    sal = p.get('salary', 0)
    if not sal:
        continue
    
    # FPPG = attr id 219
    fppg = 0
    oprk = ''
    for attr in p.get('draftStatAttributes', []):
        if attr['id'] == 219:
            try: fppg = float(attr['value'])
            except: pass
        if attr['id'] == -2:
            oprk = attr.get('value', '')
    
    if fppg <= 0:
        continue
    
    status = p.get('status', 'None')
    if status in ('O', 'OUT'):
        continue
    
    seen[pid] = {
        'name': p['displayName'],
        'team': p['teamAbbreviation'],
        'pos': p.get('position', ''),
        'salary': sal,
        'fppg': fppg,
        'oprk': oprk,
        'value': round(fppg / (sal / 1000), 2),
        'status': status,
        'game': p.get('competition', {}).get('name', ''),
    }

players = sorted(seen.values(), key=lambda x: x['salary'], reverse=True)
print(f"=== FULL DK SLATE: {len(players)} players ===\n")

print(f"{'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'OPP':12s} {'FPPG':>6s} {'SAL':>8s} {'VAL':>5s} {'OPRK':>5s}")
print("-" * 80)
for p in players[:50]:
    print(f"{p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['game']:12s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['value']:>5.2f} {p['oprk']:>5s}")

# Build optimal lineup: PG, SG, SF, PF, C, G, F, UTIL
def eligible(pos, slot):
    if slot == 'PG': return 'PG' in pos
    if slot == 'SG': return 'SG' in pos
    if slot == 'SF': return 'SF' in pos
    if slot == 'PF': return 'PF' in pos
    if slot == 'C': return pos == 'C'
    if slot == 'G': return 'PG' in pos or 'SG' in pos
    if slot == 'F': return 'SF' in pos or 'PF' in pos
    if slot == 'UTIL': return True
    return False

slots = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']

def build_greedy(pool, cap=50000):
    used = set()
    lineup = {}
    remaining = cap
    for slot in slots:
        cands = [p for p in pool if eligible(p['pos'], slot) and p['name'] not in used]
        slots_left = len(slots) - len(lineup) - 1
        min_left = slots_left * 3500
        best = None
        for c in cands:
            if c['salary'] <= remaining - min_left:
                if best is None or c['fppg'] > best['fppg']:
                    best = c
        if best:
            lineup[slot] = best
            used.add(best['name'])
            remaining -= best['salary']
    return lineup

print("\n\n=== OPTIMAL LINEUP (Max Ceiling) ===\n")
lu = build_greedy(players)
tot_fp = tot_sal = 0
print(f"{'SLOT':6s} {'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s}")
print("-" * 62)
for slot in slots:
    if slot in lu:
        p = lu[slot]
        tot_fp += p['fppg']; tot_sal += p['salary']
        print(f"{slot:6s} {p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,}")
print(f"\n{'':6s} {'':7s} {'TOTAL':26s} {'':5s} {tot_fp:>6.1f} ${tot_sal:>7,}  (${50000-tot_sal:,} left)")

# Also build balanced lineup mixing ceiling + value
print("\n\n=== BALANCED LINEUP (Ceiling + Value mix) ===\n")
# Score = fppg * 0.6 + value * 4
for p in players:
    p['score'] = p['fppg'] * 0.6 + p['value'] * 4

bal_sorted = sorted(players, key=lambda x: x['score'], reverse=True)
lu2 = build_greedy(bal_sorted)
tot_fp = tot_sal = 0
print(f"{'SLOT':6s} {'POS':7s} {'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s}")
print("-" * 62)
for slot in slots:
    if slot in lu2:
        p = lu2[slot]
        tot_fp += p['fppg']; tot_sal += p['salary']
        print(f"{slot:6s} {p['pos']:7s} {p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,}")
print(f"\n{'':6s} {'':7s} {'TOTAL':26s} {'':5s} {tot_fp:>6.1f} ${tot_sal:>7,}  (${50000-tot_sal:,} left)")
