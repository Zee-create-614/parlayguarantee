import sqlite3

try:
    conn = sqlite3.connect('results.db')
    c = conn.cursor()
    
    # Check table structure
    tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"Tables: {[t[0] for t in tables]}")
    
    # Check pick_results for Feb 19
    results = c.execute("SELECT * FROM pick_results WHERE date='2026-02-19'").fetchall()
    print(f"\nFeb 19 pick results ({len(results)} records):")
    for r in results:
        print(f"  {r}")
    
    # Check daily_summaries for Feb 19
    summaries = c.execute("SELECT * FROM daily_summaries WHERE date='2026-02-19'").fetchall()
    print(f"\nFeb 19 daily summaries ({len(summaries)} records):")
    for s in summaries:
        print(f"  {s}")
        
    # Show recent dates in pick_results
    recent = c.execute("SELECT date, COUNT(*) FROM pick_results GROUP BY date ORDER BY date DESC LIMIT 10").fetchall()
    print(f"\nRecent dates in pick_results:")
    for r in recent:
        print(f"  {r}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")