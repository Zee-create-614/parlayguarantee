"""Revenue simulation across all products at current pricing tiers."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Current pricing
SINGLE_PICK = 5
COMBO_PICK = 8  # 2-leg

# Product inventory from tonight
products = {
    'NBA Spread': {'single': 9, '2leg': 36, '3leg': 84, '4leg': 126, '5leg': 126, '6leg': 84, '7leg': 36, '8leg': 9, '9leg': 1},
    'NBA O/U': {'single': 9, '2leg': 36, '3leg': 84, '4leg': 126, '5leg': 126, '6leg': 84, '7leg': 36, '8leg': 9},
    'NBA Mixed': {'2leg': 153, '3leg': 816, '4leg': 3060, '5leg': 8568},
    'NCAAB Spread': {'single': 37, '2leg': 666, '3leg': 7770, '4leg': 66045},
    'NCAAB O/U': {'single': 38, '2leg': 703, '3leg': 8436, '4leg': 73815},
    'NCAAB Mixed': {'2leg': 2775, '3leg': 67525},
    'Cross-Sport': {'2leg': 1035, '3leg': 15180},
    'Ultimate Mixed': {'2leg': 4278, '3leg': 129766},
}

# Pricing tiers
# Singles: $5
# 2-leg: $8
# 3-leg: $8
# 4-leg+: $8 (combo price)
# Could also do pack pricing: 10 picks for $50, etc.

print("=" * 70)
print("REVENUE SIMULATION - IF EVERY UNIQUE PARLAY SOLD ONCE")
print("=" * 70)

grand_total = 0
grand_bets = 0

for product, tiers in products.items():
    prod_rev = 0
    prod_bets = 0
    for tier, count in tiers.items():
        if tier == 'single':
            price = SINGLE_PICK
        else:
            price = COMBO_PICK
        rev = count * price
        prod_rev += rev
        prod_bets += count
    grand_total += prod_rev
    grand_bets += prod_bets
    print(f"  {product:<20} {prod_bets:>8,} bets  x  avg ${prod_rev/prod_bets:.2f}  =  ${prod_rev:>12,}")

print("=" * 70)
print(f"  {'TOTAL':<20} {grand_bets:>8,} bets              =  ${grand_total:>12,}")
print()

# More realistic scenarios
print("REALISTIC SCENARIOS")
print("-" * 70)

scenarios = [
    ("If 1% of parlays sell (3,917 sales)", grand_bets * 0.01),
    ("If 100 customers buy 5 each", 500),
    ("If 500 customers buy 3 each", 1500),
    ("If 1,000 customers buy 10 each", 10000),
]

avg_price = grand_total / grand_bets

for label, sales in scenarios:
    rev = sales * avg_price
    print(f"  {label:<45} = ${rev:>10,.0f}")

print()
print("PACK PRICING MODEL")
print("-" * 70)
packs = [
    ("Single Pick", 5, 1),
    ("Combo Pick (2-leg)", 8, 1),
    ("Single Sport Pack (10 picks)", 50, 10),
    ("2-Sport Bundle (10+10)", 75, 20),
    ("Day Pass (unlimited)", 25, None),
    ("Weekly Pass (unlimited)", 99, None),
    ("Monthly Sub", 199, None),
]
for name, price, picks in packs:
    print(f"  {name:<35} ${price}")

print()
print(f"At $5-8 per parlay, tonight's full inventory = ${grand_total:,}")
print(f"That's {grand_bets:,} unique products from just 9 NBA + 37 NCAAB games.")
print(f"March Madness (67 games/day) would generate MILLIONS of unique parlays.")
