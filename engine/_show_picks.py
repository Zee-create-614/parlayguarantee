import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
with open('ncaab_picks_2026-02-21.json') as f:
    picks = json.load(f)
print(f"Total: {len(picks)} picks")
has_spread = sum(1 for p in picks if p.get('spread') is not None)
has_ml = sum(1 for p in picks if p.get('home_odds') is not None)
print(f"With spreads: {has_spread}, With ML: {has_ml}")

# Source distribution
from collections import Counter
book_counts = Counter()
for p in picks:
    for b in p.get('available_books', []):
        book_counts[b] += 1
print(f"Books: {dict(book_counts)}")

# Confidence distribution
confs = [p['confidence'] for p in picks]
print(f"Confidence: {min(confs):.1%} - {max(confs):.1%}")
above70 = sum(1 for c in confs if c >= 0.70)
above60 = sum(1 for c in confs if c >= 0.60)
print(f"60%+: {above60}, 70%+: {above70}")

print("\nTOP 15 PICKS:")
for i, p in enumerate(picks[:15], 1):
    away = p.get('away_team', '?')
    home = p.get('home_team', '?')
    winner = p.get('predicted_winner', '?')
    conf = p.get('confidence', 0)
    spread = p.get('spread')
    ml_h = p.get('home_odds')
    ml_a = p.get('away_odds')
    books = '/'.join(p.get('available_books', []))
    sp_pick = p.get('spread_pick', '')
    print(f"  #{i}: {away} @ {home}")
    print(f"      PICK: {winner} ({conf:.1%}) | spread={spread} ML={ml_a}/{ml_h} | {sp_pick}")
    print(f"      Books: {books}")
