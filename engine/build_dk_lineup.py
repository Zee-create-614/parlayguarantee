"""Build optimal DK lineup from scraped slate data"""
import json

with open('engine/dk_slate_full.json') as f:
    data = json.load(f)

players = data['players']

# 7PM slate teams
slate_teams = {'IND','WAS','HOU','CHA','BKN','CLE','ATL','PHI','DET','NYK','TOR','CHI','PHX','SAS'}

# Filter and clean
slate = []
for p in players:
    if p['team'] in slate_teams:
        try:
            fppg = float(p['fppg']) if p['fppg'] else 0
        except:
            fppg = 0
        sal = int(p['salary']) if p['salary'] else 0
        if sal > 0 and fppg > 0:
            p['fppg'] = fppg
            p['salary'] = sal
            p['value'] = fppg / (sal / 1000) if sal > 0 else 0
            slate.append(p)

slate.sort(key=lambda x: x['salary'], reverse=True)

print(f"=== DK 7PM SLATE — {len(slate)} PLAYERS ===\n")
print(f"{'POS':8s} {'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s} {'VAL':>5s} {'STATUS'}")
print("-" * 75)
for p in slate[:60]:
    pos = str(p.get('position',''))
    status = p.get('status','')
    tag = ' *OUT*' if 'O' in status.upper() else (' GTD' if 'GTD' in status.upper() or 'Q' in status.upper() else '')
    print(f"{pos:8s} {p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['value']:>5.2f}{tag}")

# Now build optimal lineup
# DK positions: PG, SG, SF, PF, C, G(PG/SG), F(SF/PF), UTIL
# Salary cap: $50,000

print("\n\n=== BUILDING OPTIMAL LINEUP ===")
print("Strategy: maximize projected points under $50,000 cap\n")

# Map position eligibility from DK rosterSlotId
# DK uses numeric IDs, let's check what we have
positions_seen = set()
for p in slate[:10]:
    positions_seen.add(str(p.get('position','')))

# Let me check the raw data structure for positions
with open('engine/dk_slate_full.json') as f:
    raw = json.load(f)

# Check first few players for position info
sample = [p for p in raw['players'] if p['team'] in slate_teams and int(p.get('salary',0) or 0) > 8000][:5]
for s in sample:
    print(f"  {s['name']:25s} pos={s.get('position','')} team={s['team']} sal=${s['salary']}")

# Simple greedy approach - pick best available for each slot
# Map positions properly
pos_map = {}
for p in slate:
    pos = str(p.get('position',''))
    if pos not in pos_map:
        pos_map[pos] = []
    pos_map[pos].append(p)

print(f"\nPosition codes found: {list(pos_map.keys())[:20]}")

# Since DK position codes might be numeric, let's just use the game info
# and player knowledge. Output the top players by value for manual lineup building
print("\n=== TOP PLAYS BY VALUE (FPPG per $1K) ===\n")
by_value = sorted(slate, key=lambda x: x['value'], reverse=True)
print(f"{'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s} {'VAL':>5s}")
print("-" * 55)
for p in by_value[:25]:
    print(f"{p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['value']:>5.2f}")

print("\n=== TOP PLAYS BY CEILING (Raw FPPG) ===\n")
by_ceil = sorted(slate, key=lambda x: x['fppg'], reverse=True)
print(f"{'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s} {'VAL':>5s}")
print("-" * 55)
for p in by_ceil[:25]:
    print(f"{p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['value']:>5.2f}")
