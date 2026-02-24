import sqlite3, os
for db in ['engine_data.db', 'engine_data_v3.db', 'engine_data_v5.db', 'results.db']:
    if not os.path.exists(db):
        continue
    try:
        conn = sqlite3.connect(db)
        c = conn.cursor()
        tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f'\n=== {db} ===')
        for t in tables:
            tname = t[0]
            count = c.execute(f'SELECT COUNT(*) FROM [{tname}]').fetchone()[0]
            print(f'  {tname}: {count} rows')
            if count > 0:
                rows = c.execute(f'SELECT * FROM [{tname}] LIMIT 2').fetchall()
                for r in rows:
                    print(f'    {str(r)[:200]}')
        conn.close()
    except Exception as e:
        print(f'{db}: {e}')
