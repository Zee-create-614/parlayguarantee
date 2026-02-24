"""Score ALL Feb 20 picks: NBA + NCAAB spreads + O/U"""
import json, requests, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get_espn_scores(sport_path, dates):
    results = {}
    for dt in dates:
        r = requests.get(f'https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard?dates={dt}&limit=200', timeout=15)
        for ev in r.json().get('events', []):
            comp = ev['competitions'][0]
            if comp['status']['type']['completed']:
                teams = {}
                for t in comp['competitors']:
                    teams[t['homeAway']] = {'name': t['team']['displayName'], 'score': int(t['score'])}
                if 'home' in teams and 'away' in teams:
                    total = teams['home']['score'] + teams['away']['score']
                    entry = {'home': teams['home'], 'away': teams['away'], 'total': total}
                    results[teams['home']['name']] = entry
                    results[teams['away']['name']] = entry
    return results

def score_picks(picks, results, label):
    ml_w, ml_t, sp_w, ou_w, ou_t = 0, 0, 0, 0, 0
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    for g in picks:
        home = g.get('home', g.get('home_team', ''))
        away = g.get('away', g.get('away_team', ''))
        pick = g.get('pick', g.get('predicted_winner', ''))
        spread = g.get('spread', 0)
        total_line = g.get('total')
        conf = g.get('win_prob', g.get('confidence', 0))
        
        match = results.get(home) or results.get(away)
        if not match:
            continue
        
        h_score = match['home']['score']
        a_score = match['away']['score']
        actual_total = match['total']
        winner = match['home']['name'] if h_score > a_score else match['away']['name']
        margin = h_score - a_score  # positive = home won
        
        ml_t += 1
        ml_hit = (pick == winner)
        if ml_hit: ml_w += 1
        
        # Spread cover check
        # spread > 0 means home is underdog (getting points)
        # Our pick's perspective: did the picked team cover?
        if pick == home:
            # We picked home. Home spread = +spread (getting points) or -spread (giving)
            cover_margin = margin + spread  # if spread positive, home gets points
            sp_hit = cover_margin > 0
        else:
            # We picked away. Away margin = -margin
            cover_margin = -margin - spread  # away perspective
            sp_hit = cover_margin > 0
        if sp_hit: sp_w += 1
        
        ml_sym = 'W' if ml_hit else 'L'
        sp_sym = 'W' if sp_hit else 'L'
        
        line = f"  ML:{ml_sym} SP:{sp_sym} | {away} @ {home}: {a_score}-{h_score} | Pick: {pick} ({conf:.0%})"
        
        if total_line and total_line > 0:
            ou_t += 1
            ou_result = 'OVER' if actual_total > total_line else 'UNDER'
            line += f" | O/U: {actual_total} vs {total_line} = {ou_result}"
        
        print(line)
    
    if ml_t:
        print(f"\n  ML: {ml_w}/{ml_t} ({100*ml_w/ml_t:.1f}%)")
        print(f"  Spread: {sp_w}/{ml_t} ({100*sp_w/ml_t:.1f}%)")
        if ou_t:
            print(f"  O/U games tracked: {ou_t} (no pick direction yet)")
    else:
        print("  No matched games found")
    
    return ml_w, ml_t, sp_w, ou_t

# Load picks
with open('history/analyzed_games_2026-02-20.json') as f:
    nba = json.load(f)
with open('history/ncaab_analyzed_games_2026-02-20.json') as f:
    ncaab = json.load(f)

# Fetch scores
nba_scores = get_espn_scores('basketball/nba', ['20260220', '20260221'])
ncaab_scores = get_espn_scores('basketball/mens-college-basketball', ['20260220', '20260221'])

print(f"ESPN NBA completed: {len(nba_scores)//2}")
print(f"ESPN NCAAB completed: {len(ncaab_scores)//2}")

nba_r = score_picks(nba, nba_scores, "NBA PICKS — Feb 20, 2026")
ncaab_r = score_picks(ncaab, ncaab_scores, "NCAAB PICKS — Feb 20, 2026")

print(f"\n{'='*60}")
print(f"  COMBINED TOTALS")
print(f"{'='*60}")
total_ml = nba_r[0] + ncaab_r[0]
total_games = nba_r[1] + ncaab_r[1]
total_sp = nba_r[2] + ncaab_r[2]
print(f"  ML: {total_ml}/{total_games} ({100*total_ml/total_games:.1f}%)" if total_games else "")
print(f"  Spread: {total_sp}/{total_games} ({100*total_sp/total_games:.1f}%)" if total_games else "")
