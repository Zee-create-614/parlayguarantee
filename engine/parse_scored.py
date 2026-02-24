import json

# Load scored parlays
with open('all_parlays_2026-02-20_scored.json') as f:
    d = json.load(f)

# Individual games
games = d.get('individual_games', d.get('games', []))
print("=== INDIVIDUAL GAMES ===")
for g in games:
    pick = g.get('predicted_winner', g.get('pick', '?'))
    conf = g.get('confidence', g.get('win_prob', '?'))
    result = g.get('result', '?')
    actual = g.get('actual_winner', '?')
    away = g.get('away_team', g.get('away', '?'))
    home = g.get('home_team', g.get('home', '?'))
    score = g.get('actual_score', '')
    print(f"  {result} {away} @ {home} | Pick: {pick} ({conf}) | Actual: {actual} {score}")

# Parlays
parlays = d.get('parlays', [])
print(f"\n=== PARLAYS ({len(parlays)} total) ===")
tiers = {}
for p in parlays:
    legs = p.get('legs', p.get('num_legs', len(p.get('games', []))))
    tiers.setdefault(legs, []).append(p)

for k in sorted(tiers):
    tier = tiers[k]
    hits = sum(1 for p in tier if p.get('result') in ('HIT', 'WIN', True))
    print(f"\n--- {k}-LEG PARLAYS: {hits}/{len(tier)} HIT ---")
    for i, p in enumerate(tier):
        res = p.get('result', '?')
        games_list = p.get('games', p.get('picks', []))
        picks_str = ' + '.join(g.get('predicted_winner', g.get('pick', '?')) for g in games_list)
        print(f"  {res}: {picks_str}")

# Summary/revenue
meta = d.get('metadata', d.get('summary', {}))
print(f"\n=== METADATA ===")
print(json.dumps(meta, indent=2))

# Check for revenue info
for key in ['revenue', 'revenue_simulation', 'financials', 'summary']:
    if key in d:
        print(f"\n=== {key.upper()} ===")
        print(json.dumps(d[key], indent=2))
