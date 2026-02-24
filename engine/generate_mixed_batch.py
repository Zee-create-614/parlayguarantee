"""
Generate remaining mixed parlay products.
Loads already-generated game data from existing files, then builds mixed combos.
"""
import sys, json, itertools, os
from datetime import date, datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(__file__)
TODAY = date.today().isoformat()

def load_games(filename):
    path = os.path.join(DIR, filename)
    if not os.path.exists(path):
        return []
    d = json.load(open(path, encoding='utf-8'))
    return d.get('games', [])

def generate_parlays(games, product, max_legs=5):
    """Generate all unique parlays up to max_legs."""
    n = len(games)
    if n > 20:
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
                    'sport': p.get('sport', 'NBA'),
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
            print(f"    {tier}: {len(bets)} parlays (best prob: {bets[0]['combined_prob']:.4f})")
    
    result['summary'] = {
        'total_bets': total,
        'by_tier': {k: len(v) for k, v in result['bets'].items()},
        'high_confidence_bets': hc,
    }
    return result

def save(data, filename):
    path = os.path.join(DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    size = os.path.getsize(path) / 1024
    print(f"    Saved: {filename} ({size:.0f} KB, {data['summary']['total_bets']} bets)")

# Load existing game data
print("Loading existing game data...")

# NBA spread games from the original all_parlays file
nba_spread = load_games(f'all_parlays_{TODAY}.json')
for g in nba_spread:
    g['sport'] = 'NBA'
    g['type'] = 'spread'
    g['bet_type'] = 'spread'
print(f"  NBA Spread: {len(nba_spread)} games")

# NBA O/U games
nba_ou = load_games(f'nba_ou_all_parlays_{TODAY}.json')
for g in nba_ou:
    g['sport'] = 'NBA'
    g['type'] = 'over_under'
    g['bet_type'] = 'over_under'
print(f"  NBA O/U: {len(nba_ou)} games")

# NCAAB spread games
ncaab_spread = load_games(f'ncaab_all_parlays_{TODAY}.json')
for g in ncaab_spread:
    g['sport'] = 'NCAAB'
    g['type'] = 'spread'
    g['bet_type'] = 'spread'
print(f"  NCAAB Spread: {len(ncaab_spread)} games")

# NCAAB O/U games
ncaab_ou = load_games(f'ncaab_ou_all_parlays_{TODAY}.json')
for g in ncaab_ou:
    g['sport'] = 'NCAAB'
    g['type'] = 'over_under'
    g['bet_type'] = 'over_under'
print(f"  NCAAB O/U: {len(ncaab_ou)} games")

print()

# 5. NBA Mixed (spread + O/U)
if nba_spread and nba_ou:
    print("5. NBA Mixed (Spread + O/U)")
    pool = nba_spread + nba_ou
    print(f"   Pool: {len(pool)} legs")
    data = generate_parlays(pool, 'nba_mixed', max_legs=8)
    save(data, f'nba_mixed_all_parlays_{TODAY}.json')
    print()

# 6. NCAAB Mixed (spread + O/U)
if ncaab_spread and ncaab_ou:
    print("6. NCAAB Mixed (Spread + O/U)")
    pool = ncaab_spread + ncaab_ou
    print(f"   Pool: {len(pool)} legs")
    data = generate_parlays(pool, 'ncaab_mixed', max_legs=4)
    save(data, f'ncaab_mixed_all_parlays_{TODAY}.json')
    print()

# 7. Cross-Sport (NBA spread + NCAAB spread)
if nba_spread and ncaab_spread:
    print("7. Cross-Sport (NBA + NCAAB Spreads)")
    pool = nba_spread + ncaab_spread
    print(f"   Pool: {len(pool)} legs")
    data = generate_parlays(pool, 'cross_sport', max_legs=4)
    save(data, f'cross_sport_all_parlays_{TODAY}.json')
    print()

# 8. Ultimate Mixed (all 4 types)
if nba_spread and nba_ou and ncaab_spread and ncaab_ou:
    print("8. Ultimate Mixed (All 4 Types)")
    pool = nba_spread + nba_ou + ncaab_spread + ncaab_ou
    print(f"   Pool: {len(pool)} legs")
    data = generate_parlays(pool, 'ultimate_mixed', max_legs=3)
    save(data, f'ultimate_mixed_parlays_{TODAY}.json')
    print()

print("DONE!")
