import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
d = json.load(open('alpha_nba_picks_2026-02-24.json'))
for g in d:
    away = g.get('away','?')
    home = g.get('home','?')
    upset = g.get('upset_score', 0)
    flip = g.get('upset_flip', False)
    reasons = g.get('upset_reasons', [])
    ml = g.get('ml_confidence', 0)
    spread = g.get('spread_confidence', 0)
    print(f"{away} @ {home}")
    print(f"  ML: {ml:.1%} | Spread: {spread:.1%} | Upset: {upset:.3f} | Flip: {flip}")
    if reasons:
        for r in reasons[:2]:
            print(f"  - {r}")
    print()
