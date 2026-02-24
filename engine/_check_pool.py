import requests, json
TURSO_URL = 'https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io'
TURSO_TOKEN = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'
headers = {'Authorization': f'Bearer {TURSO_TOKEN}', 'Content-Type': 'application/json'}

# Check all dates
sql = "SELECT date, is_active, COUNT(*) as cnt FROM parlay_pool GROUP BY date, is_active ORDER BY date DESC LIMIT 20"
body = {'requests': [{'type': 'execute', 'stmt': {'sql': sql}}, {'type': 'close'}]}
r = requests.post(f'{TURSO_URL}/v2/pipeline', json=body, headers=headers, timeout=30)
data = r.json()
results = data['results'][0]['response']['result']
cols = [c['name'] for c in results['cols']]
for row in results['rows']:
    vals = [v['value'] for v in row]
    print(dict(zip(cols, vals)))

# Check dealt tickets
print("\n--- Recent dealt tickets ---")
sql2 = "SELECT dt.*, pp.picks_json, pp.leg_count, pp.sport_category FROM dealt_tickets dt JOIN parlay_pool pp ON pp.id = dt.pool_id ORDER BY dt.dealt_at DESC LIMIT 10"
body2 = {'requests': [{'type': 'execute', 'stmt': {'sql': sql2}}, {'type': 'close'}]}
r2 = requests.post(f'{TURSO_URL}/v2/pipeline', json=body2, headers=headers, timeout=30)
data2 = r2.json()
results2 = data2['results'][0]['response']['result']
cols2 = [c['name'] for c in results2['cols']]
for row in results2['rows']:
    vals = [v['value'] for v in row]
    print(dict(zip(cols2, vals)))
