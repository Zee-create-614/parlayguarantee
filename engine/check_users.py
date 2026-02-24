import sys, sqlite3, os, glob
sys.stdout.reconfigure(encoding='utf-8')

for db_file in glob.glob('*.db'):
    conn = sqlite3.connect(db_file)
    tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\n=== {db_file}: {tables} ===")
    for t in tables:
        try:
            rows = conn.execute(f"SELECT * FROM [{t}] LIMIT 10").fetchall()
            if rows:
                cols = [d[0] for d in conn.execute(f"SELECT * FROM [{t}] LIMIT 1").description]
                print(f"\n  {t} ({len(rows)} rows): {cols}")
                for r in rows:
                    print(f"    {r}")
        except Exception as e:
            print(f"  {t}: ERROR {e}")
    conn.close()
