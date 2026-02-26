import sqlite3
c = sqlite3.connect('learning.db').cursor()

# Get all results by sport, date, pick_type
c.execute("""
SELECT sport, game_date, pick_type, tier,
  COUNT(*), 
  SUM(CASE WHEN spread_correct=1 THEN 1 ELSE 0 END) as spread_hits,
  SUM(CASE WHEN ou_correct=1 THEN 1 ELSE 0 END) as ou_hits
FROM picks WHERE scored=1 
GROUP BY sport, game_date, pick_type, tier
ORDER BY sport, game_date DESC, pick_type, tier
""")
print("=== LEARNING.DB SCORED PICKS ===")
for r in c.fetchall():
    print(f"  {r[0]:6s} {r[1]} {r[2]:8s} tier={r[3]:8s} n={r[4]} spread={r[5]} ou={r[6]}")

print()
# Overall by tier
c.execute("""
SELECT tier, COUNT(*), 
  SUM(CASE WHEN spread_correct=1 THEN 1 ELSE 0 END),
  SUM(CASE WHEN ou_correct=1 THEN 1 ELSE 0 END)
FROM picks WHERE scored=1 AND tier IS NOT NULL
GROUP BY tier ORDER BY tier
""")
print("=== BY TIER ===")
for r in c.fetchall():
    tier, n, sp, ou = r
    print(f"  {tier:10s} n={n}  spread={sp}/{n} ({sp/n*100:.0f}%)  ou={ou}/{n} ({ou/n*100:.0f}%)" if n else "")

print()
# By engine_version
c.execute("""
SELECT engine_version, sport, COUNT(*), 
  SUM(CASE WHEN spread_correct=1 THEN 1 ELSE 0 END),
  SUM(CASE WHEN ou_correct=1 THEN 1 ELSE 0 END)
FROM picks WHERE scored=1 
GROUP BY engine_version, sport ORDER BY engine_version, sport
""")
print("=== BY ENGINE VERSION ===")
for r in c.fetchall():
    eng, sport, n, sp, ou = r
    print(f"  {eng or 'None':15s} {sport:6s} n={n}  spread={sp}/{n}  ou={ou}/{n}")

# Value score analysis
print()
c.execute("""
SELECT 
  CASE WHEN value_score >= 0.7 THEN 'high_value'
       WHEN value_score >= 0.5 THEN 'mid_value'
       ELSE 'low_value' END as bucket,
  COUNT(*),
  SUM(CASE WHEN spread_correct=1 THEN 1 ELSE 0 END),
  AVG(confidence)
FROM picks WHERE scored=1 AND value_score IS NOT NULL
GROUP BY bucket ORDER BY bucket
""")
print("=== BY VALUE SCORE BUCKET ===")
for r in c.fetchall():
    bucket, n, hits, conf = r
    print(f"  {bucket:12s} n={n}  spread_hits={hits}/{n} ({hits/n*100:.0f}%)  avg_conf={conf:.2f}")
