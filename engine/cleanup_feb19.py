import sqlite3
c = sqlite3.connect('results.db')
# Delete the bogus parlay results with wrong matchups
deleted = c.execute("DELETE FROM pick_results WHERE date='2026-02-19' AND product != 'nba_engine'").rowcount
print(f"Deleted {deleted} bogus parlay results")
# Delete bogus daily summaries except the corrected nba_engine one
deleted2 = c.execute("DELETE FROM daily_summaries WHERE date='2026-02-19' AND product != 'nba_engine'").rowcount
print(f"Deleted {deleted2} bogus daily summaries")
c.commit()
# Verify
for r in c.execute("SELECT * FROM daily_summaries WHERE date='2026-02-19'").fetchall():
    print(r)
print("\nPick results:")
for r in c.execute("SELECT pick_number, predicted_winner, actual_winner, correct, spread, spread_correct, confidence FROM pick_results WHERE date='2026-02-19'").fetchall():
    print(r)
