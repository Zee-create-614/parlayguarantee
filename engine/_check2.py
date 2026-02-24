import sqlite3, os
c = sqlite3.connect('results.db')
cur = c.cursor()
# pick_results
cur.execute("SELECT * FROM pick_results ORDER BY rowid DESC LIMIT 3")
print(f"pick_results cols: {[d[0] for d in cur.description]}")
for r in cur.fetchall():
    print(r)

# daily_summaries
cur.execute("SELECT * FROM daily_summaries ORDER BY rowid DESC LIMIT 3")
print(f"\ndaily_summaries cols: {[d[0] for d in cur.description]}")
for r in cur.fetchall():
    print(r)

# Check today's picks dir
d = 'picks_2026-02-22'
if os.path.isdir(d):
    print(f"\n{d}/: {os.listdir(d)}")

# Check result scorecard
if os.path.exists('results_2026-02-21_scorecard.md'):
    with open('results_2026-02-21_scorecard.md') as f:
        print(f"\nScorecard preview:\n{f.read()[:500]}")
