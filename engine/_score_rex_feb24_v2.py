#!/usr/bin/env python3
"""Score Rex V2 Feb 24 picks against actual results - fuzzy matching"""
import json, sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

with open('rex_v2_ncaab_picks_2026-02-24.json') as f:
    picks = json.load(f)

from autopilot import ODDS_API_KEY
import requests

url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/"
params = {"apiKey": ODDS_API_KEY, "daysFrom": 2, "dateFormat": "iso"}
resp = requests.get(url, params=params, timeout=30)
scores_data = resp.json()

# Build completed games list with flexible matching
completed = []
for g in scores_data:
    if not g.get('completed'):
        continue
    teams = {}
    for s in g.get('scores', []):
        teams[s['name']] = int(s['score'])
    if len(teams) == 2:
        completed.append({
            'home': g.get('home_team', ''),
            'away': g.get('away_team', ''),
            'scores': teams,
            'commence': g.get('commence_time', '')
        })

print(f"Completed NCAAB games: {len(completed)}")

def normalize(name):
    return re.sub(r'[^a-z]', '', name.lower())

def find_game(home, away):
    nh, na = normalize(home), normalize(away)
    for g in completed:
        gh, ga = normalize(g['home']), normalize(g['away'])
        if (nh in gh or gh in nh) and (na in ga or ga in na):
            return g
        if (nh in ga or ga in nh) and (na in gh or gh in na):
            return g
    return None

spread_picks = [p for p in picks if p.get('spread_status') == 'PICK' and p.get('spread_pick')]
ml_picks = [p for p in picks if p.get('ml_status') in ('PICK', 'WEAK')]
ou_picks = [p for p in picks if p.get('ou_pick')]

print(f"Spread picks: {len(spread_picks)} | ML picks: {len(ml_picks)} | O/U picks: {len(ou_picks)}")

# Score spreads
s_hit = s_miss = s_push = s_unm = 0
print("\n=== SPREAD RESULTS ===")
for p in spread_picks:
    g = find_game(p['home_team'], p['away_team'])
    if not g:
        s_unm += 1
        print(f"  ? {p['away_team']} @ {p['home_team']} - NO SCORE")
        continue
    
    # Get scores by matching team names
    home_score = away_score = 0
    for tname, tscore in g['scores'].items():
        if normalize(p['home_team']) in normalize(tname) or normalize(tname) in normalize(p['home_team']):
            home_score = tscore
        elif normalize(p['away_team']) in normalize(tname) or normalize(tname) in normalize(p['away_team']):
            away_score = tscore
    
    margin = home_score - away_score
    spread_val = p['spread']
    
    if spread_val < 0:
        ats_margin = abs(spread_val) - margin
    else:
        ats_margin = margin + spread_val
    
    covered = ats_margin > 0
    push = ats_margin == 0
    
    if covered: s_hit += 1
    elif push: s_push += 1
    else: s_miss += 1
    
    tag = "✅" if covered else ("➡️" if push else "❌")
    print(f"  {tag} {p['away_team']} @ {p['home_team']} ({away_score}-{home_score}) | {p['spread_pick']} ({p['spread_confidence']:.0%}) | margin={margin}, ats={ats_margin:+.1f}")

total = s_hit + s_miss
if total:
    print(f"\nSPREAD: {s_hit}/{total} ({s_hit/total*100:.1f}%) | Push: {s_push} | No score: {s_unm}")

# Score ML
m_hit = m_miss = m_unm = 0
print("\n=== ML RESULTS ===")
for p in ml_picks:
    g = find_game(p['home_team'], p['away_team'])
    if not g:
        m_unm += 1
        continue
    
    home_score = away_score = 0
    for tname, tscore in g['scores'].items():
        if normalize(p['home_team']) in normalize(tname) or normalize(tname) in normalize(p['home_team']):
            home_score = tscore
        elif normalize(p['away_team']) in normalize(tname) or normalize(tname) in normalize(p['away_team']):
            away_score = tscore
    
    actual = p['home_team'] if home_score > away_score else p['away_team']
    hit = actual == p['predicted_winner']
    if hit: m_hit += 1
    else: m_miss += 1
    
    tag = "✅" if hit else "❌"
    print(f"  {tag} {p['away_team']} @ {p['home_team']} ({away_score}-{home_score}) | Pick: {p['predicted_winner']} ({p['confidence']:.0%})")

mt = m_hit + m_miss
if mt:
    print(f"\nML: {m_hit}/{mt} ({m_hit/mt*100:.1f}%) | No score: {m_unm}")

# Score O/U
o_hit = o_miss = o_unm = 0
print("\n=== O/U RESULTS ===")
for p in ou_picks:
    g = find_game(p['home_team'], p['away_team'])
    if not g:
        o_unm += 1
        continue
    
    home_score = away_score = 0
    for tname, tscore in g['scores'].items():
        if normalize(p['home_team']) in normalize(tname) or normalize(tname) in normalize(p['home_team']):
            home_score = tscore
        elif normalize(p['away_team']) in normalize(tname) or normalize(tname) in normalize(p['away_team']):
            away_score = tscore
    
    total_pts = home_score + away_score
    line = p['total']
    over = 'Over' in p['ou_pick']
    hit = (total_pts > line) if over else (total_pts < line)
    if hit: o_hit += 1
    else: o_miss += 1
    
    tag = "✅" if hit else "❌"
    print(f"  {tag} {p['away_team']} @ {p['home_team']} ({total_pts}) | {p['ou_pick']} (line {line})")

ot = o_hit + o_miss
if ot:
    print(f"\nO/U: {o_hit}/{ot} ({o_hit/ot*100:.1f}%) | No score: {o_unm}")
