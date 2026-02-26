import sqlite3
conn = sqlite3.connect('ncaab_cache/ncaab_stats.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    print(f"  {t[0]}: {count} rows")
    if count > 0:
        row = conn.execute(f"SELECT * FROM {t[0]} ORDER BY rowid DESC LIMIT 1").fetchone()
        cols = [d[0] for d in conn.execute(f"SELECT * FROM {t[0]} LIMIT 1").description]
        print(f"  Latest: {dict(zip(cols, row))}")
