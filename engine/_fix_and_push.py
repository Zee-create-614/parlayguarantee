"""Fix all_picks.json from morning's correct data and re-push to Turso."""
import json, sys, requests
sys.stdout.reconfigure(encoding='utf-8')

# Load correct morning picks
ncaab_sp = json.load(open('picks_2026-02-22/ncaab_spread_picks.json'))
nba_sp = json.load(open('picks_2026-02-22/nba_spread_picks.json'))
ncaab_ou = json.load(open('picks_2026-02-22/ncaab_ou_picks.json'))
nba_ou = json.load(open('picks_2026-02-22/nba_ou_picks.json'))

print(f"Morning picks: {len(ncaab_sp)} NCAAB spread, {len(nba_sp)} NBA spread")
print(f"               {len(ncaab_ou)} NCAAB O/U, {len(nba_ou)} NBA O/U")

# Merge spread + OU data per game
all_games = []
for g in ncaab_sp + nba_sp:
    game = dict(g)
    # Find matching OU pick
    ou_list = ncaab_ou if g['sport'] == 'NCAAB' else nba_ou
    for ou in ou_list:
        if ou.get('home_team') == g.get('home_team') and ou.get('away_team') == g.get('away_team'):
            game['total_line'] = ou.get('total')
            game['ou_pick'] = ou.get('ou_pick', ou.get('predicted_ou', ''))
            game['ou_prob'] = ou.get('ou_confidence', ou.get('confidence', 0))
            break
    # Map fields for Turso
    game['home'] = game.get('home_team', '')
    game['away'] = game.get('away_team', '')
    game['spread'] = game.get('pick_spread', game.get('spread_away', 0))
    game['spread_str'] = f"{game.get('predicted_winner','')} {game.get('pick_spread','')}"
    game['pick'] = game.get('predicted_winner', '')
    game['cover_prob'] = game.get('confidence', 0)
    game['enhanced_prob'] = game.get('confidence', 0)
    game['upset_score'] = game.get('upset_composite_score', 0)
    game['upset_flip'] = game.get('is_upset_play', False)
    all_games.append(game)

# Rebuild all_picks.json
all_picks = {
    'date': '2026-02-22',
    'generated_at': '2026-02-22T07:48:00-05:00',
    'total_games': len(all_games),
    'nba_games': len(nba_sp),
    'ncaab_games': len(ncaab_sp),
    'all_games': all_games,
    'tiers': {},
    'ou_tiers': {},
    'ml_tiers': {},
}
json.dump(all_picks, open('picks_2026-02-22/all_picks.json', 'w'), indent=2)
print(f"\nFixed all_picks.json: {len(all_games)} games")

# Now push to Turso
URL = 'https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io'
TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'
headers = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

def execute(statements):
    reqs = []
    for sql, args in statements:
        stmt = {'sql': sql}
        if args:
            stmt['args'] = [{'type': 'text', 'value': str(a)} if a is not None else {'type': 'null'} for a in args]
        reqs.append({'type': 'execute', 'stmt': stmt})
    reqs.append({'type': 'close'})
    r = requests.post(f'{URL}/v2/pipeline', headers=headers, json={'requests': reqs})
    return r.json()

# Delete today's bad picks
print("\nClearing bad Turso picks...")
result = execute([("DELETE FROM daily_picks WHERE pick_date='2026-02-22'", None)])
print(f"  Deleted old rows")

# Insert correct picks
batch = []
for g in all_games:
    raw = json.dumps(g)
    sql = """INSERT INTO daily_picks (pick_date, sport, home, away, spread, spread_str, pick, cover_prob, enhanced_prob,
             ml_pick, ml_prob, total_line, ou_pick, ou_prob, upset_score, upset_flip, game_time, commence_time, book_count, raw_json)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    args = [
        '2026-02-22', g.get('sport',''), g.get('home',''), g.get('away',''),
        g.get('spread'), g.get('spread_str',''), g.get('pick',''),
        g.get('cover_prob'), g.get('enhanced_prob'),
        '', None,
        g.get('total_line'), g.get('ou_pick',''), g.get('ou_prob'),
        g.get('upset_score',0), 1 if g.get('upset_flip') else 0,
        '', g.get('commence_time',''),
        0, raw
    ]
    batch.append((sql, args))

result = execute(batch)
errors = [r for r in result.get('results',[]) if 'error' in r]
if errors:
    print(f"Errors: {errors[:3]}")
else:
    print(f"Inserted {len(all_games)} correct picks!")

# Verify
def query(sql):
    r = requests.post(f'{URL}/v2/pipeline', headers=headers, json={
        'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]
    })
    data = r.json()
    if 'results' in data and data['results']:
        res = data['results'][0].get('response', {}).get('result', {})
        return [[c.get('value') for c in row] for row in res.get('rows', [])]
    return []

rows = query("SELECT sport, COUNT(*), ROUND(AVG(CAST(cover_prob AS REAL)),3) FROM daily_picks WHERE pick_date='2026-02-22' GROUP BY sport")
print("\nVerification:")
for r in rows:
    print(f"  {r[0]}: {r[1]} picks, avg confidence: {r[2]}")

# Show Kansas specifically
rows = query("SELECT away, home, cover_prob, upset_score FROM daily_picks WHERE pick_date='2026-02-22' AND (home LIKE '%Kansas%' OR away LIKE '%Kansas%')")
for r in rows:
    print(f"  Kansas game: {r[0]} @ {r[1]} | conf={r[2]} | upset={r[3]}")
