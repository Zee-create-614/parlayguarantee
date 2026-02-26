import sqlite3

# results.db - the main scored results
c = sqlite3.connect('results.db').cursor()
c.execute("SELECT date, product, total_picks, correct_picks, accuracy FROM daily_summaries ORDER BY date DESC")
print("=== DAILY SUMMARIES ===")
for r in c.fetchall():
    print(f"  {r[0]} {r[1]:20s} {r[3]}/{r[2]} ({r[4]*100:.0f}%)")

print("\n=== PICK RESULTS BY DATE+TYPE ===")
c.execute("""SELECT date, type, COUNT(*), SUM(correct), AVG(confidence) 
FROM pick_results GROUP BY date, type ORDER BY date DESC, type""")
for r in c.fetchall():
    d, t, n, hits, conf = r
    pct = hits/n*100 if n and hits else 0
    print(f"  {d} {t:12s} {hits}/{n} ({pct:.0f}%) conf={conf:.2f}")

# Totals V3 - unscored but has predictions
print("\n=== TOTALS V3 (UNSCORED PREDICTIONS) ===")
c = sqlite3.connect('totals_engine_v3.db').cursor()
c.execute("SELECT sport, game_date, pick, COUNT(*), AVG(confidence), AVG(edge) FROM predictions GROUP BY sport, game_date, pick ORDER BY sport, game_date DESC, pick")
for r in c.fetchall():
    print(f"  {r[0]:6s} {r[1]} {r[2]:5s} n={r[3]} conf={r[4]:.1f} edge={r[5]:.1f}")

# Adaptive learner results
print("\n=== ADAPTIVE LEARNER RESULTS ===")
import json
for f in ['learned_weights/alpha_results.json', 'learned_weights/rex_results.json']:
    try:
        data = json.load(open(f))
        print(f"\n{f}: {len(data)} entries")
        for entry in data:
            print(f"  {entry}")
    except Exception as e: print(f"{f}: {e}")
