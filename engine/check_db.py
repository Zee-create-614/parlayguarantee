import sqlite3
conn = sqlite3.connect('results.db')
cur = conn.cursor()
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for t in tables:
    cols = cur.execute(f"PRAGMA table_info({t[0]})").fetchall()
    print(f"\n{t[0]} columns:", cols)
    rows = cur.execute(f"SELECT * FROM {t[0]} LIMIT 2").fetchall()
    print(f"Sample rows:", rows)
