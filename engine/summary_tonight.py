import sys, json, glob, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(__file__)
grand = 0
print("TONIGHT'S EVENING SLATE — FINAL NUMBERS")
print("=" * 60)
for f in sorted(glob.glob(os.path.join(DIR, 'tonight_*2026-02-20*'))):
    d = json.load(open(f, encoding='utf-8'))
    s = d.get('summary', {})
    bets = s.get('total_bets', 0)
    games = d.get('total_games', 0)
    hc = s.get('high_conf', s.get('high_confidence_bets', 0))
    name = os.path.basename(f).replace('tonight_','').replace('_2026-02-20.json','')
    print(f"  {name:<30} {games:>3} games  {bets:>8,} parlays  ({hc:,} high-conf)")
    grand += bets

print("-" * 60)
print(f"  {'TOTAL':<30}          {grand:>8,} parlays")
print(f"\n  @ $5 single / $8 combo avg:")
print(f"  If every parlay sold once:    ${grand * 7.50:>12,.0f}")
print(f"  100 customers x 5 each:       ${500 * 7.50:>12,.0f}")
print(f"  1,000 customers x 10 each:    ${10000 * 7.50:>12,.0f}")
