import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from totals_engine import TotalsEngine
e = TotalsEngine()
preds = e.run_predictions()
for p in preds:
    away = p['away_team']
    home = p['home_team']
    pick = p['pick']
    posted = p['posted_total']
    edge = p['edge']
    tier = p['tier']
    pred = p['predicted_total']
    print(f"{away} @ {home}: {pick} {posted} (pred {pred}) | edge {edge:+.1f} | {tier}")
