import requests, json, sys
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8')

URL = 'https://vocal-crawdad-5028.upstash.io'
TOKEN = 'AROkAAImcDFiNGU4YjJlYjI3NjM0ODEzYmUwNmY3ZjE1MzgzMjI5MnAxNTAyOA'

def cmd(*args):
    r = requests.post(URL, headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}, json=list(args))
    return r.json().get('result')

email = 'mybotzee@gmail.com'
now = datetime.now(timezone.utc).isoformat()

user = {
    'email': email,
    'fullName': 'Josh Smith',
    'phone': '',
    'address': None,
    'dob': '1985-02-28',
    'referralCode': 'JOSH0001',
    'referredBy': None,
    'freePackUsed': False,
    'referralCredits': 0,
    'createdAt': '2026-02-17T00:00:00Z',  # original signup ~Feb 17
    'lastLogin': now,
    'purchaseCount': 0,
}

# Save user
cmd('SET', f'user:{email}', json.dumps(user))
# Add to sorted set
cmd('ZADD', 'users:all', str(int(datetime(2026, 2, 17, tzinfo=timezone.utc).timestamp())), email)
# Add to recent
cmd('LPUSH', 'users:recent', json.dumps({'email': email, 'name': 'Josh Smith', 'at': '2026-02-17T00:00:00Z'}))

print(f'Seeded {email} into Upstash')
print(f'Verify: {cmd("GET", f"user:{email}")}')
print(f'users:all: {cmd("ZRANGE", "users:all", "0", "-1")}')
