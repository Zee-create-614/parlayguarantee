import requests
r = requests.get('https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores',
    params={'apiKey':'f3c9f91dc369f56dea1b523d3071e1f1','daysFrom':3,'dateFormat':'iso'}, timeout=20)
print(f"Status: {r.status_code}")
print(f"Remaining: {r.headers.get('x-requests-remaining','?')}")
data = r.json()
print(f"Total events: {len(data)}")
completed = [g for g in data if g.get('completed')]
print(f"Completed: {len(completed)}")
if completed:
    g = completed[0]
    print(f"Sample: {g['away_team']} @ {g['home_team']}, scores: {g.get('scores')}")
    print(f"Commence: {g.get('commence_time','?')[:10]}")
