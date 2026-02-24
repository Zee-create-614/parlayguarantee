import json, sqlite3, os
# Check analyzed games
d = json.load(open('analyzed_games.json'))
print(f"analyzed_games.json: {len(d)} games, date={d[0].get('game_date','?')}")
sports = {}
for g in d:
    s = g.get('sport','?')
    sports[s] = sports.get(s,0)+1
print(f"  Sports: {sports}")
hi = [g for g in d if g.get('enhanced_prob',0) >= 0.6]
print(f"  High confidence (>=60%): {len(hi)}")

# Check picks_output
p = json.load(open('picks_output.json'))
print(f"\npicks_output.json: date={p.get('date')}, games={p.get('total_games')}")
for tier_name, tier_data in (p.get('tiers') or {}).items():
    print(f"  tier '{tier_name}': {len(tier_data) if isinstance(tier_data,list) else type(tier_data)}")

# Check results DB
c = sqlite3.connect('results.db')
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"\nresults.db tables: {[t[0] for t in tables]}")
for t in tables:
    cnt = c.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
    print(f"  {t[0]}: {cnt} rows")
    sample = c.execute(f"SELECT * FROM [{t[0]}] ORDER BY rowid DESC LIMIT 2").fetchall()
    cols = [d[0] for d in c.description]
    print(f"    cols: {cols}")
    for r in sample:
        print(f"    {r}")

# Check picks folder for today
today_dir = 'picks_2026-02-22'
if os.path.isdir(today_dir):
    files = os.listdir(today_dir)
    print(f"\n{today_dir}/: {files}")
