"""
Generate ALL possible unique parlays for tonight's games.
Now generates BOTH moneyline parlays and spread parlays separately.

With 9 games:
  Singles: 9
  2-leg: C(9,2) = 36
  3-leg: C(9,3) = 84
  4-leg: C(9,4) = 126
  5-leg: C(9,5) = 126
  6-leg: C(9,6) = 84
  7-leg: C(9,7) = 36
  8-leg: C(9,8) = 9
  9-leg: C(9,9) = 1
  TOTAL: 511 unique bets per bet type (moneyline + spread)

FIX (Feb 21, 2026): Parlay generator was using spread cover picks + cover
probabilities for everything. Now properly separates:
  - Moneyline parlays: uses ml_home_prob/ml_away_prob, picks the likely WINNER
  - Spread parlays: uses cover_prob, picks the side to COVER
Scorers must check the bet_type field to know how to grade each pick.
"""

import json
import itertools
from datetime import datetime, date
import os
import sys


def _derive_moneyline_pick(g: dict) -> dict:
    """
    Derive moneyline pick + probability from a game's ML probabilities.
    Falls back to spread pick if ML data is missing.
    """
    ml_home = g.get('ml_home_prob')
    ml_away = g.get('ml_away_prob')

    if ml_home is not None and ml_away is not None:
        if ml_home >= ml_away:
            return {
                'pick': g['home'],
                'pick_side': 'home',
                'win_prob': round(ml_home, 4),
                'pick_label': 'FAVORITE' if ml_home >= 0.6 else 'LEAN',
            }
        else:
            return {
                'pick': g['away'],
                'pick_side': 'away',
                'win_prob': round(ml_away, 4),
                'pick_label': 'FAVORITE' if ml_away >= 0.6 else 'LEAN',
            }
    # Fallback — no ML data, use spread pick as-is (shouldn't happen)
    return {
        'pick': g['pick'],
        'pick_side': g.get('pick_side', '?'),
        'win_prob': g.get('win_prob', 0.5),
        'pick_label': g.get('pick_label', '?'),
    }


def generate_all_parlays(analyzed_games_file='analyzed_games.json', output_file=None):
    # Load analyzed games
    with open(analyzed_games_file, 'r', encoding='utf-8') as f:
        games = json.load(f)
    
    game_date = games[0].get('game_date', date.today().isoformat()) if games else date.today().isoformat()
    
    if not output_file:
        output_file = f'all_parlays_{game_date}.json'
    
    # Build moneyline view of each game
    ml_games = []
    for g in games:
        ml = _derive_moneyline_pick(g)
        ml_games.append({**g, **ml, 'bet_type': 'moneyline'})

    # Spread view uses existing engine output as-is
    spread_games = []
    for g in games:
        spread_games.append({**g, 'bet_type': 'spread'})

    print(f"Generating ALL unique parlays for {game_date}")
    print(f"Games: {len(games)}")
    print(f"Generating moneyline AND spread parlays\n")
    
    all_bets = {
        'date': game_date,
        'generated_at': datetime.now().isoformat(),
        'total_games': len(games),
        'games_moneyline': [],
        'games_spread': [],
        'games': [],  # backward compat — moneyline picks (what scorers check)
        'bets': {},
        'bets_spread': {},
        'summary': {}
    }
    
    # Store game info for both views
    for i, g in enumerate(ml_games):
        info = {
            'game_num': i + 1,
            'home': g['home'],
            'away': g['away'],
            'pick': g['pick'],
            'win_prob': round(g['win_prob'], 4),
            'spread': g.get('spread', 0),
            'pick_label': g.get('pick_label', '?'),
            'bet_type': 'moneyline',
        }
        all_bets['games_moneyline'].append(info)
        all_bets['games'].append(info)  # backward compat

    for i, g in enumerate(spread_games):
        all_bets['games_spread'].append({
            'game_num': i + 1,
            'home': g['home'],
            'away': g['away'],
            'pick': g['pick'],
            'win_prob': round(g['win_prob'], 4),
            'spread': g.get('spread', 0),
            'spread_str': g.get('spread_str', ''),
            'pick_label': g.get('pick_label', '?'),
            'bet_type': 'spread',
        })
    
    total_bets = 0
    
    # ===== MONEYLINE PARLAYS (PRIMARY — scored by game winner) =====
    for legs in range(1, len(ml_games) + 1):
        tier_name = 'single' if legs == 1 else f'{legs}leg'
        combos = list(itertools.combinations(range(len(ml_games)), legs))
        
        tier_bets = []
        for combo in combos:
            combo_games = [ml_games[i] for i in combo]
            
            # Calculate combined probability
            combined_prob = 1.0
            for g in combo_games:
                combined_prob *= g['win_prob']
            
            # Calculate implied payout ($100 bet)
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                payout = round(100 * decimal_odds, 2)
            else:
                payout = 0
            
            # Determine bet quality
            min_conf = min(g['win_prob'] for g in combo_games)
            avg_conf = sum(g['win_prob'] for g in combo_games) / len(combo_games)
            
            # High confidence = all legs >= 60%
            all_high_conf = all(g['win_prob'] >= 0.60 for g in combo_games)
            
            bet = {
                'bet_id': f'{tier_name}_{len(tier_bets)+1:04d}',
                'bet_type': 'moneyline',
                'legs': legs,
                'game_indices': list(combo),
                'picks': [],
                'combined_prob': round(combined_prob, 6),
                'implied_payout_per_100': payout,
                'min_confidence': round(min_conf, 4),
                'avg_confidence': round(avg_conf, 4),
                'all_high_confidence': all_high_conf,
                'result': None,  # Will be filled by scorer
                'legs_correct': None,
                'legs_total': legs,
            }
            
            for g in combo_games:
                bet['picks'].append({
                    'home': g['home'],
                    'away': g['away'],
                    'pick': g['pick'],
                    'win_prob': round(g['win_prob'], 4),
                    'spread': g.get('spread', 0),
                    'pick_label': g.get('pick_label', '?'),
                    'bet_type': 'moneyline',
                    'result': None,  # W/L filled by scorer (did picked team WIN?)
                    'actual_score': None,
                })
            
            tier_bets.append(bet)
        
        # Sort by combined probability descending
        tier_bets.sort(key=lambda x: x['combined_prob'], reverse=True)
        
        all_bets['bets'][tier_name] = tier_bets
        total_bets += len(tier_bets)
        
        if tier_bets:
            print(f"  ML {tier_name}: {len(tier_bets)} parlays (best prob: {tier_bets[0]['combined_prob']:.4f} = ${tier_bets[0]['implied_payout_per_100']:.0f} payout)")

    # ===== SPREAD PARLAYS (scored by ATS cover) =====
    spread_total = 0
    for legs in range(1, len(spread_games) + 1):
        tier_name = 'single' if legs == 1 else f'{legs}leg'
        combos = list(itertools.combinations(range(len(spread_games)), legs))
        
        tier_bets = []
        for combo in combos:
            combo_games = [spread_games[i] for i in combo]
            
            combined_prob = 1.0
            for g in combo_games:
                combined_prob *= g['win_prob']
            
            if combined_prob > 0:
                decimal_odds = 1.0 / combined_prob
                payout = round(100 * decimal_odds, 2)
            else:
                payout = 0
            
            min_conf = min(g['win_prob'] for g in combo_games)
            avg_conf = sum(g['win_prob'] for g in combo_games) / len(combo_games)
            all_high_conf = all(g['win_prob'] >= 0.55 for g in combo_games)
            
            bet = {
                'bet_id': f'spread_{tier_name}_{len(tier_bets)+1:04d}',
                'bet_type': 'spread',
                'legs': legs,
                'game_indices': list(combo),
                'picks': [],
                'combined_prob': round(combined_prob, 6),
                'implied_payout_per_100': payout,
                'min_confidence': round(min_conf, 4),
                'avg_confidence': round(avg_conf, 4),
                'all_high_confidence': all_high_conf,
                'result': None,
                'legs_correct': None,
                'legs_total': legs,
            }
            
            for g in combo_games:
                bet['picks'].append({
                    'home': g['home'],
                    'away': g['away'],
                    'pick': g['pick'],
                    'win_prob': round(g['win_prob'], 4),
                    'spread': g.get('spread', 0),
                    'spread_str': g.get('spread_str', ''),
                    'pick_label': g.get('pick_label', '?'),
                    'bet_type': 'spread',
                    'result': None,  # W/L filled by scorer (did picked team COVER?)
                    'actual_score': None,
                })
            
            tier_bets.append(bet)
        
        tier_bets.sort(key=lambda x: x['combined_prob'], reverse=True)
        all_bets['bets_spread'][tier_name] = tier_bets
        spread_total += len(tier_bets)
        
        if tier_bets:
            print(f"  ATS {tier_name}: {len(tier_bets)} parlays (best prob: {tier_bets[0]['combined_prob']:.4f})")

    # Summary
    all_bets['summary'] = {
        'total_moneyline_bets': total_bets,
        'total_spread_bets': spread_total,
        'total_bets': total_bets + spread_total,
        'by_tier_moneyline': {k: len(v) for k, v in all_bets['bets'].items()},
        'by_tier_spread': {k: len(v) for k, v in all_bets['bets_spread'].items()},
        'high_confidence_ml_bets': sum(
            1 for tier_bets in all_bets['bets'].values() 
            for b in tier_bets if b['all_high_confidence']
        ),
    }
    
    # Revenue simulation (moneyline only — primary product)
    bet_amount = 10
    total_wagered = total_bets * bet_amount
    total_potential_payout = sum(
        b['implied_payout_per_100'] / 100 * bet_amount
        for tier_bets in all_bets['bets'].values()
        for b in tier_bets
    )
    
    all_bets['revenue_simulation'] = {
        'bet_amount': bet_amount,
        'total_wagered': round(total_wagered, 2),
        'total_potential_payout': round(total_potential_payout, 2),
        'note': 'Moneyline parlays scored by game winner. Spread parlays scored by ATS cover.'
    }
    
    # Save
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_bets, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"MONEYLINE BETS: {total_bets}")
    print(f"SPREAD BETS:    {spread_total}")
    print(f"TOTAL:          {total_bets + spread_total}")
    print(f"High confidence ML (all legs 60%+): {all_bets['summary']['high_confidence_ml_bets']}")
    print(f"Saved to: {output_file}")
    print(f"{'='*60}")
    
    # Print top moneyline parlays
    print(f"\nTOP MONEYLINE PARLAYS:")
    for tier_name in ['single', '2leg', '3leg', '4leg', '5leg']:
        if tier_name in all_bets['bets'] and all_bets['bets'][tier_name]:
            best = all_bets['bets'][tier_name][0]
            picks_str = ' + '.join(f"{p['pick']} ({p['win_prob']:.0%})" for p in best['picks'])
            print(f"\n  Best {tier_name}: {picks_str}")
            print(f"    Combined: {best['combined_prob']:.4f} | Payout: ${best['implied_payout_per_100']:.0f} per $100")
    
    return all_bets


if __name__ == '__main__':
    games_file = sys.argv[1] if len(sys.argv) > 1 else 'analyzed_games.json'
    generate_all_parlays(games_file)
