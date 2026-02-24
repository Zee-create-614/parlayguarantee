import sqlite3
for db in ['engine_data.db', 'engine_data_v3.db', 'engine_data_v5.db']:
    conn = sqlite3.connect(db)
    c = conn.cursor()
    # Get column names
    cols = c.execute("PRAGMA table_info(predictions)").fetchall()
    print(f'\n{db} predictions columns: {[c[1] for c in cols]}')
    rows = c.execute("SELECT game_date, COUNT(*) FROM predictions GROUP BY game_date ORDER BY game_date DESC LIMIT 10").fetchall()
    for r in rows:
        print(f'  {r}')
    feb19 = c.execute("SELECT home_team, away_team, predicted_winner, confidence FROM predictions WHERE game_date='2026-02-19'").fetchall()
    if feb19:
        print(f'  Feb 19 picks ({len(feb19)}):')
        for r in feb19:
            print(f'    {r}')
    conn.close()
