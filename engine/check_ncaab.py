import sqlite3
conn = sqlite3.connect('results.db')
cur = conn.cursor()

cur.execute("PRAGMA table_info(pick_results)")
print("Schema:", cur.fetchall())

cur.execute("SELECT * FROM pick_results WHERE sport='ncaab' AND date LIKE '2026-02-20%'")
rows = cur.fetchall()
print(f"\nNCAA Feb 20 rows: {len(rows)}")
for r in rows:
    print(r)

if not rows:
    cur.execute("SELECT DISTINCT sport, date FROM pick_results ORDER BY date DESC LIMIT 20")
    print("\nRecent entries:")
    for r in cur.fetchall():
        print(r)
