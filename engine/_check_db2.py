import sqlite3
conn = sqlite3.connect('ncaab_data.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
    latest = conn.execute(f"SELECT last_updated FROM [{t[0]}] ORDER BY last_updated DESC LIMIT 1").fetchone()
    print(f"  {t[0]}: {count} rows, latest: {latest[0] if latest else 'n/a'}")
