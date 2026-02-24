import requests, json

url = 'https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io'
token = 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA'
h = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Get tables
r = requests.post(f'{url}/v2/pipeline', headers=h, json={'requests': [
    {'type': 'execute', 'stmt': {'sql': "SELECT name FROM sqlite_master WHERE type='table'"}},
    {'type': 'close'}
]})
print("Tables:", json.dumps(r.json(), indent=2)[:2000])

# Check for picks from today
r2 = requests.post(f'{url}/v2/pipeline', headers=h, json={'requests': [
    {'type': 'execute', 'stmt': {'sql': "SELECT COUNT(*) as cnt FROM picks WHERE game_date='2026-02-22'"}},
    {'type': 'close'}
]})
print("\nFeb 22 picks:", json.dumps(r2.json(), indent=2)[:1000])
