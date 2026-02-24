"""Quick scorer — checks all pick dates against ESPN actual results."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json, requests
from datetime import date, timedelta
from pathlib import Path

ENGINE = Path(__file__).parent

def fetch_espn(dt, sport='nba'):
    league = 'nba' if sport == 'nba' else 'mens-college-basketball'
    extra = '&groups=50&limit=500' if sport == 'ncaab' else ''
    url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard?dates={dt.strftime("%Y%m%d")}{extra}'
    r = requests.get(url, timeout=15)
    scores = {}
    for ev in r.json().get('events', []):
        if ev.get('status',{}).get('type',{}).get('name') != 'STATUS_FINAL':
            continue
        comps = ev['competitions'][0]['competitors']
        home = away = None
        for c in comps:
            if c['homeAway'] == 'home': home = c
            else: away = c
        if not home or not away: continue
        h_name = home['team']['displayName']
        a_name = away['team']['displayName']
        h_score = int(home['score'])
        a_score = int(away['score'])
        scores[f'{a_name} @ {h_name}'] = {
            'home': h_name, 'away': a_name,
            'h_score': h_score, 'a_score': a_score,
            'winner': h_name if h_score > a_score else a_name,
            'margin': h_score - a_score
        }
    return scores

def fuzzy(a, b):
    if not a or not b: return False
    if a.lower() == b.lower(): return True
    if a.lower() in b.lower() or b.lower() in a.lower(): return True
    al = a.lower().split(); bl = b.lower().split()
    if al and bl and al[-1] == bl[-1]: return True
    return False

def find(home, away, scores):
    for k, v in scores.items():
        if fuzzy(home, v['home']) and fuzzy(away, v['away']):
            return v
    return None

GRAND = {'ml_h': 0, 'ml_t': 0, 'sp_h': 0, 'sp_t': 0}

for pick_date in ['2026-02-21', '2026-02-22', '2026-02-23']:
    pdir = ENGINE / f'picks_{pick_date}'
    if not pdir.exists():
        continue
    
    print(f'\n{"="*60}')
    print(f'  PICKS: {pick_date}')
    print(f'{"="*60}')
    
    for sport, label in [('nba', 'NBA'), ('ncaab', 'NCAAB')]:
        sf = pdir / f'{sport}_spread_picks.json'
        if not sf.exists():
            continue
        picks = json.loads(sf.read_text(encoding='utf-8'))
        
        d = date.fromisoformat(pick_date)
        scores = {}
        for offset in [0, 1]:
            scores.update(fetch_espn(d + timedelta(days=offset), sport))
        
        hits = misses = no_match = 0
        sp_hits = sp_misses = 0
        results = []
        
        for p in picks:
            actual = find(p['home_team'], p['away_team'], scores)
            if not actual:
                no_match += 1
                continue
            
            ml_hit = fuzzy(p['predicted_winner'], actual['winner'])
            if ml_hit: hits += 1
            else: misses += 1
            
            spread = p.get('pick_spread', p.get('spread'))
            if spread is not None:
                margin = actual['margin']
                if fuzzy(p['predicted_winner'], actual['home']):
                    covered = (margin + spread) > 0
                else:
                    covered = (-margin + spread) > 0
                if covered: sp_hits += 1
                else: sp_misses += 1
            
            emoji = '\u2705' if ml_hit else '\u274c'
            conf = p.get('confidence', 0)
            results.append((conf, emoji, p['away_team'], p['home_team'], p['predicted_winner'], actual['winner'], f"{actual['a_score']}-{actual['h_score']}"))
        
        results.sort(key=lambda x: -x[0])
        total = hits + misses
        stotal = sp_hits + sp_misses
        GRAND['ml_h'] += hits; GRAND['ml_t'] += total
        GRAND['sp_h'] += sp_hits; GRAND['sp_t'] += stotal
        
        ml_pct = round(hits/total*100,1) if total else 0
        sp_pct = round(sp_hits/stotal*100,1) if stotal else 0
        print(f'\n  {label} ML: {hits}/{total} ({ml_pct}%)')
        print(f'  {label} Spread: {sp_hits}/{stotal} ({sp_pct}%)')
        if no_match: print(f'  ({no_match} games not found/not final)')
        for conf, emoji, away, home, pred, actual_w, score in results:
            print(f'    {emoji} {away} @ {home} | pick: {pred} | winner: {actual_w} | {score} | conf: {conf:.0%}')

print(f'\n{"="*60}')
print(f'  GRAND TOTALS (all dates, all sports)')
print(f'{"="*60}')
g = GRAND
print(f'  ML:     {g["ml_h"]}/{g["ml_t"]} ({round(g["ml_h"]/g["ml_t"]*100,1) if g["ml_t"] else 0}%)')
print(f'  Spread: {g["sp_h"]}/{g["sp_t"]} ({round(g["sp_h"]/g["sp_t"]*100,1) if g["sp_t"] else 0}%)')
