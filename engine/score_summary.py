import json

# NBA Moneyline
d = json.load(open('all_parlays_2026-02-20_scored.json'))
games = d['games']
wins = sum(1 for g in games if g['correct'])
print(f"=== NBA MONEYLINE: {wins}/{len(games)} ({wins/len(games)*100:.0f}%) ===")
for g in games:
    r = 'W' if g['correct'] else 'L'
    tag = g.get('pick_label', '')
    print(f"  [{r}] {g['away']} @ {g['home']} -> Pick: {g['pick']} ({tag}) | {g['actual_score']}")

# Upset flips
upsets = [g for g in games if g.get('upset_flip')]
upset_wins = sum(1 for g in upsets if g['correct'])
print(f"\n  Upset flips: {upset_wins}/{len(upsets)}")
non_upsets = [g for g in games if not g.get('upset_flip')]
non_upset_wins = sum(1 for g in non_upsets if g['correct'])
print(f"  Non-upset picks: {non_upset_wins}/{len(non_upsets)}")

# O/U
print()
ou = json.load(open('scored_results_2026-02-20.json'))
for k, v in ou.items():
    if k == 'date' or not isinstance(v, dict):
        continue
    results = v.get('results', [])
    scored = [r for r in results if r['result'] != 'NO SCORE']
    hits = sum(1 for r in scored if r['result'] == 'HIT')
    total = len(scored)
    if total:
        print(f"=== {v['sport']}: {hits}/{total} ({hits/total*100:.0f}%) ===")
        for r in scored:
            tag = 'HIT' if r['result'] == 'HIT' else 'MISS'
            print(f"  [{tag}] {r['matchup']} -> {r['pick']} (edge {r['edge']:+.1f}) | Posted: {r['posted']}, Actual: {r['actual']}")
    else:
        print(f"=== {v['sport']}: No scored games (ESPN data missing) ===")
