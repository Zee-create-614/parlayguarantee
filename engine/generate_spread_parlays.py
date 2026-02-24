"""
Generate ALL possible spread (ATS) parlays for tonight's games.
Spread bets are typically -110 each side, so payout math is different.
Each leg at -110 means parlay odds compound as (2.909)^n - style.

This complements the ML parlays in generate_all_parlays.py
"""

import json
import itertools
from datetime import datetime, date
import sys

def american_to_decimal(american):
    """Convert American odds to decimal odds"""
    if american >= 100:
        return 1 + american / 100
    else:
        return 1 + 100 / abs(american)

def generate_spread_parlays(analyzed_games_file='analyzed_games.json', output_file=None):
    with open(analyzed_games_file, 'r', encoding='utf-8') as f:
        games = json.load(f)
    
    game_date = games[0].get('game_date', date.today().isoformat()) if games else date.today().isoformat()
    
    if not output_file:
        output_file = f'all_spread_parlays_{game_date}.json'
    
    print(f"Generating ALL unique SPREAD parlays for {game_date}")
    print(f"Games: {len(games)}")
    
    # For spread bets, each game has a spread pick
    # Standard spread odds: -110 (bet $110 to win $100)
    spread_decimal = american_to_decimal(-110)  # 1.909
    
    # Build spread picks for each game
    spread_picks = []
    for g in games:
        spread = g.get('spread', 0)
        if spread == 0:
            continue
        
        # Determine the spread pick
        # Home team spread is the value we have
        # If spread is +6.0, home team is getting 6 points (underdog)
        # If spread is -6.0, home team is giving 6 points (favorite)
        home = g['home']
        away = g['away']
        
        # Pick: favorite covers or underdog covers?
        # Use our model's pick — if we picked the home team, we take home spread
        pick = g['pick']
        if pick == home:
            spread_value = spread  # e.g. +6.0 means home getting points
            cover_team = home
        else:
            spread_value = -spread  # flip for away team
            cover_team = away
        
        spread_picks.append({
            'home': home,
            'away': away,
            'cover_pick': cover_team,
            'spread_value': spread_value,
            'original_spread': spread,
            'win_prob': g.get('win_prob', 0.5),
            'pick_label': g.get('pick_label', '?'),
            'upset_potential': g.get('upset_potential', g.get('upset_score', 0)),
            'upset_flip': g.get('upset_flip', False),
            'game_date': g.get('game_date', game_date),
        })
    
    print(f"\nSpread picks ({len(spread_picks)} games):")
    for sp in spread_picks:
        print(f"  {sp['away']} @ {sp['home']} → {sp['cover_pick']} {sp['spread_value']:+.1f} | {sp['pick_label']}")
    
    all_bets = {
        'date': game_date,
        'generated_at': datetime.now().isoformat(),
        'bet_type': 'spread',
        'total_games': len(spread_picks),
        'games': spread_picks,
        'bets': {},
        'summary': {},
    }
    
    total_bets = 0
    n = len(spread_picks)
    
    for legs in range(1, n + 1):
        tier_name = 'single' if legs == 1 else f'{legs}leg'
        combos = list(itertools.combinations(range(n), legs))
        
        tier_bets = []
        for combo in combos:
            combo_picks = [spread_picks[i] for i in combo]
            
            # Parlay payout at -110 per leg
            parlay_decimal = spread_decimal ** legs
            payout_per_100 = round((parlay_decimal - 1) * 100, 2)
            payout_per_10 = round((parlay_decimal - 1) * 10, 2)
            payout_per_15 = round((parlay_decimal - 1) * 15, 2)
            payout_per_25 = round((parlay_decimal - 1) * 25, 2)
            
            # Approximate combined cover probability
            # Spread bets are ~50/50 by design, but our model has edge
            combined_prob = 1.0
            for p in combo_picks:
                # Use model win prob as proxy for cover prob (conservative)
                combined_prob *= p['win_prob']
            
            upset_count = sum(1 for p in combo_picks if p.get('pick_label') == 'UPSET')
            
            bet = {
                'bet_id': f'spread_{tier_name}_{len(tier_bets)+1:04d}',
                'legs': legs,
                'game_indices': list(combo),
                'picks': [{
                    'home': p['home'],
                    'away': p['away'],
                    'cover_pick': p['cover_pick'],
                    'spread_value': p['spread_value'],
                    'win_prob': round(p['win_prob'], 4),
                    'pick_label': p['pick_label'],
                    'result': None,
                } for p in combo_picks],
                'parlay_decimal_odds': round(parlay_decimal, 4),
                'payout_per_10': payout_per_10,
                'payout_per_15': payout_per_15,
                'payout_per_25': payout_per_25,
                'payout_per_100': payout_per_100,
                'combined_model_prob': round(combined_prob, 6),
                'upset_legs': upset_count,
                'result': None,
                'legs_correct': None,
                'legs_total': legs,
            }
            tier_bets.append(bet)
        
        tier_bets.sort(key=lambda x: x['combined_model_prob'], reverse=True)
        all_bets['bets'][tier_name] = tier_bets
        total_bets += len(tier_bets)
        
        # Show payout for this tier
        print(f"  {tier_name}: {len(tier_bets)} parlays | $15 bet pays ${tier_bets[0]['payout_per_15']:.2f}")
    
    all_bets['summary'] = {
        'total_bets': total_bets,
        'by_tier': {k: len(v) for k, v in all_bets['bets'].items()},
    }
    
    # Revenue simulation
    pricing = {
        'single': 5, '2leg': 8, '3leg': 8, '4leg': 10,
        '5leg': 10, '6leg': 15, '7leg': 15, '8leg': 20, '9leg': 20,
    }
    total_deposits = sum(len(bets) * pricing.get(tier, 10) for tier, bets in all_bets['bets'].items())
    all_bets['revenue_simulation'] = {
        'total_deposits': total_deposits,
        'note': 'Spread parlays at -110 per leg',
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_bets, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {total_bets} spread parlays saved to {output_file}")
    print(f"Total deposits if all sold: ${total_deposits:,}")
    
    # Show 9-leg payout
    if '9leg' in all_bets['bets']:
        nine = all_bets['bets']['9leg'][0]
        print(f"\n🌙 9-LEG SPREAD PARLAY:")
        for p in nine['picks']:
            print(f"  {p['cover_pick']} {p['spread_value']:+.1f} | {p['pick_label']}")
        print(f"  $15 pays: ${nine['payout_per_15']:,.2f}")
        print(f"  $25 pays: ${nine['payout_per_25']:,.2f}")
    
    return all_bets


if __name__ == '__main__':
    generate_spread_parlays()
