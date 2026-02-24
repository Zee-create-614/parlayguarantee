"""Scrape DK NBA slate + build optimal 7PM lineup"""
import requests, json
from itertools import combinations

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Get contests to find draft group
r = requests.get("https://www.draftkings.com/lobby/getcontests?sport=NBA", headers=headers, timeout=15)
contests = r.json()
dg = contests['Contests'][0]['dg']
print(f"Draft group: {dg}")

# Get all draftables
r2 = requests.get(f"https://api.draftkings.com/draftgroups/v1/draftgroups/{dg}/draftables", headers=headers, timeout=15)
raw = r2.json()

# 7PM slate teams
slate_teams = {'IND','WAS','HOU','CHA','BKN','CLE','ATL','PHI','DET','NYK','TOR','CHI','PHX','SAS'}

players = []
for p in raw.get('draftables', []):
    team = p.get('teamAbbreviation','')
    if team not in slate_teams:
        continue
    sal = p.get('salary', 0)
    if not sal or sal == 0:
        continue
    
    # Get FPPG
    fppg = 0
    for attr in p.get('draftStatAttributes', []):
        if attr.get('id') == 90:
            try:
                fppg = float(attr.get('value', 0))
            except:
                fppg = 0
    
    if fppg <= 0:
        continue
    
    # Get position from rosterSlotId  
    pos_raw = p.get('rosterSlotId', 0)
    
    # DK position names
    roster_positions = []
    for rs in p.get('rosterSlots', []):
        roster_positions.append(rs.get('name', ''))
    
    # Also check displayPosition or position
    display_pos = p.get('position', {})
    if isinstance(display_pos, dict):
        display_pos = display_pos.get('name', '')
    
    status = p.get('status', '')
    if status and ('O' == status or 'OUT' in str(status).upper()):
        continue  # skip OUT players
    
    players.append({
        'name': p.get('displayName', ''),
        'team': team,
        'salary': sal,
        'fppg': fppg,
        'positions': roster_positions,
        'pos_display': display_pos,
        'value': fppg / (sal / 1000),
        'status': status,
    })

players.sort(key=lambda x: x['salary'], reverse=True)
print(f"\n{len(players)} eligible players on 7PM slate\n")

# Print top 40
print(f"{'POS':12s} {'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s} {'VAL':>5s}")
print("-" * 68)
for p in players[:40]:
    pos = '/'.join(p['positions'][:2]) if p['positions'] else str(p['pos_display'])
    print(f"{pos:12s} {p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['value']:>5.2f}")

# Save for reference
with open('engine/dk_slate_full.json', 'w') as f:
    json.dump(players, f, indent=2)

# === BUILD OPTIMAL LINEUP ===
# DK Classic: PG, SG, SF, PF, C, G, F, UTIL = 8 players, $50,000 cap
# G = PG or SG, F = SF or PF, UTIL = any

print("\n\n=== BUILDING OPTIMAL LINEUP ===\n")

# Map each player to eligible DK slots
def get_eligible_slots(p):
    slots = set()
    pos = '/'.join(p['positions']) if p['positions'] else str(p['pos_display'])
    pos = pos.upper()
    if 'PG' in pos:
        slots.update(['PG', 'G', 'UTIL'])
    if 'SG' in pos:
        slots.update(['SG', 'G', 'UTIL'])
    if 'SF' in pos:
        slots.update(['SF', 'F', 'UTIL'])
    if 'PF' in pos:
        slots.update(['PF', 'F', 'UTIL'])
    if 'C' in pos:
        slots.update(['C', 'UTIL'])
    if not slots:
        slots.add('UTIL')
    return slots

for p in players:
    p['slots'] = get_eligible_slots(p)

# Greedy optimizer: fill each slot with best available
# Order slots from most restrictive to least
slot_order = ['C', 'PG', 'SG', 'SF', 'PF', 'G', 'F', 'UTIL']

def build_lineup_greedy(player_pool, salary_cap=50000):
    used = set()
    lineup = {}
    remaining = salary_cap
    
    for slot in slot_order:
        candidates = [p for p in player_pool if slot in p['slots'] and p['name'] not in used]
        # For each candidate, check if remaining budget allows filling other slots
        slots_left = len([s for s in slot_order if s not in lineup]) - 1
        min_remaining_cost = slots_left * 3500  # minimum salary per remaining slot
        
        best = None
        for c in candidates:
            if c['salary'] <= remaining - min_remaining_cost:
                if best is None or c['fppg'] > best['fppg']:
                    best = c
        
        if best:
            lineup[slot] = best
            used.add(best['name'])
            remaining -= best['salary']
    
    return lineup, remaining

lineup, remaining = build_lineup_greedy(players)

total_fppg = 0
total_salary = 0
print(f"{'SLOT':6s} {'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s}")
print("-" * 55)
for slot in slot_order:
    if slot in lineup:
        p = lineup[slot]
        total_fppg += p['fppg']
        total_salary += p['salary']
        print(f"{slot:6s} {p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,}")

print(f"\n{'TOTAL':6s} {'':26s} {'':5s} {total_fppg:>6.1f} ${total_salary:>7,}")
print(f"Remaining salary: ${50000 - total_salary:,}")

# Also build a value lineup
print("\n\n=== VALUE LINEUP (maximize value per $) ===\n")

def build_value_lineup(player_pool, salary_cap=50000):
    used = set()
    lineup = {}
    remaining = salary_cap
    
    for slot in slot_order:
        candidates = [p for p in player_pool if slot in p['slots'] and p['name'] not in used]
        slots_left = len([s for s in slot_order if s not in lineup]) - 1
        min_remaining_cost = slots_left * 3500
        
        best = None
        for c in candidates:
            if c['salary'] <= remaining - min_remaining_cost:
                if best is None or c['value'] > best['value']:
                    best = c
        
        if best:
            lineup[slot] = best
            used.add(best['name'])
            remaining -= best['salary']
    
    return lineup, remaining

vlineup, vremaining = build_value_lineup(players)

total_fppg = 0
total_salary = 0
print(f"{'SLOT':6s} {'PLAYER':26s} {'TEAM':5s} {'FPPG':>6s} {'SALARY':>8s} {'VAL':>5s}")
print("-" * 62)
for slot in slot_order:
    if slot in vlineup:
        p = vlineup[slot]
        total_fppg += p['fppg']
        total_salary += p['salary']
        print(f"{slot:6s} {p['name']:26s} {p['team']:5s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['value']:>5.2f}")

print(f"\n{'TOTAL':6s} {'':26s} {'':5s} {total_fppg:>6.1f} ${total_salary:>7,}")
print(f"Remaining salary: ${50000 - total_salary:,}")
