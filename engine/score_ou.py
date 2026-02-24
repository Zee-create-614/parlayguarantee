import requests, json, sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Fetch Feb 22 NBA scores
resp = requests.get('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard', params={'dates': '20260222'}, timeout=30)
data = resp.json()

scores = {}
for ev in data.get('events', []):
    comp = ev['competitions'][0]
    status = comp['status']['type']['name']
    teams = comp['competitors']
    home = [t for t in teams if t['homeAway']=='home'][0]
    away = [t for t in teams if t['homeAway']=='away'][0]
    h_name = home['team']['displayName']
    a_name = away['team']['displayName']
    h_score = int(home['score'])
    a_score = int(away['score'])
    total = h_score + a_score
    scores[h_name.lower()] = {'home': h_name, 'away': a_name, 'h': h_score, 'a': a_score, 'total': total, 'status': status}
    print(f"{a_name} @ {h_name}: {a_score}-{h_score} (Total: {total}) [{status}]")

# Load O/U picks
with open('picks_2026-02-22/nba_ou_picks.json') as f:
    picks = json.load(f)

# Match and score
team_map = {
    'okc thunder': 'oklahoma city thunder',
    'gs warriors': 'golden state warriors',
    'atl hawks': 'atlanta hawks',
    'mil bucks': 'milwaukee bucks',
    'ind pacers': 'indiana pacers',
    'was wizards': 'washington wizards',
    'la lakers': 'los angeles lakers',
    'min timberwolves': 'minnesota timberwolves',
    'pho suns': 'phoenix suns',
    'chi bulls': 'chicago bulls',
    'la clippers': 'la clippers',
    'cle cavaliers': 'cleveland cavaliers',
    'den nuggets': 'denver nuggets',
    'bkn nets': 'brooklyn nets',
    'tor raptors': 'toronto raptors',
    'dal mavericks': 'dallas mavericks',
    'cha hornets': 'charlotte hornets',
    'bos celtics': 'boston celtics',
    'phi 76ers': 'philadelphia 76ers',
    'por trail blazers': 'portland trail blazers',
    'ny knicks': 'new york knicks',
    'orl magic': 'orlando magic',
}

print("\n===== O/U RESULTS =====")
correct = 0
total_picks = 0
for p in picks:
    full_home = p['home_team'].lower()
    mapped = team_map.get(full_home, full_home)
    
    matched = scores.get(mapped, None)
    
    if not matched:
        print(f"  NO MATCH: {p['home_team']} vs {p['away_team']}")
        continue
    
    if matched['status'] != 'STATUS_FINAL':
        print(f"  NOT FINAL: {matched['home']} vs {matched['away']} ({matched['status']})")
        continue
    
    actual_total = matched['total']
    line = p['total']
    pick = p['ou_pick']
    conf = p['confidence']
    
    if pick == 'Over':
        hit = actual_total > line
    else:
        hit = actual_total < line
    
    if actual_total == line:
        result = "PUSH"
    elif hit:
        result = "HIT"
        correct += 1
    else:
        result = "MISS"
    
    total_picks += 1
    print(f"  {matched['away']} @ {matched['home']}: {matched['a']}-{matched['h']} = {actual_total} | Line: {pick} {line} | Conf: {conf:.0%} | {result}")

print(f"\n===== TOTAL: {correct}/{total_picks} ({correct/total_picks*100:.0f}%) =====")
