import sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from ncaab_engine import NCAABEngine
e = NCAABEngine()
preds = e.predict_games()
for p in preds:
    home = p['home_team']
    away = p['away_team']
    winner = p['predicted_winner']
    conf = p['confidence']
    upset = p.get('upset_composite', 0)
    spread = p.get('factors', {}).get('spread_signal', 0)
    market_h = p.get('market_home_prob', 0.5)
    market_a = p.get('market_away_prob', 0.5)
    fav = home if market_h > market_a else away
    dog = away if market_h > market_a else home
    is_upset = winner != fav
    tag = " ** UPSET **" if is_upset else ""
    print(f"{away} @ {home}")
    print(f"  Pick: {winner} ({conf*100:.0f}%) | Market fav: {fav} ({max(market_h,market_a)*100:.0f}%)")
    print(f"  Upset composite: {upset:.3f} | Spread signal: {spread:.3f}{tag}")
    print()
