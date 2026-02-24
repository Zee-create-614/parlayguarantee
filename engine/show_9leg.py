import json

d = json.load(open('all_parlays_2026-02-20.json', 'r', encoding='utf-8'))

# 9 leg parlay
nine = d['bets']['9leg'][0]
print('🌙 THE 9-LEG MOON SHOT 🌙')
print('=' * 50)
for i, p in enumerate(nine['picks']):
    label = p['pick_label']
    spread = p['spread']
    print(f"  Leg {i+1}: {p['pick']:<28} {p['win_prob']:.0%} | {label} | {spread:+.1f}")
print(f"\n  Combined prob: {nine['combined_prob']:.6f} ({nine['combined_prob']*100:.2f}%)")
print(f"  $10 bet pays: ${nine['implied_payout_per_100'] / 100 * 10:,.0f}")
print(f"  $25 bet pays: ${nine['implied_payout_per_100'] / 100 * 25:,.0f}")
print(f"  $50 bet pays: ${nine['implied_payout_per_100'] / 100 * 50:,.0f}")
print(f"  $100 bet pays: ${nine['implied_payout_per_100']:,.0f}")

# Revenue calculation
pricing = {
    'single': 5,
    '2leg': 8,
    '3leg': 8,
    '4leg': 10,
    '5leg': 10,
    '6leg': 15,
    '7leg': 15,
    '8leg': 20,
    '9leg': 20,
}

total_revenue = 0
print(f"\n\n💰 REVENUE IF ALL 511 BETS SOLD")
print('=' * 55)
for tier in ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg', '8leg', '9leg']:
    if tier in d['bets']:
        bets = d['bets'][tier]
        price = pricing[tier]
        tier_rev = len(bets) * price
        total_revenue += tier_rev
        print(f"  {tier:>10}: {len(bets):>4} bets × ${price:>2} = ${tier_rev:>6,}")

print(f"  {'':->55}")
print(f"  {'TOTAL':>10}: {511:>4} bets        = ${total_revenue:>6,}")
print(f"\n  That's ${total_revenue:,} in deposits we'd be holding tonight.")
print(f"  Tomorrow we see how much we keep vs refund.")
