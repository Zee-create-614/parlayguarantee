import sqlite3, glob
for db in glob.glob("*.db"):
    try:
        conn = sqlite3.connect(db)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        print(f"\n{db}: {tables}")
        for t in tables:
            c.execute(f"SELECT COUNT(*) FROM [{t}]")
            cnt = c.fetchone()[0]
            if cnt > 0:
                c.execute(f"SELECT * FROM [{t}] LIMIT 1")
                cols = [d[0] for d in c.description]
                print(f"  {t}: {cnt} rows, cols={cols}")
        conn.close()
    except Exception as e:
        print(f"{db}: {e}")
