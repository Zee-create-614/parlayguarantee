import sqlite3, os, glob

# Find user-related tables in all DBs
for db in glob.glob('C:/Users/joshs/.openclaw/workspace/parlayguarantee/engine/*.db'):
    conn = sqlite3.connect(db)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for t in tables:
        if 'user' in t.lower() or 'email' in t.lower() or 'drip' in t.lower() or 'customer' in t.lower() or 'signup' in t.lower():
            print(f"{os.path.basename(db)}: {t}")
            cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
            print(f"  cols: {[c[1] for c in cols]}")
            rows = conn.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
            print(f"  rows: {rows}")
    conn.close()

# Check Next.js app for DB references
import re
for f in glob.glob('C:/Users/joshs/.openclaw/workspace/parlayguarantee/src/**/*.ts', recursive=True):
    content = open(f, encoding='utf-8', errors='ignore').read()
    if 'drip' in content.lower() or 'email_queue' in content.lower():
        print(f"\nDrip reference in: {f}")

# Check engine db.ts
dbts = 'C:/Users/joshs/.openclaw/workspace/parlayguarantee/engine/db.ts'
if os.path.exists(dbts):
    with open(dbts) as f:
        content = f.read()
    if 'user' in content.lower():
        print(f"\nUser references in db.ts")
        for i, line in enumerate(content.split('\n')):
            if 'user' in line.lower() or 'email' in line.lower() or 'drip' in line.lower():
                print(f"  L{i+1}: {line.strip()}")
