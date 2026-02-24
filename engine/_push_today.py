"""Push today's analyzed_games.json to Turso DB."""
import json, sys, requests
sys.stdout.reconfigure(encoding='utf-8')

TURSO_URL = "libsql://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA"

games = json.load(open('engine/analyzed_games.json'))
print(f"Loaded {len(games)} games from analyzed_games.json")

def turso_exec(stmts):
    url = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"
    body = {"requests": [{"type": "execute", "stmt": s} for s in stmts] + [{"type": "close"}]}
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(url, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

# Create table if needed
turso_exec([{
    "sql": """CREATE TABLE IF NOT EXISTS daily_picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_date TEXT NOT NULL,
        sport TEXT, home TEXT, away TEXT,
        spread REAL, spread_str TEXT, pick TEXT,
        cover_prob REAL, enhanced_prob REAL,
        ml_pick TEXT, ml_prob REAL,
        total_line REAL, ou_pick TEXT, ou_prob REAL,
        upset_score REAL, upset_flip INTEGER,
        game_time TEXT, commence_time TEXT,
        book_count INTEGER, raw_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )"""
}])

# Get today's date from the games
pick_date = games[0].get('game_date', '2026-02-23')
print(f"Pick date: {pick_date}")

# Delete existing picks for today
turso_exec([{"sql": "DELETE FROM daily_picks WHERE pick_date = ?", "args": [{"type": "text", "value": pick_date}]}])
print("Cleared old picks for today")

# Insert in batches of 5
batch = []
for g in games:
    raw = json.dumps(g)
    stmt = {
        "sql": """INSERT INTO daily_picks (pick_date, sport, home, away, spread, spread_str, pick,
                  cover_prob, enhanced_prob, ml_pick, ml_prob, total_line, ou_pick, ou_prob,
                  upset_score, upset_flip, game_time, commence_time, book_count, raw_json)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        "args": [
            {"type": "text", "value": pick_date},
            {"type": "text", "value": g.get('sport', '') or ''},
            {"type": "text", "value": g.get('home', '') or ''},
            {"type": "text", "value": g.get('away', '') or ''},
            {"type": "text", "value": str(g.get('spread', 0))},
            {"type": "text", "value": g.get('spread_str', '') or ''},
            {"type": "text", "value": g.get('pick', '') or ''},
            {"type": "text", "value": str(g.get('cover_prob', 0))},
            {"type": "text", "value": str(g.get('enhanced_prob', 0))},
            {"type": "text", "value": g.get('ml_pick', '') or ''},
            {"type": "text", "value": str(g.get('ml_prob', 0))},
            {"type": "text", "value": str(g.get('total_line', 0))},
            {"type": "text", "value": g.get('ou_pick', '') or ''},
            {"type": "text", "value": str(g.get('ou_prob', 0))},
            {"type": "text", "value": str(g.get('upset_score', 0))},
            {"type": "text", "value": str(1 if g.get('upset_flip') else 0)},
            {"type": "text", "value": g.get('game_time', '') or ''},
            {"type": "text", "value": g.get('commence_time', '') or ''},
            {"type": "text", "value": str(g.get('book_count', 0))},
            {"type": "text", "value": raw},
        ]
    }
    batch.append(stmt)
    if len(batch) >= 5:
        turso_exec(batch)
        batch = []

if batch:
    turso_exec(batch)

print(f"SUCCESS: Pushed {len(games)} picks to Turso for {pick_date}")

# Verify
result = turso_exec([{"sql": "SELECT COUNT(*) as cnt FROM daily_picks WHERE pick_date = ?", "args": [{"type": "text", "value": pick_date}]}])
print(f"Verification: {result}")
