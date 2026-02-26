import sqlite3

# Check results.db
print("=== RESULTS.DB ===")
c = sqlite3.connect('results.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)
for t in tables[:3]:
    c.execute(f"PRAGMA table_info({t})")
    cols = [r[1] for r in c.fetchall()]
    c.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t}: {c.fetchone()[0]} rows, cols: {cols[:10]}")

# Check engine_data_v3 for scored results
print("\n=== ENGINE_DATA_V3.DB ===")
c = sqlite3.connect('engine_data_v3.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)
for t in tables[:5]:
    c.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t}: {c.fetchone()[0]} rows")

# Check ncaab_engine for scored results
print("\n=== NCAAB_ENGINE.DB ===")
c = sqlite3.connect('ncaab_engine.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)

# Check totals_engine_v3 
print("\n=== TOTALS_ENGINE_V3.DB ===")
c = sqlite3.connect('totals_engine_v3.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)
c.execute("SELECT sport, result, COUNT(*) FROM predictions WHERE result IS NOT NULL GROUP BY sport, result")
rows = c.fetchall()
if rows:
    for r in rows: print(f"  {r}")
else:
    c.execute("SELECT sport, COUNT(*), MIN(game_date), MAX(game_date) FROM predictions GROUP BY sport")
    for r in c.fetchall(): print(f"  {r}")

# Check ncaab_totals_v2
print("\n=== NCAAB_TOTALS_V2.DB ===")
c = sqlite3.connect('ncaab_totals_v2.db').cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in c.fetchall()])
c.execute("SELECT COUNT(*) FROM predictions")
print(f"  predictions: {c.fetchone()[0]} rows")
c.execute("SELECT result, COUNT(*) FROM predictions WHERE result IS NOT NULL GROUP BY result")
for r in c.fetchall(): print(f"  result={r[0]}: {r[1]}")

# Adaptive learner results
print("\n=== LEARNED WEIGHTS ===")
import json
for f in ['learned_weights/alpha_results.json', 'learned_weights/rex_results.json']:
    try:
        data = json.load(open(f))
        print(f"\n{f}:")
        for entry in data[-3:]:
            print(f"  {entry.get('date','?')}: {entry.get('correct',0)}/{entry.get('total',0)} ({entry.get('accuracy',0)*100:.0f}%)")
    except: pass
