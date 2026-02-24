import json

d = json.load(open('picks_output.json', 'r', encoding='utf-8'))
print(f"=== TONIGHT'S PICKS ({d['date']}) — {d['total_games']} games ===\n")

# Show analyzed games with upset composite
games = json.load(open('analyzed_games.json', 'r', encoding='utf-8'))
print("📊 ALL 9 GAMES — 38-Factor Model + Upset Composite:\n")
print(f"{'Matchup':<45} {'Pick':<25} {'Win%':>6} {'Value':>6} {'Edge':>7} {'Upset':>6} {'Label'}")
print("-" * 110)
for g in games:
    matchup = f"{g['away']} @ {g['home']}"
    pick = g['pick']
    wp = g['win_prob']
    vs = g.get('value_score', 0)
    edge = g.get('edge_vs_market', 0)
    upset = g.get('upset_potential', g.get('upset_score', 0))
    label = g.get('pick_label', '?')
    spread = g.get('spread', 0)
    print(f"{matchup:<45} {pick:<25} {wp:>5.1%} {vs:>6.3f} {edge:>+6.1%} {upset:>6.3f} {label} (spread {spread:+.1f})")

print(f"\n{'='*110}")
print("\n🎯 MONEYLINE SINGLES (Top 5):\n")
for p in d['tiers']['single']['picks']:
    games_in = p.get('games', [p])
    for g in games_in:
        print(f"  {g['pick']} ({g['win_prob']:.1%}) — {g.get('pick_label','?')} | upset={g.get('upset_potential',0):.3f}")

print("\n🎯 SPREAD SINGLES (Top 5):\n")
for p in d['tiers']['spread_single']['picks']:
    games_in = p.get('games', [p])
    for g in games_in:
        sp = g.get('spread_value', g.get('spread', 0))
        print(f"  {g.get('spread_pick', g['pick'])} {sp:+.1f} (cover {g.get('cover_prob', g['win_prob']):.1%}) — {g.get('pick_label','?')}")
