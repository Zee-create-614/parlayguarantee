#!/usr/bin/env python3
"""Score Rex V2 Feb 24 picks against actual results"""
import json, sys, os
sys.path.insert(0, os.path.dirname(__file__))

# Load picks
with open('rex_v2_ncaab_picks_2026-02-24.json') as f:
    picks = json.load(f)

# Try to get scores via Odds API
from autopilot import ODDS_API_KEY
import requests

print(f"Total games analyzed: {len(picks)}")
spread_picks = [p for p in picks if p.get('spread_status') == 'PICK' and p.get('spread_pick')]
ml_picks = [p for p in picks if p.get('ml_status') == 'PICK']
ou_picks = [p for p in picks if p.get('ou_pick')]
print(f"Spread picks: {len(spread_picks)}")
print(f"ML picks: {len(ml_picks)}")  
print(f"O/U picks: {len(ou_picks)}")

# Fetch scores
url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores/"
params = {"apiKey": ODDS_API_KEY, "daysFrom": 2, "dateFormat": "iso"}
resp = requests.get(url, params=params, timeout=30)
scores_data = resp.json()
print(f"\nScores API returned {len(scores_data)} games")

# Build score lookup
score_map = {}
for g in scores_data:
    if not g.get('completed'):
        continue
    teams = {}
    for s in g.get('scores', []):
        teams[s['name']] = int(s['score'])
    if len(teams) == 2:
        home = g.get('home_team', '')
        away = g.get('away_team', '')
        score_map[f"{away}@{home}"] = teams

print(f"Completed games with scores: {len(score_map)}")

# Score spread picks
spread_hits = 0
spread_misses = 0
spread_push = 0
spread_unmatched = 0

print("\n=== SPREAD RESULTS ===")
for p in spread_picks:
    key = f"{p['away_team']}@{p['home_team']}"
    if key not in score_map:
        spread_unmatched += 1
        print(f"  ? {p['away_team']} @ {p['home_team']} - NO SCORE FOUND")
        continue
    
    scores = score_map[key]
    home_score = scores.get(p['home_team'], 0)
    away_score = scores.get(p['away_team'], 0)
    margin = home_score - away_score  # positive = home won
    spread_val = p['spread']  # negative = home favored
    
    # Spread pick covers if: margin + spread > 0 means home covers, < 0 means away covers
    # The spread_pick text tells us who to take
    pick_text = p['spread_pick']
    
    # If pick is "Away +X" we're taking away + spread
    # If pick is "Home -X" we're taking home - spread  
    # ATS margin from home perspective: margin + spread (if spread is the away line)
    ats = margin + spread_val  # This gives ATS from home perspective
    
    # Determine if we picked home or away spread
    if p['predicted_winner'] == p['home_team']:
        # We picked home to cover (spread is negative for home)
        covered = margin + spread_val > 0  # home margin beats the spread
    else:
        # We picked away to cover (spread is positive for away, meaning away_score + spread vs home_score)
        covered = away_score + abs(spread_val) > home_score if spread_val > 0 else away_score - spread_val > home_score
    
    # Simpler: the spread_pick is always from underdog perspective "+X"
    # If spread_pick = "Minnesota +22.2", Minnesota gets 22.2 pts
    # Minnesota covers if: away_score + 22.2 > home_score
    # i.e., margin (home - away) < 22.2
    
    # Actually let's just use the spread value directly
    # spread field: negative = home favored, positive = away favored (home is dog)
    # For "Minnesota +22.2" at Michigan: spread = -22.2 (Michigan favored by 22.2)
    # Cover check: did the underdog cover? margin < |spread|
    
    if spread_val < 0:
        # Home favored. Pick is away + |spread|. Away covers if margin < |spread|
        ats_margin = abs(spread_val) - margin
        covered = ats_margin > 0
        push = ats_margin == 0
    else:
        # Away favored (home is dog). Pick is home + spread. Home covers if margin > -spread
        ats_margin = margin + spread_val
        covered = ats_margin > 0
        push = ats_margin == 0
    
    result = "HIT" if covered else ("PUSH" if push else "MISS")
    if covered:
        spread_hits += 1
    elif push:
        spread_push += 1
    else:
        spread_misses += 1
    
    print(f"  {result} | {p['away_team']} @ {p['home_team']} ({away_score}-{home_score}) | Pick: {pick_text} ({p['spread_confidence']:.0%})")

total_decided = spread_hits + spread_misses
print(f"\nSPREAD: {spread_hits}/{total_decided} ({spread_hits/total_decided*100:.1f}%) | Pushes: {spread_push} | Unmatched: {spread_unmatched}")

# Score ML picks  
ml_hits = 0
ml_misses = 0
ml_unmatched = 0

print("\n=== ML RESULTS ===")
for p in ml_picks:
    key = f"{p['away_team']}@{p['home_team']}"
    if key not in score_map:
        ml_unmatched += 1
        continue
    
    scores = score_map[key]
    home_score = scores.get(p['home_team'], 0)
    away_score = scores.get(p['away_team'], 0)
    
    actual_winner = p['home_team'] if home_score > away_score else p['away_team']
    hit = actual_winner == p['predicted_winner']
    
    if hit:
        ml_hits += 1
    else:
        ml_misses += 1
    
    result = "HIT" if hit else "MISS"
    print(f"  {result} | {p['away_team']} @ {p['home_team']} ({away_score}-{home_score}) | Pick: {p['predicted_winner']} ({p['confidence']:.0%})")

ml_total = ml_hits + ml_misses
if ml_total:
    print(f"\nML: {ml_hits}/{ml_total} ({ml_hits/ml_total*100:.1f}%) | Unmatched: {ml_unmatched}")

# Score O/U picks
ou_hits = 0
ou_misses = 0
ou_unmatched = 0

print("\n=== O/U RESULTS ===")
for p in ou_picks:
    key = f"{p['away_team']}@{p['home_team']}"
    if key not in score_map:
        ou_unmatched += 1
        continue
    
    scores = score_map[key]
    home_score = scores.get(p['home_team'], 0)
    away_score = scores.get(p['away_team'], 0)
    total_score = home_score + away_score
    total_line = p['total']
    
    ou_text = p['ou_pick']
    if 'Over' in ou_text:
        hit = total_score > total_line
    else:
        hit = total_score < total_line
    
    if hit:
        ou_hits += 1
    else:
        ou_misses += 1
    
    result = "HIT" if hit else "MISS"
    print(f"  {result} | {p['away_team']} @ {p['home_team']} ({away_score}-{home_score}, total={total_score}) | {ou_text} (line {total_line})")

ou_total = ou_hits + ou_misses
if ou_total:
    print(f"\nO/U: {ou_hits}/{ou_total} ({ou_hits/ou_total*100:.1f}%) | Unmatched: {ou_unmatched}")
