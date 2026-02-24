import json, os, sqlite3

base = r'C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine'
conn = sqlite3.connect(os.path.join(base, 'results.db'))

# Get all individual pick results (the truth)
picks = conn.execute("""
    SELECT date, game_home, game_away, predicted_winner, correct, 
           spread_pick, spread_correct, sport, bet_type,
           ou_pick, ou_correct, confidence
    FROM pick_results 
    ORDER BY date, pick_number
""").fetchall()

print(f"Total scored picks in DB: {len(picks)}")

# Build lookup: (date, home, away) -> result
results_by_game = {}
for p in picks:
    key = (p[0], p[1], p[2])  # date, home, away
    results_by_game[key] = {
        'winner': p[3], 'correct': p[4],
        'spread_pick': p[5], 'spread_correct': p[6],
        'ou_pick': p[9], 'ou_correct': p[10],
        'confidence': p[11]
    }

# Now score all parlays from the scored file (Feb 20)
f = os.path.join(base, 'all_parlays_2026-02-20_scored.json')
data = json.load(open(f))
games = data['games']
bets = data['bets']

# Map game results
game_results = {}
for g in games:
    game_results[g['game_num']] = g['correct']  # True/False

print(f"\nFeb 20 games: {len(games)}")
print(f"Game results: {sum(1 for g in games if g['correct'])}/{len(games)} correct")

# Score parlays by leg count
for leg_type in ['2leg', '3leg', '4leg', '5leg']:
    parlays = bets.get(leg_type, [])
    if not parlays:
        continue
    
    total_legs = 0
    hit_legs = 0
    full_hits = 0
    
    for p in parlays:
        indices = p['game_indices']
        legs_hit = sum(1 for i in indices if game_results.get(i, False))
        total_legs += len(indices)
        hit_legs += legs_hit
        if legs_hit == len(indices):
            full_hits += 1
    
    pct = hit_legs / total_legs * 100 if total_legs else 0
    full_pct = full_hits / len(parlays) * 100 if parlays else 0
    print(f"\n{leg_type}: {len(parlays)} parlays")
    print(f"  Leg hit rate: {hit_legs}/{total_legs} ({pct:.1f}%)")
    print(f"  Full parlay hits: {full_hits}/{len(parlays)} ({full_pct:.1f}%)")

# Also check by confidence bucket
print("\n\n=== LEG HIT RATE BY CONFIDENCE ===")
for g in games:
    prob = g['win_prob']
    result = 'W' if g['correct'] else 'L'
    label = g.get('pick_label', '?')
    print(f"  {g['pick']:30s} conf={prob:.3f} label={label:8s} {result}")

# High confidence only parlays
print("\n=== HIGH CONFIDENCE PARLAYS (all legs >= 60%) ===")
for leg_type in ['2leg', '3leg', '4leg', '5leg']:
    parlays = bets.get(leg_type, [])
    hc_parlays = [p for p in parlays if p.get('all_high_confidence')]
    if not hc_parlays:
        continue
    
    total_legs = 0
    hit_legs = 0
    full_hits = 0
    
    for p in hc_parlays:
        indices = p['game_indices']
        legs_hit = sum(1 for i in indices if game_results.get(i, False))
        total_legs += len(indices)
        hit_legs += legs_hit
        if legs_hit == len(indices):
            full_hits += 1
    
    pct = hit_legs / total_legs * 100 if total_legs else 0
    full_pct = full_hits / len(hc_parlays) * 100 if hc_parlays else 0
    print(f"\n{leg_type} (high conf only): {len(hc_parlays)} parlays")
    print(f"  Leg hit rate: {hit_legs}/{total_legs} ({pct:.1f}%)")
    print(f"  Full parlay hits: {full_hits}/{len(hc_parlays)} ({full_pct:.1f}%)")

conn.close()
