import sys, json, os, sqlite3
sys.stdout.reconfigure(encoding='utf-8')

# analyzed_games.json
if os.path.exists('analyzed_games.json'):
    data = json.load(open('analyzed_games.json'))
    print(f'analyzed_games.json: {len(data)} games, date={data[0].get("game_date","?") if isinstance(data,list) and data else "?"}')

# picks_output.json
if os.path.exists('picks_output.json'):
    data = json.load(open('picks_output.json'))
    print(f'picks_output.json: date={data.get("date","?")}, total_games={data.get("total_games",0)}')
    print(f'  Keys: {list(data.keys())}')

# all_picks.json in today's folder
fp = 'picks_2026-02-22/all_picks.json'
if os.path.exists(fp):
    data = json.load(open(fp))
    print(f'\npicks_2026-02-22/all_picks.json: {data.get("total_games",0)} games')
    games = data.get('all_games', [])
    sports = {}
    for g in games:
        s = g.get('sport', '?')
        sports[s] = sports.get(s, 0) + 1
    print(f'  By sport: {sports}')
    # Check fields needed for user parlays
    if games:
        g = games[0]
        print(f'  Sample fields: {list(g.keys())[:15]}')

# results.db
if os.path.exists('results.db'):
    db = sqlite3.connect('results.db')
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f'\nresults.db tables: {[t[0] for t in tables]}')
    for t in tables:
        c = db.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()
        print(f'  {t[0]}: {c[0]} rows')
    db.close()
else:
    print('\nresults.db: MISSING')
