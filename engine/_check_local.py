import sqlite3
db = sqlite3.connect('results.db')
print('Tables:', db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
print('Summaries:', db.execute("SELECT * FROM daily_summaries ORDER BY date DESC LIMIT 10").fetchall())
cnt = db.execute("SELECT count(*) FROM pick_results").fetchone()
print('Results count:', cnt)
print('Products:', db.execute("SELECT DISTINCT product, date FROM pick_results ORDER BY date DESC LIMIT 20").fetchall())
print('Sample:', db.execute("SELECT * FROM pick_results LIMIT 3").fetchall())
