"""
Score ALL parlays from generate_all_parlays.py against actual NBA results.
Run this the morning after games complete.

Usage: python score_all_parlays.py [all_parlays_YYYY-MM-DD.json]
"""

import json
import requests
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

# ESPN Scoreboard API
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# Team name normalization
NAME_MAP = {
    'LA Clippers': ['LA Clippers', 'Los Angeles Clippers', 'LAC'],
    'Los Angeles Lakers': ['Los Angeles Lakers', 'LA Lakers', 'LAL'],
    'Oklahoma City Thunder': ['Oklahoma City Thunder', 'OKC Thunder', 'OKC'],
}

def normalize_team(name):
    name_lower = name.lower().strip()
    for canonical, aliases in NAME_MAP.items():
        for alias in aliases:
            if alias.lower() == name_lower:
                return canonical
    return name


def fetch_scores(game_date):
    """Fetch final scores from ESPN for a given date"""
    date_str = game_date.strftime('%Y%m%d')
    resp = requests.get(ESPN_SCOREBOARD, params={'dates': date_str}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    
    results = []
    events = data.get('events', [])
    for event in events:
        competitions = event.get('competitions', [])
        if not competitions:
            continue
        comp = competitions[0]
        status = comp.get('status', {}).get('type', {}).get('name', '')
        
        teams = comp.get('competitors', [])
        if len(teams) < 2:
            continue
        
        home = away = None
        home_score = away_score = 0
        for t in teams:
            team_name = t.get('team', {}).get('displayName', '')
            score = int(t.get('score', 0))
            if t.get('homeAway') == 'home':
                home = normalize_team(team_name)
                home_score = score
            else:
                away = normalize_team(team_name)
                away_score = score
        
        if home and away:
            winner = home if home_score > away_score else away
            results.append({
                'home': home,
                'away': away,
                'home_score': home_score,
                'away_score': away_score,
                'winner': winner,
                'margin': abs(home_score - away_score),
                'final': status == 'STATUS_FINAL',
            })
    
    return results


def score_parlays(parlays_file, game_date=None):
    with open(parlays_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not game_date:
        game_date = date.fromisoformat(data['date'])
    
    print(f"Scoring parlays for {game_date}")
    print(f"Total bets: {data['summary']['total_bets']}")
    print()
    
    # Fetch actual scores
    scores = fetch_scores(game_date)
    print(f"Fetched {len(scores)} game results from ESPN")
    
    if not scores:
        print("ERROR: No scores found. Games may not be final yet.")
        return
    
    not_final = [s for s in scores if not s['final']]
    if not_final:
        print(f"WARNING: {len(not_final)} games not yet final")
    
    # Print scores
    print("\nActual Results:")
    for s in scores:
        status = "FINAL" if s['final'] else "IN PROGRESS"
        print(f"  {s['away']} {s['away_score']} @ {s['home']} {s['home_score']} — Winner: {s['winner']} ({status})")
    
    # Build lookup: match by home+away team
    score_lookup = {}
    for s in scores:
        key = (normalize_team(s['home']), normalize_team(s['away']))
        score_lookup[key] = s
        # Also try reverse for safety
        key2 = (normalize_team(s['away']), normalize_team(s['home']))
        score_lookup[key2] = s
    
    # Score each pick in each bet
    tier_results = {}
    overall_stats = {
        'total_bets': 0,
        'bets_won': 0,
        'bets_lost': 0,
        'bets_push': 0,
        'individual_picks_correct': 0,
        'individual_picks_total': 0,
        'high_conf_bets_won': 0,
        'high_conf_bets_total': 0,
        'revenue_won': 0,
        'revenue_wagered': 0,
    }
    
    for tier_name, tier_bets in data['bets'].items():
        tier_won = 0
        tier_lost = 0
        tier_pick_correct = 0
        tier_pick_total = 0
        
        for bet in tier_bets:
            legs_correct = 0
            legs_total = bet['legs']
            all_correct = True
            
            for pick in bet['picks']:
                home = normalize_team(pick['home'])
                away = normalize_team(pick['away'])
                picked = normalize_team(pick['pick'])
                
                key = (home, away)
                game_result = score_lookup.get(key)
                
                if not game_result:
                    # Try with team names from the pick
                    found = False
                    for sk, sv in score_lookup.items():
                        if (picked.lower() in sk[0].lower() or picked.lower() in sk[1].lower()):
                            # Fuzzy match
                            game_result = sv
                            found = True
                            break
                    if not found:
                        pick['result'] = 'NO_SCORE'
                        all_correct = False
                        continue
                
                actual_winner = game_result['winner']
                pick['actual_score'] = f"{game_result['away']} {game_result['away_score']} @ {game_result['home']} {game_result['home_score']}"
                
                if normalize_team(picked) == normalize_team(actual_winner):
                    pick['result'] = 'W'
                    legs_correct += 1
                    tier_pick_correct += 1
                else:
                    pick['result'] = 'L'
                    all_correct = False
                
                tier_pick_total += 1
            
            bet['legs_correct'] = legs_correct
            bet['result'] = 'W' if all_correct else 'L'
            
            if all_correct:
                tier_won += 1
                overall_stats['bets_won'] += 1
                overall_stats['revenue_won'] += bet['implied_payout_per_100'] / 100 * 10  # $10 bet
                if bet.get('all_high_confidence'):
                    overall_stats['high_conf_bets_won'] += 1
            else:
                tier_lost += 1
                overall_stats['bets_lost'] += 1
            
            if bet.get('all_high_confidence'):
                overall_stats['high_conf_bets_total'] += 1
            
            overall_stats['total_bets'] += 1
            overall_stats['revenue_wagered'] += 10
            overall_stats['individual_picks_correct'] += tier_pick_correct
            overall_stats['individual_picks_total'] += tier_pick_total
        
        tier_total = tier_won + tier_lost
        tier_results[tier_name] = {
            'total': tier_total,
            'won': tier_won,
            'lost': tier_lost,
            'win_rate': round(tier_won / tier_total * 100, 1) if tier_total > 0 else 0,
            'pick_accuracy': round(tier_pick_correct / tier_pick_total * 100, 1) if tier_pick_total > 0 else 0,
        }
    
    # Print results
    print(f"\n{'='*70}")
    print(f"RESULTS — {game_date}")
    print(f"{'='*70}")
    print(f"\n{'Tier':<12} {'Total':>6} {'Won':>6} {'Lost':>6} {'Win%':>8} {'Pick Acc':>10}")
    print(f"{'-'*52}")
    
    for tier_name in ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg', '8leg', '9leg']:
        if tier_name in tier_results:
            r = tier_results[tier_name]
            print(f"{tier_name:<12} {r['total']:>6} {r['won']:>6} {r['lost']:>6} {r['win_rate']:>7.1f}% {r['pick_accuracy']:>9.1f}%")
    
    print(f"\n{'='*70}")
    print(f"OVERALL STATS")
    print(f"{'='*70}")
    print(f"Total bets: {overall_stats['total_bets']}")
    print(f"Bets won: {overall_stats['bets_won']} ({overall_stats['bets_won']/max(1,overall_stats['total_bets'])*100:.1f}%)")
    print(f"High-conf bets won: {overall_stats['high_conf_bets_won']}/{overall_stats['high_conf_bets_total']}")
    print(f"Total wagered: ${overall_stats['revenue_wagered']:.2f}")
    print(f"Total won: ${overall_stats['revenue_won']:.2f}")
    print(f"Net P/L: ${overall_stats['revenue_won'] - overall_stats['revenue_wagered']:.2f}")
    
    # Revenue by our pricing model
    print(f"\n{'='*70}")
    print(f"REVENUE SIMULATION (ParlayGuarantee Pricing)")
    print(f"{'='*70}")
    
    # Our pricing: Single $5, Combo $8, Pack $50 (10 picks), Bundle $75
    # For simulation: count how many would be refunded
    tiers_to_check = {
        'single': {'price': 5, 'refund_if': 'pick loses'},
        '2leg': {'price': 8, 'refund_if': 'both lose'},
        '3leg': {'price': 8, 'refund_if': 'all lose'},
    }
    
    # Deposit model: $50 for 10 picks, refund if under 7 correct
    pack_size = 10
    pack_price = 50
    # Take top 10 singles by confidence
    if 'single' in data['bets']:
        top_singles = sorted(data['bets']['single'], key=lambda x: x['combined_prob'], reverse=True)[:pack_size]
        singles_correct = sum(1 for b in top_singles if b.get('result') == 'W')
        refund_pack = singles_correct < 7
        print(f"\nSingle Sport Pack (top {pack_size} picks):")
        print(f"  Correct: {singles_correct}/{pack_size}")
        print(f"  Refund: {'YES' if refund_pack else 'NO — deposit kept!'}")
        print(f"  Revenue: ${0 if refund_pack else pack_price}")
    
    # Save scored results
    data['scored_at'] = datetime.now().isoformat()
    data['tier_results'] = tier_results
    data['overall_stats'] = overall_stats
    
    scored_file = parlays_file.replace('.json', '_scored.json')
    with open(scored_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nScored results saved to: {scored_file}")
    return data


if __name__ == '__main__':
    parlays_file = sys.argv[1] if len(sys.argv) > 1 else f'all_parlays_{date.today().isoformat()}.json'
    
    # If scoring yesterday's games
    if '--yesterday' in sys.argv:
        yesterday = date.today() - timedelta(days=1)
        parlays_file = f'all_parlays_{yesterday.isoformat()}.json'
    
    score_parlays(parlays_file)
