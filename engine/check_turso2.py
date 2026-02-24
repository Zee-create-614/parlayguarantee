import requests, json

url = 'https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io'
token = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

for table in ['daily_picks', 'parlay_pool', 'pick_results']:
    r = requests.post(f'{url}/v2/pipeline', headers=h, json={'requests': [
        {'type': 'execute', 'stmt': {'sql': f"SELECT COUNT(*) as cnt FROM {table} WHERE game_date='2026-02-22'"}},
        {'type': 'close'}
    ]})
    data = r.json()
    try:
        cnt = data['results'][0]['response']['result']['rows'][0][0]['value']
        print(f"{table}: {cnt} rows for Feb 22")
    except:
        print(f"{table}: {json.dumps(data['results'][0], indent=2)[:300]}")
