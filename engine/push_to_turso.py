import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

URL = 'https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io'
TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'

headers = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

def execute(statements):
    """Execute multiple SQL statements via pipeline API"""
    reqs = []
    for sql, args in statements:
        stmt = {'sql': sql}
        if args:
            stmt['args'] = [{'type': 'text', 'value': str(a)} if a is not None else {'type': 'null'} for a in args]
        reqs.append({'type': 'execute', 'stmt': stmt})
    reqs.append({'type': 'close'})
    r = requests.post(f'{URL}/v2/pipeline', headers=headers, json={'requests': reqs})
    return r.json()

# 1. Create tables
print("Creating tables...")
create_stmts = [
    ("""CREATE TABLE IF NOT EXISTS daily_picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_date TEXT NOT NULL,
        sport TEXT NOT NULL,
        home TEXT NOT NULL,
        away TEXT NOT NULL,
        spread REAL,
        spread_str TEXT,
        pick TEXT,
        cover_prob REAL,
        enhanced_prob REAL,
        ml_pick TEXT,
        ml_prob REAL,
        total_line REAL,
        ou_pick TEXT,
        ou_prob REAL,
        upset_score REAL,
        upset_flip INTEGER DEFAULT 0,
        game_time TEXT,
        commence_time TEXT,
        book_count INTEGER,
        raw_json TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""", None),
    ("""CREATE TABLE IF NOT EXISTS pick_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        product TEXT NOT NULL,
        pick_number INTEGER,
        type TEXT,
        predicted_winner TEXT,
        actual_winner TEXT,
        correct INTEGER,
        confidence REAL,
        odds TEXT,
        game_home TEXT,
        game_away TEXT,
        home_score INTEGER,
        away_score INTEGER
    )""", None),
    ("""CREATE TABLE IF NOT EXISTS daily_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        product TEXT NOT NULL,
        total_picks INTEGER,
        correct_picks INTEGER,
        accuracy REAL,
        parlays_hit INTEGER,
        total_parlays INTEGER,
        deposit_kept INTEGER
    )""", None),
    ("CREATE INDEX IF NOT EXISTS idx_picks_date ON daily_picks(pick_date)", None),
    ("CREATE INDEX IF NOT EXISTS idx_results_date ON pick_results(date)", None),
]
result = execute(create_stmts)
print(f"Tables created. Response has {len(result.get('results',[]))} results")

# 2. Load today's picks
picks_data = json.load(open('picks_2026-02-22/all_picks.json'))
games = picks_data.get('all_games', [])
print(f"\nLoading {len(games)} games to Turso...")

# Insert in batches of 10
batch = []
for g in games:
    raw = json.dumps(g)
    sql = """INSERT INTO daily_picks (pick_date, sport, home, away, spread, spread_str, pick, cover_prob, enhanced_prob, 
             ml_pick, ml_prob, total_line, ou_pick, ou_prob, upset_score, upset_flip, game_time, commence_time, book_count, raw_json)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    args = [
        '2026-02-22', g.get('sport',''), g.get('home',''), g.get('away',''),
        g.get('spread'), g.get('spread_str',''), g.get('pick',''),
        g.get('cover_prob'), g.get('enhanced_prob'),
        g.get('ml_pick',''), g.get('ml_prob'),
        g.get('total_line'), g.get('ou_pick',''), g.get('ou_prob'),
        g.get('upset_score',0), 1 if g.get('upset_flip') else 0,
        g.get('game_time',''), g.get('commence_time',''),
        g.get('book_count',0), raw
    ]
    batch.append((sql, args))

# Execute all inserts
result = execute(batch)
errors = [r for r in result.get('results',[]) if 'error' in r]
if errors:
    print(f"Errors: {errors[:3]}")
else:
    print(f"All {len(games)} games inserted successfully!")

# 3. Also push historical results from local results.db
import sqlite3, os
if os.path.exists('results.db'):
    db = sqlite3.connect('results.db')
    
    # Push pick_results
    local_results = db.execute("SELECT date, product, pick_number, type, predicted_winner, actual_winner, correct, confidence, odds, game_home, game_away, home_score, away_score FROM pick_results").fetchall()
    if local_results:
        print(f"\nPushing {len(local_results)} pick results...")
        batch = []
        for r in local_results:
            sql = """INSERT INTO pick_results (date, product, pick_number, type, predicted_winner, actual_winner, correct, confidence, odds, game_home, game_away, home_score, away_score)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            batch.append((sql, list(r)))
        result = execute(batch)
        errors = [r for r in result.get('results',[]) if 'error' in r]
        print(f"  {'Errors: ' + str(errors[:2]) if errors else 'Done!'}")
    
    # Push daily_summaries
    local_sums = db.execute("SELECT date, product, total_picks, correct_picks, accuracy, parlays_hit, total_parlays, deposit_kept FROM daily_summaries").fetchall()
    if local_sums:
        print(f"Pushing {len(local_sums)} daily summaries...")
        batch = []
        for s in local_sums:
            sql = """INSERT INTO daily_summaries (date, product, total_picks, correct_picks, accuracy, parlays_hit, total_parlays, deposit_kept)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            batch.append((sql, list(s)))
        result = execute(batch)
        errors = [r for r in result.get('results',[]) if 'error' in r]
        print(f"  {'Errors: ' + str(errors[:2]) if errors else 'Done!'}")
    
    db.close()

# 4. Verify
def query(sql):
    r = requests.post(f'{URL}/v2/pipeline', headers=headers, json={
        'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]
    })
    data = r.json()
    if 'results' in data and data['results']:
        res = data['results'][0].get('response', {}).get('result', {})
        rows = []
        for row in res.get('rows', []):
            rows.append([c.get('value') for c in row])
        return rows
    return []

print("\n=== VERIFICATION ===")
rows = query("SELECT COUNT(*) FROM daily_picks WHERE pick_date='2026-02-22'")
print(f"Turso picks for 2026-02-22: {rows[0][0] if rows else 0}")
rows = query("SELECT sport, COUNT(*) FROM daily_picks WHERE pick_date='2026-02-22' GROUP BY sport")
for r in rows:
    print(f"  {r[0]}: {r[1]}")
rows = query("SELECT COUNT(*) FROM pick_results")
print(f"Pick results: {rows[0][0] if rows else 0}")
rows = query("SELECT COUNT(*) FROM daily_summaries")
print(f"Daily summaries: {rows[0][0] if rows else 0}")
