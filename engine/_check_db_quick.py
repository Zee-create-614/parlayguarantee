import sqlite3
conn = sqlite3.connect('results.db')
cur = conn.cursor()
for r in cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
    print(f"\n=== {r[0]} ===")
    print(r[1])
    rows = cur.execute(f"SELECT COUNT(*) FROM {r[0]}").fetchone()
    print(f"Rows: {rows[0]}")
    sample = cur.execute(f"SELECT * FROM {r[0]} LIMIT 3").fetchall()
    for s in sample:
        print(s)
