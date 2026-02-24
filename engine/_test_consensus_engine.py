import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from ncaab_engine import NCAABEngine
from datetime import date

engine = NCAABEngine()
preds = engine.predict_games(date(2026, 2, 21))

print(f"\n{len(preds)} predictions generated")
for p in preds[:10]:
    away = p.get("away_team", "?")
    home = p.get("home_team", "?")
    winner = p.get("predicted_winner", "?")
    conf = p.get("confidence", 0)
    spread = p.get("spread", "?")
    upset = p.get("upset_composite", 0)
    print(f"  {away} @ {home} | pick={winner} conf={conf:.1%} spread={spread} upset={upset:.2f}")
