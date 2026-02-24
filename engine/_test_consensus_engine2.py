import sys, traceback
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

try:
    from ncaab_engine import NCAABEngine
    from datetime import date
    
    engine = NCAABEngine()
    print("Engine created, predicting...", flush=True)
    preds = engine.predict_games(date(2026, 2, 21))
    
    print(f"\n{len(preds)} predictions generated", flush=True)
    for p in preds[:10]:
        away = p.get("away_team", "?")
        home = p.get("home_team", "?")
        winner = p.get("predicted_winner", "?")
        conf = p.get("confidence", 0)
        spread = p.get("spread", "?")
        print(f"  {away} @ {home} | pick={winner} conf={conf:.1%} spread={spread}", flush=True)
except Exception as e:
    traceback.print_exc()
    print(f"\nERROR: {e}", flush=True)
