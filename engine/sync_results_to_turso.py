"""
Sync local results.db to Turso cloud DB.
Run after scoring to ensure Vercel can read results.
"""
import sys, json, sqlite3, requests, os
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

ENGINE_DIR = Path(__file__).parent

TURSO_URL = "https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA"

headers = {'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'}

def execute(statements):
    reqs = []
    for sql, args in statements:
        stmt = {'sql': sql}
        if args:
            stmt['args'] = [{'type': 'text', 'value': str(a)} if a is not None else {'type': 'null'} for a in args]
        reqs.append({'type': 'execute', 'stmt': stmt})
    reqs.append({'type': 'close'})
    r = requests.post(f'{TURSO_URL}/v2/pipeline', headers=headers, json={'requests': reqs})
    return r.json()

def query(sql):
    r = requests.post(f'{TURSO_URL}/v2/pipeline', headers=headers, json={
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

def sync():
    db_path = ENGINE_DIR / 'results.db'
    if not db_path.exists():
        print("No local results.db found")
        return

    db = sqlite3.connect(str(db_path))

    # Ensure Turso tables exist
    execute([
        ("""CREATE TABLE IF NOT EXISTS pick_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, product TEXT NOT NULL, pick_number INTEGER,
            type TEXT, predicted_winner TEXT, actual_winner TEXT,
            correct INTEGER, confidence REAL, odds TEXT,
            game_home TEXT, game_away TEXT,
            home_score INTEGER, away_score INTEGER
        )""", None),
        ("""CREATE TABLE IF NOT EXISTS daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, product TEXT NOT NULL,
            total_picks INTEGER, correct_picks INTEGER, accuracy REAL,
            parlays_hit INTEGER, total_parlays INTEGER, deposit_kept INTEGER
        )""", None),
    ])

    # Get existing dates in Turso to avoid duplicates
    existing_dates = set()
    rows = query("SELECT DISTINCT date FROM pick_results")
    for r in rows:
        existing_dates.add(r[0])

    # Sync pick_results
    local_results = db.execute(
        "SELECT date, product, pick_number, type, predicted_winner, actual_winner, correct, confidence, odds, game_home, game_away, home_score, away_score FROM pick_results"
    ).fetchall()

    new_results = [r for r in local_results if r[0] not in existing_dates]
    if new_results:
        print(f"Pushing {len(new_results)} new pick results...")
        batch = []
        for r in new_results:
            sql = """INSERT INTO pick_results (date, product, pick_number, type, predicted_winner, actual_winner, correct, confidence, odds, game_home, game_away, home_score, away_score)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            batch.append((sql, list(r)))
        execute(batch)
        print("  Done!")
    else:
        print("Pick results already synced")

    # Sync daily_summaries
    existing_sum_dates = set()
    rows = query("SELECT DISTINCT date FROM daily_summaries")
    for r in rows:
        existing_sum_dates.add(r[0])

    local_sums = db.execute(
        "SELECT date, product, total_picks, correct_picks, accuracy, parlays_hit, total_parlays, deposit_kept FROM daily_summaries"
    ).fetchall()

    new_sums = [s for s in local_sums if s[0] not in existing_sum_dates]
    if new_sums:
        print(f"Pushing {len(new_sums)} new daily summaries...")
        batch = []
        for s in new_sums:
            sql = """INSERT INTO daily_summaries (date, product, total_picks, correct_picks, accuracy, parlays_hit, total_parlays, deposit_kept)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
            batch.append((sql, list(s)))
        execute(batch)
        print("  Done!")
    else:
        print("Daily summaries already synced")

    # Also sync scorecard JSON files for today
    for f in ENGINE_DIR.glob('results_*_scorecard.json'):
        print(f"Found scorecard: {f.name}")

    db.close()

    # Verify
    rows = query("SELECT COUNT(*) FROM pick_results")
    print(f"\nTurso pick_results: {rows[0][0] if rows else 0}")
    rows = query("SELECT COUNT(*) FROM daily_summaries")
    print(f"Turso daily_summaries: {rows[0][0] if rows else 0}")

if __name__ == '__main__':
    sync()
