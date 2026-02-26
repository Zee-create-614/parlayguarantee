import sqlite3
conn = sqlite3.connect('totals_engine_v3.db')
c = conn.cursor()
c.execute("SELECT sport, game_date, COUNT(*), SUM(CASE WHEN result='HIT' THEN 1 ELSE 0 END) FROM predictions WHERE result IS NOT NULL GROUP BY sport, game_date ORDER BY sport, game_date DESC")
for r in c.fetchall():
    sport, dt, total, hits = r
    pct = (hits/total*100) if total and hits else 0
    print(f"{sport:6s} {dt} {hits}/{total} ({pct:.0f}%)")
print()
# Also check alpha/rex spread results
for db in ['learning.db']:
    try:
        c2 = sqlite3.connect(db).cursor()
        c2.execute("SELECT name FROM sqlite_master WHERE type='table'")
        print(f"{db} tables:", [r[0] for r in c2.fetchall()])
        c2.execute("SELECT engine, game_date, COUNT(*), SUM(correct) FROM results GROUP BY engine, game_date ORDER BY engine, game_date DESC LIMIT 20")
        for r in c2.fetchall():
            eng, dt, total, hits = r
            pct = (hits/total*100) if total and hits else 0
            print(f"  {eng:10s} {dt} {hits}/{total} ({pct:.0f}%)")
    except Exception as e:
        print(f"{db}: {e}")
conn.close()
