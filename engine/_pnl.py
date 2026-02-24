import sqlite3
conn = sqlite3.connect('results.db')
cur = conn.cursor()

# Show tables
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)

for t in tables:
    print(f"\n--- {t[0]} schema ---")
    schema = cur.execute(f"SELECT sql FROM sqlite_master WHERE name='{t[0]}'").fetchone()
    print(schema[0] if schema else "no schema")
    
    rows = cur.execute(f"SELECT * FROM {t[0]} ORDER BY rowid DESC LIMIT 20").fetchall()
    cols = [d[0] for d in cur.description]
    print("Columns:", cols)
    for r in rows:
        print(r)

conn.close()
