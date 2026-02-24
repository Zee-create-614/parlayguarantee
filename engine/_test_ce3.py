import sys, traceback, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s',
                    handlers=[logging.FileHandler('_test_ce3.log', encoding='utf-8'),
                              logging.StreamHandler()])

try:
    from ncaab_engine import NCAABEngine
    from datetime import date
    
    engine = NCAABEngine()
    print("Predicting...", flush=True)
    preds = engine.predict_games(date(2026, 2, 21))
    
    print(f"{len(preds)} predictions", flush=True)
    for p in preds[:5]:
        print(f"  {p.get('away_team','?')} @ {p.get('home_team','?')} | {p.get('predicted_winner','?')} {p.get('confidence',0):.0%}", flush=True)
except Exception as e:
    with open('_test_ce3_error.txt', 'w', encoding='utf-8') as f:
        traceback.print_exc(file=f)
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
