import sqlite3
c = sqlite3.connect('engine/results.db')
cur = c.cursor()
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for t in tables:
    rows = cur.execute(f"SELECT * FROM {t[0]} LIMIT 20").fetchall()
    cols = [d[0] for d in cur.description]
    print(f"\n--- {t[0]} ({len(rows)} rows) ---")
    print("Columns:", cols)
    for r in rows:
        print(r)
