import sys, json, os, sqlite3
sys.stdout.reconfigure(encoding='utf-8')

# Check analyzed_games.json
if os.path.exists('analyzed_games.json'):
    data = json.load(open('analyzed_games.json'))
    if isinstance(data, list):
        print(f'analyzed_games.json: {len(data)} games')
        if data:
            print(f'  First game date: {data[0].get("game_date","?")}')
    else:
        print(f'analyzed_games.json: dict')
else:
    print('analyzed_games.json: MISSING')

# Check picks_output.json  
if os.path.exists('picks_output.json'):
    data = json.load(open('picks_output.json'))
    print(f'picks_output.json: {len(data)} keys: {list(data.keys())[:5]}')
    for k, v in data.items():
        print(f'  {k}: {v.get("total_picks",0)} picks, date={v.get("date","?")}')
else:
    print('picks_output.json: MISSING')

# Check results.db
if os.path.exists('results.db'):
    db = sqlite3.connect('results.db')
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f'\nresults.db tables: {[t[0] for t in tables]}')
    for t in tables:
        c = db.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()
        print(f'  {t[0]}: {c[0]} rows')
    # Latest results
    try:
        latest = db.execute("SELECT date, product, correct, actual_winner FROM pick_results ORDER BY date DESC LIMIT 3").fetchall()
        print(f'  Latest results: {latest}')
    except:
        pass
    db.close()
else:
    print('results.db: MISSING')

# Check result_tracker
print('\nResult tracker scripts:')
for f in ['result_tracker.py', 'result_tracker_v2.py', 'result_tracker_v3.py']:
    print(f'  {f}: {"EXISTS" if os.path.exists(f) else "MISSING"}')
