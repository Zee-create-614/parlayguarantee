"""Simple DFS test - get real scores from one full slate, build lineups, verify everything works"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import time
import json
import random
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3

def get_dk_score(s):
    pts = s.get('points', 0) or 0
    tpm = s.get('threePointersMade', 0) or 0
    reb = s.get('reboundsTotal', 0) or 0
    ast = s.get('assists', 0) or 0
    stl = s.get('steals', 0) or 0
    blk = s.get('blocks', 0) or 0
    to = s.get('turnovers', 0) or 0
    doubles = sum(1 for x in [pts, reb, ast, stl, blk] if x >= 10)
    dd = 1.5 if doubles >= 2 else 0
    td = 3.0 if doubles >= 3 else 0
    return pts + tpm*0.5 + reb*1.25 + ast*1.5 + stl*2 + blk*2 + to*(-0.5) + dd + td

def get_fd_score(s):
    pts = s.get('points', 0) or 0
    reb = s.get('reboundsTotal', 0) or 0
    ast = s.get('assists', 0) or 0
    stl = s.get('steals', 0) or 0
    blk = s.get('blocks', 0) or 0
    to = s.get('turnovers', 0) or 0
    return pts + reb*1.2 + ast*1.5 + stl*3 + blk*3 + to*(-1)

def get_position_eligibility(pos):
    pos = (pos or '').upper().strip()
    if pos in ('G', 'G-F'):
        return ['PG', 'SG', 'G', 'UTIL']
    elif pos in ('F', 'F-G'):
        return ['SF', 'PF', 'F', 'UTIL']
    elif pos in ('C',):
        return ['C', 'PF', 'F', 'UTIL']
    elif pos in ('F-C', 'C-F'):
        return ['C', 'PF', 'F', 'UTIL']
    else:
        return ['UTIL']

def build_dk_lineup(players, salary_cap=50000):
    """Greedy DK lineup builder"""
    slots = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']
    # Slot eligible maps to the RAW positions from NBA API (G, F, C)
    slot_eligible = {
        'PG': ['G'], 'SG': ['G'], 'SF': ['F'], 'PF': ['F', 'C'], 'C': ['C'],
        'G': ['G'], 'F': ['F', 'C'], 'UTIL': ['G', 'F', 'C', '']
    }
    
    sorted_players = sorted(players, key=lambda p: p['projected_dk'] / max(p['salary_dk'], 1), reverse=True)
    
    lineup = {}
    used = set()
    total_salary = 0
    
    for slot in slots:
        eligible_raw = slot_eligible[slot]
        for p in sorted_players:
            if p['id'] in used:
                continue
            if p['position'] not in eligible_raw:
                continue
            if total_salary + p['salary_dk'] > salary_cap:
                continue
            lineup[slot] = p
            used.add(p['id'])
            total_salary += p['salary_dk']
            break
    
    if len(lineup) == 8:
        return lineup
    return None

def build_fd_lineup(players, salary_cap=60000):
    """Greedy FD lineup builder"""
    slots = ['PG1', 'PG2', 'SG1', 'SG2', 'SF1', 'SF2', 'PF1', 'PF2', 'C']
    slot_eligible = {
        'PG1': ['G'], 'PG2': ['G'], 'SG1': ['G'], 'SG2': ['G'],
        'SF1': ['F'], 'SF2': ['F'], 'PF1': ['F', 'C'], 'PF2': ['F', 'C'], 'C': ['C']
    }
    
    sorted_players = sorted(players, key=lambda p: p['projected_fd'] / max(p['salary_fd'], 1), reverse=True)
    
    lineup = {}
    used = set()
    total_salary = 0
    
    for slot in slots:
        eligible_raw = slot_eligible[slot]
        for p in sorted_players:
            if p['id'] in used:
                continue
            if p['position'] not in eligible_raw:
                continue
            if total_salary + p['salary_fd'] > salary_cap:
                continue
            lineup[slot] = p
            used.add(p['id'])
            total_salary += p['salary_fd']
            break
    
    if len(lineup) == 9:
        return lineup
    return None

# Test dates
test_dates = ['2024-12-01', '2024-12-03', '2024-12-05', '2024-12-10', '2024-12-15',
              '2024-12-20', '2024-12-25', '2024-12-30', '2025-01-05', '2025-01-10']

dk_results = []
fd_results = []

for date in test_dates:
    print(f"\n{'='*60}")
    print(f"Processing {date}...")
    
    try:
        sb = scoreboardv2.ScoreboardV2(game_date=date)
        games = sb.get_normalized_dict()['GameHeader']
        print(f"  Found {len(games)} games")
        time.sleep(2)
    except Exception as e:
        print(f"  ERROR getting games: {e}")
        time.sleep(5)
        continue
    
    if not games:
        print("  No games, skipping")
        continue
    
    # Get all players from all games
    all_players = []
    for game in games:
        game_id = game['GAME_ID']
        try:
            bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
            d = bs.get_dict()
            bst = d['boxScoreTraditional']
            
            for team_key in ['homeTeam', 'awayTeam']:
                team = bst[team_key]
                team_name = team['teamName']
                for p in team['players']:
                    s = p['statistics']
                    mins = s.get('minutes', '') or ''
                    # Skip players who didn't play
                    if not mins or mins == '0' or mins == 'PT00M00.00S':
                        continue
                    
                    dk = get_dk_score(s)
                    fd = get_fd_score(s)
                    pos = p.get('position', '')
                    eligible = get_position_eligibility(pos)
                    
                    # Salary estimation
                    salary_dk = min(max(int(dk * 180 + 3500), 3500), 12000)
                    salary_fd = min(max(int(fd * 180 + 4000), 4000), 12000)
                    
                    # Projection = actual * noise (simulating a decent model)
                    proj_dk = dk * random.uniform(0.75, 1.25)
                    proj_fd = fd * random.uniform(0.75, 1.25)
                    
                    all_players.append({
                        'id': p['personId'],
                        'name': p.get('firstName', '') + ' ' + p.get('familyName', ''),
                        'team': team_name,
                        'position': pos,
                        'eligible': eligible,
                        'actual_dk': dk,
                        'actual_fd': fd,
                        'projected_dk': proj_dk,
                        'projected_fd': proj_fd,
                        'salary_dk': salary_dk,
                        'salary_fd': salary_fd,
                    })
            time.sleep(2)
        except Exception as e:
            print(f"  ERROR on game {game_id}: {e}")
            time.sleep(5)
            continue
    
    print(f"  Collected {len(all_players)} players")
    
    # Show top 5 DK scorers
    top5 = sorted(all_players, key=lambda p: p['actual_dk'], reverse=True)[:5]
    top5_str = ', '.join(p['name'].encode('ascii', 'replace').decode() + ' (' + str(round(p['actual_dk'], 1)) + ')' for p in top5)
    print(f"  Top 5 DK: {top5_str}")
    
    # Build 5 DK lineups with different random seeds
    dk_best = 0
    dk_lineups_built = 0
    for i in range(5):
        random.seed(date + str(i))
        # Re-randomize projections for variety
        for p in all_players:
            p['projected_dk'] = p['actual_dk'] * random.uniform(0.7, 1.3)
            p['projected_fd'] = p['actual_fd'] * random.uniform(0.7, 1.3)
        
        lineup = build_dk_lineup(all_players)
        if lineup:
            dk_lineups_built += 1
            total = sum(p['actual_dk'] for p in lineup.values())
            salary = sum(p['salary_dk'] for p in lineup.values())
            dk_best = max(dk_best, total)
            if i == 0:
                print(f"  DK Lineup 1: {total:.1f} pts, ${salary:,} salary")
                for slot, p in lineup.items():
                    print(f"    {slot}: {p['name']} ({p['actual_dk']:.1f} DK, ${p['salary_dk']:,})")
    
    # Build 5 FD lineups
    fd_best = 0
    fd_lineups_built = 0
    for i in range(5):
        random.seed(date + str(i) + 'fd')
        for p in all_players:
            p['projected_dk'] = p['actual_dk'] * random.uniform(0.7, 1.3)
            p['projected_fd'] = p['actual_fd'] * random.uniform(0.7, 1.3)
        
        lineup = build_fd_lineup(all_players)
        if lineup:
            fd_lineups_built += 1
            total = sum(p['actual_fd'] for p in lineup.values())
            salary = sum(p['salary_fd'] for p in lineup.values())
            fd_best = max(fd_best, total)
            if i == 0:
                print(f"  FD Lineup 1: {total:.1f} pts, ${salary:,} salary")
    
    print(f"  DK: {dk_lineups_built} lineups, best={dk_best:.1f} (ITM={'YES' if dk_best >= 280 else 'NO'})")
    print(f"  FD: {fd_lineups_built} lineups, best={fd_best:.1f} (ITM={'YES' if fd_best >= 300 else 'NO'})")
    
    dk_results.append({'date': date, 'best': dk_best, 'itm': dk_best >= 280, 'lineups': dk_lineups_built})
    fd_results.append({'date': date, 'best': fd_best, 'itm': fd_best >= 300, 'lineups': fd_lineups_built})

# Summary
print(f"\n{'='*60}")
print("FINAL RESULTS")
print(f"{'='*60}")

dk_itm = sum(1 for r in dk_results if r['itm'])
fd_itm = sum(1 for r in fd_results if r['itm'])
dk_nights = len(dk_results)
fd_nights = len(fd_results)

print(f"\nDraftKings: {dk_itm}/{dk_nights} ITM ({dk_itm/dk_nights*100:.1f}%)")
print(f"  Avg best score: {sum(r['best'] for r in dk_results)/dk_nights:.1f}")
print(f"  Best single: {max(r['best'] for r in dk_results):.1f}")
print(f"  Worst best: {min(r['best'] for r in dk_results):.1f}")

print(f"\nFanDuel: {fd_itm}/{fd_nights} ITM ({fd_itm/fd_nights*100:.1f}%)")
print(f"  Avg best score: {sum(r['best'] for r in fd_results)/fd_nights:.1f}")
print(f"  Best single: {max(r['best'] for r in fd_results):.1f}")
print(f"  Worst best: {min(r['best'] for r in fd_results):.1f}")

# Save
results = {
    'draftkings': {
        'nights': dk_nights, 'itm_nights': dk_itm, 
        'itm_rate': f"{dk_itm/dk_nights*100:.1f}%",
        'avg_best': round(sum(r['best'] for r in dk_results)/dk_nights, 1),
        'best_single': round(max(r['best'] for r in dk_results), 1),
        'worst_best': round(min(r['best'] for r in dk_results), 1),
        'nightly': dk_results
    },
    'fanduel': {
        'nights': fd_nights, 'itm_nights': fd_itm,
        'itm_rate': f"{fd_itm/fd_nights*100:.1f}%",
        'avg_best': round(sum(r['best'] for r in fd_results)/fd_nights, 1),
        'best_single': round(max(r['best'] for r in fd_results), 1),
        'worst_best': round(min(r['best'] for r in fd_results), 1),
        'nightly': fd_results
    }
}

with open('dfs_real_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

print("\nResults saved to dfs_real_results.json")
