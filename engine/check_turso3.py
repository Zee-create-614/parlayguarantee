import requests, json

url = 'https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io'
token = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Get schema for key tables
for table in ['daily_picks', 'parlay_pool', 'pick_results']:
    r = requests.post(f'{url}/v2/pipeline', headers=h, json={'requests': [
        {'type': 'execute', 'stmt': {'sql': f"PRAGMA table_info({table})"}},
        {'type': 'close'}
    ]})
    cols = r.json()['results'][0]['response']['result']['rows']
    col_names = [c[1]['value'] for c in cols]
    print(f"{table}: {col_names}")

# Get counts
r = requests.post(f'{url}/v2/pipeline', headers=h, json={'requests': [
    {'type': 'execute', 'stmt': {'sql': "SELECT COUNT(*) FROM daily_picks"}},
    {'type': 'execute', 'stmt': {'sql': "SELECT * FROM daily_picks ORDER BY id DESC LIMIT 2"}},
    {'type': 'close'}
]})
res = r.json()['results']
print(f"\ndaily_picks total: {res[0]['response']['result']['rows'][0][0]['value']}")
rows = res[1]['response']['result']['rows']
cols = res[1]['response']['result']['cols']
print(f"Columns: {[c['name'] for c in cols]}")
for row in rows:
    print([v.get('value','NULL') for v in row])
