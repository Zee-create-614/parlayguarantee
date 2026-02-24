import json, requests, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

abbr_map = {
    'OKC Thunder': 'OKC', 'CLE Cavaliers': 'CLE', 'BKN Nets': 'BKN', 'ATL Hawks': 'ATL',
    'MIL Bucks': 'MIL', 'TOR Raptors': 'TOR', 'DEN Nuggets': 'DEN', 'GS Warriors': 'GS',
    'DAL Mavericks': 'DAL', 'IND Pacers': 'IND', 'WAS Wizards': 'WSH', 'CHA Hornets': 'CHA',
    'LA Lakers': 'LAL', 'BOS Celtics': 'BOS', 'PHI 76ers': 'PHI', 'MIN Timberwolves': 'MIN',
    'NY Knicks': 'NY', 'CHI Bulls': 'CHI', 'PHO Suns': 'PHX', 'POR Trail Blazers': 'POR',
    'ORL Magic': 'ORL', 'LA Clippers': 'LAC',
}

# NBA scores
r = requests.get('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20260222', timeout=15)
nba_scores = {}
for event in r.json().get('events', []):
    c = event['competitions'][0]
    if not c.get('status',{}).get('type',{}).get('completed'): continue
    teams = c['competitors']
    home = [t for t in teams if t['homeAway']=='home'][0]
    away = [t for t in teams if t['homeAway']=='away'][0]
    h_abbr = home['team']['abbreviation']
    a_abbr = away['team']['abbreviation']
    nba_scores[h_abbr] = {'home': h_abbr, 'away': a_abbr, 'hs': int(home['score']), 'as': int(away['score'])}
    nba_scores[a_abbr] = nba_scores[h_abbr]

# Score NBA picks
with open('picks_2026-02-22/nba_spread_picks.json') as f:
    nba_picks = json.load(f)

print("=== NBA SPREAD RESULTS (Feb 22) ===")
w, l = 0, 0
for p in nba_picks:
    team = p['predicted_winner']
    spread = p['pick_spread']  # this is the spread for the picked team
    conf = round(p['confidence'] * 100)
    upset = p.get('is_upset_play', False)
    
    abbr = abbr_map.get(team, team)
    g = nba_scores.get(abbr)
    if not g:
        print(f"  ? {team} ({spread:+g}) {conf}% — no score")
        continue
    
    if abbr == g['home']:
        margin = g['hs'] - g['as']
    else:
        margin = g['as'] - g['hs']
    
    # covered = margin + spread > 0 (spread is positive for dogs, negative for favs)
    covered = margin + spread > 0
    tag = "U" if upset else ""
    icon = "HIT" if covered else "MISS"
    if covered: w += 1
    else: l += 1
    
    actual = f"{g['away']}:{nba_scores[g['away']]['as'] if g['away'] in nba_scores else '?'} vs {g['home']}:{g['hs']}"
    print(f"  {'W' if covered else 'L'} | {team} ({spread:+g}) | {conf}% {tag} | margin: {margin:+d}")

pct = round(w/(w+l)*100) if w+l else 0
print(f"\nNBA: {w}-{l} ({pct}%)")

# NCAAB - ESPN only returns ~top games, try anyway
r2 = requests.get('https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260222&limit=200', timeout=15)
cbb_games = []
for event in r2.json().get('events', []):
    c = event['competitions'][0]
    if not c.get('status',{}).get('type',{}).get('completed'): continue
    teams = c['competitors']
    home = [t for t in teams if t['homeAway']=='home'][0]
    away = [t for t in teams if t['homeAway']=='away'][0]
    cbb_games.append({
        'home': home['team'].get('displayName',''),
        'away': away['team'].get('displayName',''),
        'hs': int(home['score']), 'as': int(away['score'])
    })

print(f"\n=== NCAAB SPREAD RESULTS (Feb 22) ===")
print(f"(ESPN returned {len(cbb_games)} completed games)")

with open('picks_2026-02-22/ncaab_spread_picks.json') as f:
    ncaab_picks = json.load(f)

cw, cl, miss = 0, 0, 0
for p in ncaab_picks:
    team = p['predicted_winner']
    spread = p['pick_spread']
    conf = round(p['confidence'] * 100)
    upset = p.get('is_upset_play', False)
    
    matched = None
    team_l = team.lower()
    for g in cbb_games:
        if team_l in g['home'].lower() or team_l in g['away'].lower():
            matched = g
            break
    if not matched:
        for g in cbb_games:
            for word in team_l.split():
                if len(word) > 3 and (word in g['home'].lower() or word in g['away'].lower()):
                    matched = g
                    break
            if matched: break
    
    if not matched:
        miss += 1
        continue
    
    is_home = team_l in matched['home'].lower() or any(w in matched['home'].lower() for w in team_l.split() if len(w)>3)
    margin = (matched['hs'] - matched['as']) if is_home else (matched['as'] - matched['hs'])
    covered = margin + spread > 0
    tag = "U" if upset else ""
    if covered: cw += 1
    else: cl += 1
    print(f"  {'W' if covered else 'L'} | {team} ({spread:+g}) | {conf}% {tag} | margin: {margin:+d}")

if miss:
    print(f"  ({miss} games not found on ESPN — small school games not tracked)")
pct2 = round(cw/(cw+cl)*100) if cw+cl else 0
print(f"\nNCAAB scored: {cw}-{cl} ({pct2}%)")

tw, tl = w+cw, l+cl
pct3 = round(tw/(tw+tl)*100) if tw+tl else 0
print(f"\n{'='*40}")
print(f"OVERALL: {tw}-{tl} ({pct3}%)")
print(f"(+{miss} NCAAB unscored)")
