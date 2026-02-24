import json

d = json.load(open('picks_output.json', 'r', encoding='utf-8'))

for tier_id in ['5leg', '6leg']:
    tier = d['tiers'][tier_id]
    print(f"\n{'='*60}")
    print(f"🎯 {tier['tier_name'].upper()} (Top Pick)")
    print(f"{'='*60}")
    for i, pick in enumerate(tier['picks']):
        games = pick.get('games', [])
        conf = pick.get('confidence', 0)
        payout = pick.get('estimated_payout', 'N/A')
        print(f"\nParlay #{i+1} | Combined Confidence: {conf:.1%} | Est Payout: {payout}")
        print("-"*50)
        for j, g in enumerate(games):
            upset = g.get('upset_potential', g.get('upset_score', 0))
            label = g.get('pick_label', '?')
            spread = g.get('spread', 0)
            print(f"  Leg {j+1}: {g['pick']:<28} {g['win_prob']:.1%} | {label} | upset={upset:.2f} | spread {spread:+.1f}")
