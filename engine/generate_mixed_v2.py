"""
Generate mixed parlay products. 
Streams JSON to extract only the 'games' array without loading full file.
"""
import sys, json, itertools, os, re
from datetime import date, datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(__file__)
TODAY = date.today().isoformat()

def extract_games_fast(filename):
    """Extract just the games array from a large JSON file without loading the full thing."""
    path = os.path.join(DIR, filename)
    if not os.path.exists(path):
        return []
    
    # For smaller files, just load normally
    size = os.path.getsize(path)
    if size < 5_000_000:  # <5MB, load normally
        d = json.load(open(path, encoding='utf-8'))
        return d.get('games', [])
    
    # For large files, extract just the games section
    games = []
    with open(path, 'r', encoding='utf-8') as f:
        content = ''
        in_games = False
        bracket_depth = 0
        games_str = ''
        
        for line in f:
            if '"games"' in line and '[' in line:
                in_games = True
                games_str = '['
                bracket_depth = 1
                continue
            
            if in_games:
                for ch in line:
                    if ch == '[':
                        bracket_depth += 1
                    elif ch == ']':
                        bracket_depth -= 1
                    games_str += ch
                    if bracket_depth == 0:
                        in_games = False
                        try:
                            games = json.loads(games_str)
                        except:
                            pass
                        break
                if not in_games:
                    break
    
    return games

def generate_parlays(games, product, max_legs=5):
    n = len(games)
    if n > 30:
        max_legs = min(max_legs, 3)
    elif n > 20:
        max_legs = min(max_legs, 4)
    elif n > 15:
        max_legs = min(max_legs, 5)
    
    result = {
        'date': TODAY,
        'product': product,
        'generated_at': datetime.now().isoformat(),
        'total_games': n,
        'games': games,
        'bets': {},
        'summary': {}
    }
    
    total = 0
    hc = 0
    
    for legs in range(2, min(max_legs + 1, n + 1)):
        tier = f'{legs}leg'
        combos = list(itertools.combinations(range(n), legs))
        bets = []
        
        for ci, combo in enumerate(combos):
            picks = [games[i] for i in combo]
            prob = 1.0
            for p in picks:
                prob *= p.get('win_prob', p.get('confidence', 0.5))
            
            payout = round(100 / prob, 2) if prob > 0 else 0
            all_hc = all(p.get('win_prob', p.get('confidence', 0.5)) >= 0.60 for p in picks)
            if all_hc:
                hc += 1
            
            bets.append({
                'bet_id': f'{product}_{tier}_{ci+1:05d}',
                'legs': legs,
                'game_indices': list(combo),
                'picks': [{
                    'home': p.get('home', p.get('home_team', '')),
                    'away': p.get('away', p.get('away_team', '')),
                    'pick': p.get('pick', ''),
                    'win_prob': round(p.get('win_prob', p.get('confidence', 0.5)), 4),
                    'sport': p.get('sport', '?'),
                    'type': p.get('type', p.get('bet_type', 'spread')),
                    'total_line': p.get('total_line', None),
                } for p in picks],
                'combined_prob': round(prob, 6),
                'implied_payout_per_100': payout,
                'all_high_confidence': all_hc,
                'result': None,
            })
        
        bets.sort(key=lambda x: x['combined_prob'], reverse=True)
        result['bets'][tier] = bets
        total += len(bets)
        if bets:
            print(f"    {tier}: {len(bets)} parlays (best: {bets[0]['combined_prob']:.4f})")
    
    result['summary'] = {
        'total_bets': total,
        'by_tier': {k: len(v) for k, v in result['bets'].items()},
        'high_confidence_bets': hc,
    }
    return result

def save(data, filename):
    path = os.path.join(DIR, filename)
    # Don't save games array in mixed files to keep size down
    save_data = dict(data)
    save_data['games'] = [{'home': g.get('home',''), 'away': g.get('away',''), 'pick': g.get('pick',''), 
                           'sport': g.get('sport',''), 'type': g.get('type','')} for g in data['games']]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, indent=1, ensure_ascii=False)
    size = os.path.getsize(path) / (1024*1024)
    print(f"    Saved: {filename} ({size:.1f} MB, {data['summary']['total_bets']} bets)")

print("Loading game data (streaming large files)...")

nba_spread = extract_games_fast(f'all_parlays_{TODAY}.json')
for g in nba_spread:
    g['sport'] = 'NBA'; g['type'] = 'spread'
print(f"  NBA Spread: {len(nba_spread)} games")

nba_ou = extract_games_fast(f'nba_ou_all_parlays_{TODAY}.json')
for g in nba_ou:
    g['sport'] = 'NBA'; g['type'] = 'over_under'
print(f"  NBA O/U: {len(nba_ou)} games")

ncaab_spread = extract_games_fast(f'ncaab_all_parlays_{TODAY}.json')
for g in ncaab_spread:
    g['sport'] = 'NCAAB'; g['type'] = 'spread'
print(f"  NCAAB Spread: {len(ncaab_spread)} games")

ncaab_ou = extract_games_fast(f'ncaab_ou_all_parlays_{TODAY}.json')
for g in ncaab_ou:
    g['sport'] = 'NCAAB'; g['type'] = 'over_under'
print(f"  NCAAB O/U: {len(ncaab_ou)} games")
print()

# 5. NBA Mixed
if nba_spread and nba_ou:
    print("5. NBA Mixed (Spread + O/U) - pool of", len(nba_spread)+len(nba_ou))
    data = generate_parlays(nba_spread + nba_ou, 'nba_mixed', max_legs=8)
    save(data, f'nba_mixed_all_parlays_{TODAY}.json')
    print()

# 6. NCAAB Mixed
if ncaab_spread and ncaab_ou:
    print("6. NCAAB Mixed (Spread + O/U) - pool of", len(ncaab_spread)+len(ncaab_ou))
    data = generate_parlays(ncaab_spread + ncaab_ou, 'ncaab_mixed', max_legs=3)
    save(data, f'ncaab_mixed_all_parlays_{TODAY}.json')
    print()

# 7. Cross-Sport
if nba_spread and ncaab_spread:
    print("7. Cross-Sport (NBA + NCAAB Spreads) - pool of", len(nba_spread)+len(ncaab_spread))
    data = generate_parlays(nba_spread + ncaab_spread, 'cross_sport', max_legs=4)
    save(data, f'cross_sport_all_parlays_{TODAY}.json')
    print()

# 8. Ultimate Mixed
if nba_spread and nba_ou and ncaab_spread and ncaab_ou:
    print("8. Ultimate Mixed (All 4 Types) - pool of", len(nba_spread)+len(nba_ou)+len(ncaab_spread)+len(ncaab_ou))
    data = generate_parlays(nba_spread + nba_ou + ncaab_spread + ncaab_ou, 'ultimate_mixed', max_legs=3)
    save(data, f'ultimate_mixed_parlays_{TODAY}.json')
    print()

print("ALL MIXED PRODUCTS COMPLETE!")
