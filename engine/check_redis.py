import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

URL = 'https://vocal-crawdad-5028.upstash.io'
TOKEN = 'AROkAAImcDFiNGU4YjJlYjI3NjM0ODEzYmUwNmY3ZjE1MzgzMjI5MnAxNTAyOA'

def cmd(*args):
    r = requests.post(URL, headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}, json=list(args))
    return r.json().get('result')

keys = cmd('KEYS', '*')
print(f'All keys: {keys}')
print(f'users:all: {cmd("ZRANGE", "users:all", "0", "-1")}')
print(f'users:recent: {cmd("LRANGE", "users:recent", "0", "10")}')
