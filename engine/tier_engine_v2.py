"""
Tier-Based Engine v2 for ParlayGuarantee
Uses The Odds API as primary data source (real Vegas lines)
Generates picks organized by tier: single, 2-7 leg parlays
"""

import json
import logging
import sys
import math
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from itertools import combinations
import random

logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Tier config: how many unique parlays per tier
TIERS = {
    'single': {'legs': 1, 'count': 5},
    '2leg':   {'legs': 2, 'count': 5},
    '3leg':   {'legs': 3, 'count': 3},
    '4leg':   {'legs': 4, 'count': 3},
    '5leg':   {'legs': 5, 'count': 2},
    '6leg':   {'legs': 6, 'count': 2},
    '7leg':   {'legs': 7, 'count': 1},
}


def american_to_implied_prob(american: int) -> float:
    """Convert American odds to implied probability."""
    if american < 0:
        return abs(american) / (abs(american) + 100)
    else:
        return 100 / (american + 100)


def fetch_games(sport: str = "basketball_nba") -> List[Dict]:
    """Fetch upcoming games with odds from The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'us',
        'markets': 'h2h,spreads',
        'oddsFormat': 'american',
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    remaining = r.headers.get('x-requests-remaining', '?')
    logger.info(f"Odds API: {len(r.json())} games, {remaining} requests remaining")
    return r.json()


def analyze_game(game: Dict) -> Dict:
    """
    Analyze a single game using consensus spread odds from multiple bookmakers.
    PRIMARY pick type: spread cover (will the picked team cover the spread?)
    Spread cover probability is derived from consensus spread odds across books.
    Moneyline win probability kept as secondary reference.
    """
    home = game['home_team']
    away = game['away_team']
    commence = game['commence_time']
    
    # Parse date from commence_time (ISO format)
    dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
    # Convert to EST
    from datetime import timezone
    est = timezone(timedelta(hours=-5))
    dt_est = dt.astimezone(est)
    game_date = dt_est.strftime('%Y-%m-%d')
    game_time = dt_est.strftime('%I:%M %p EST')
    
    # Aggregate odds across bookmakers for consensus
    home_ml_probs = []
    away_ml_probs = []
    home_spread_points = []
    home_spread_probs = []
    away_spread_probs = []
    
    for bm in game.get('bookmakers', []):
        for mkt in bm.get('markets', []):
            if mkt['key'] == 'h2h':
                for outcome in mkt['outcomes']:
                    prob = american_to_implied_prob(outcome['price'])
                    if outcome['name'] == home:
                        home_ml_probs.append(prob)
                    elif outcome['name'] == away:
                        away_ml_probs.append(prob)
            elif mkt['key'] == 'spreads':
                for outcome in mkt['outcomes']:
                    spread_prob = american_to_implied_prob(outcome['price'])
                    if outcome['name'] == home:
                        home_spread_points.append(outcome.get('point', 0))
                        home_spread_probs.append(spread_prob)
                    elif outcome['name'] == away:
                        away_spread_probs.append(spread_prob)
    
    if not home_spread_probs or not away_spread_probs:
        # No spread data — can't make spread picks, skip
        return None
    
    # === MONEYLINE WIN PROBABILITY (reference) ===
    ml_home_prob = None
    ml_away_prob = None
    if home_ml_probs and away_ml_probs:
        avg_home_ml = sum(home_ml_probs) / len(home_ml_probs)
        avg_away_ml = sum(away_ml_probs) / len(away_ml_probs)
        ml_total = avg_home_ml + avg_away_ml
        ml_home_prob = avg_home_ml / ml_total
        ml_away_prob = avg_away_ml / ml_total
    
    # Average spread line (from home team perspective: negative = home favored)
    avg_spread = round(sum(home_spread_points) / len(home_spread_points), 1) if home_spread_points else None
    
    # === SPREAD COVER ANALYSIS (PRIMARY) ===
    # Consensus spread cover probs across all books (vig-removed)
    # This is the REAL signal — when books disagree on spread pricing, 
    # the side with higher consensus cover prob has an edge
    avg_home_spread_raw = sum(home_spread_probs) / len(home_spread_probs)
    avg_away_spread_raw = sum(away_spread_probs) / len(away_spread_probs)
    spread_total = avg_home_spread_raw + avg_away_spread_raw
    home_cover_prob = avg_home_spread_raw / spread_total
    away_cover_prob = avg_away_spread_raw / spread_total
    
    # Determine favorite/dog from the spread line
    if avg_spread is not None and avg_spread < 0:
        favorite = home
        dog = away
        fav_ml = ml_home_prob or 0.5
    else:
        favorite = away
        dog = home
        fav_ml = ml_away_prob or 0.5
    
    # === SPREAD EDGE MODEL ===
    # Key insight: spread is designed to be 50/50. Our edge comes from:
    # 1. Consensus spread cover prob divergence from 50% (books disagree)
    # 2. Selective upset detection — NOT a blanket dog boost
    # 3. Home dogs get a small historical ATS edge (~52% ATS)
    #
    # REWORKED Feb 21, 2026: Removed blind big_spread_boost that was picking
    # every dog regardless of context. Upset flips went 0/8 over two nights.
    # New approach: only boost dogs when multiple independent signals agree.
    
    # Start with book consensus
    home_edge = home_cover_prob - 0.5
    away_edge = away_cover_prob - 0.5
    
    # Small home dog ATS edge (historical ~52% cover rate for home dogs)
    # Only applies to moderate underdogs (spread +1 to +8)
    if avg_spread is not None:
        spread_size = abs(avg_spread)
        
        # Home dog small edge: only for moderate spreads (+1 to +8)
        # Heavy underdogs (+10 or more) do NOT get boosted — they're underdogs for a reason
        if avg_spread > 0 and spread_size <= 8:  # home is the dog, moderate spread
            home_edge += 0.01
            away_edge -= 0.01
        
        # PENALTY for heavy dogs: spreads >= 12 are usually accurate.
        # The dog almost never covers massive spreads — lean AWAY from picking them.
        if spread_size >= 12:
            # Reduce confidence in the dog covering
            if avg_spread < 0:  # home is big favorite, away is heavy dog
                away_edge -= 0.01
                home_edge += 0.01
            else:  # away is big favorite, home is heavy dog
                home_edge -= 0.01
                away_edge += 0.01
    
    # Convert edges to confidence (50% base + edge)
    home_confidence = 0.5 + home_edge
    away_confidence = 0.5 + away_edge
    
    # Pick the side with higher adjusted confidence
    if home_confidence >= away_confidence:
        pick = home
        pick_side = 'home'
        cover_prob = round(home_confidence, 3)
        pick_spread = avg_spread
        edge = round(home_edge, 3)
    else:
        pick = away
        pick_side = 'away'
        cover_prob = round(away_confidence, 3)
        pick_spread = round(-avg_spread, 1) if avg_spread is not None else None
        edge = round(away_edge, 3)
    
    # === UPSET COMPOSITE (v2 — smart, selective) ===
    # This scores the DOG's upset potential on a 0-100 scale.
    # Only used to TAG games — does NOT flip picks blindly.
    # Future: wire in injury data, H2H, momentum, streaks from engine_v2/analyzer
    upset_score = 0.0
    upset_reasons = []
    
    if avg_spread is not None and ml_home_prob is not None and ml_away_prob is not None:
        # Identify the dog
        if ml_home_prob < ml_away_prob:
            dog_team = home
            dog_ml = ml_home_prob
            dog_spread = avg_spread  # positive = home getting points
            is_home_dog = True
        else:
            dog_team = away
            dog_ml = ml_away_prob
            dog_spread = -avg_spread if avg_spread else 0
            is_home_dog = False
        
        spread_size = abs(avg_spread)
        
        # Factor 1: Spread-ML divergence (books think spread is close but ML isn't)
        # If spread cover prob is ~50/50 but ML is 65/35, spread may be too tight
        # Skip — this just means books set the spread correctly
        
        # Factor 2: Dog's ML probability (25%+ dogs are live, <20% are dead)
        if dog_ml >= 0.40:
            upset_score += 30
            upset_reasons.append(f"{dog_team} has {dog_ml:.0%} ML — near coin flip")
        elif dog_ml >= 0.30:
            upset_score += 15
            upset_reasons.append(f"{dog_team} has {dog_ml:.0%} ML — live dog")
        elif dog_ml < 0.20:
            upset_score -= 20  # Heavy underdog, avoid
            upset_reasons.append(f"{dog_team} only {dog_ml:.0%} ML — heavy dog, avoid")
        
        # Factor 3: Home court for the dog (home dogs cover ~52% ATS historically)
        if is_home_dog:
            upset_score += 10
            upset_reasons.append(f"{dog_team} is the home dog")
        
        # Factor 4: Small spread (1-5) dogs are much more live than 10+ dogs
        if spread_size <= 5:
            upset_score += 15
            upset_reasons.append(f"Small spread ({spread_size:.1f})")
        elif spread_size <= 8:
            upset_score += 5
        elif spread_size >= 12:
            upset_score -= 15
            upset_reasons.append(f"Massive spread ({spread_size:.1f}) — dog unlikely")
        
        # Factor 5: Book disagreement on spread (high variance = uncertainty = dog opportunity)
        if len(home_spread_probs) >= 3:
            spread_variance = max(home_spread_probs) - min(home_spread_probs)
            if spread_variance >= 0.05:  # >5% disagreement across books
                upset_score += 10
                upset_reasons.append(f"Books disagree on spread (variance {spread_variance:.1%})")
    
    upset_score = max(0, min(100, upset_score))
    
    # Format spread string for display
    if pick_spread is not None:
        spread_str = f"+{pick_spread}" if pick_spread > 0 else str(pick_spread)
    else:
        spread_str = "PK"
    
    return {
        'home': home,
        'away': away,
        'pick': pick,
        'pick_side': pick_side,
        'pick_type': 'spread',
        'spread': avg_spread,           # home spread line (negative = home favored)
        'pick_spread': pick_spread,     # spread from picked team's perspective
        'spread_str': spread_str,       # formatted: "-3.5" or "+6.5"
        'win_prob': cover_prob,         # adjusted cover probability (used for ranking/parlays)
        'cover_prob': cover_prob,       # explicit alias
        'edge': edge,                   # edge vs 50% baseline
        'home_cover_prob': round(home_cover_prob, 3),
        'away_cover_prob': round(away_cover_prob, 3),
        'ml_home_prob': round(ml_home_prob, 3) if ml_home_prob else None,
        'ml_away_prob': round(ml_away_prob, 3) if ml_away_prob else None,
        'upset_score': round(upset_score, 1),
        'upset_reasons': upset_reasons,
        'game_date': game_date,
        'game_time': game_time,
        'commence_time': commence,  # ISO 8601 UTC — needed for time-window parlay grouping
        'game_id': game.get('id', ''),
        'bookmaker_count': len(game.get('bookmakers', [])),
    }


def generate_parlays(games: List[Dict], legs: int, count: int, publish_time=None) -> List[Dict]:
    """
    Generate the best N-leg parlays from analyzed games.
    Optimizes for highest combined probability. No duplicate games.
    
    For multi-leg parlays (2+), groups games by time window so all legs
    in a parlay are placeable together on DraftKings.
    """
    from time_windows import filter_and_group_games, window_label as wl
    
    if legs == 1:
        # Single picks — just top games by confidence
        sorted_games = sorted(games, key=lambda g: g['win_prob'], reverse=True)
        result = []
        for i, g in enumerate(sorted_games[:count]):
            result.append({
                'pick_number': i + 1,
                'type': 'single',
                'legs': 1,
                'games': [g],
                'combined_prob': g['win_prob'],
                'implied_payout': f"{1/g['win_prob']:.1f}x",
            })
        return result
    
    if len(games) < legs:
        return []
    
    # Group games by time window for parlay compatibility
    windows = filter_and_group_games(games, publish_time=publish_time)
    
    all_combos = []
    for window_name, window_games in windows.items():
        if len(window_games) < legs:
            continue
        
        for combo in combinations(range(len(window_games)), legs):
            combo_games = [window_games[i] for i in combo]
            combined = 1.0
            for g in combo_games:
                combined *= g['win_prob']
            all_combos.append((combined, combo_games, window_name))
    
    # Sort by combined prob descending
    all_combos.sort(key=lambda x: x[0], reverse=True)
    
    result = []
    for i, (prob, combo_games, window_name) in enumerate(all_combos[:count]):
        result.append({
            'pick_number': i + 1,
            'type': 'parlay',
            'legs': legs,
            'games': combo_games,
            'combined_prob': round(prob, 4),
            'implied_payout': f"{1/prob:.1f}x" if prob > 0 else "N/A",
            'window': window_name,
            'window_label': wl(window_name),
        })
    
    return result


def run_tier_engine(target_date: str = None) -> Dict:
    """
    Main entry point. Fetches games, analyzes them, generates tier picks.
    
    Args:
        target_date: YYYY-MM-DD string. If None, uses today.
    
    Returns:
        Dict with picks organized by tier
    """
    if not target_date:
        target_date = date.today().strftime('%Y-%m-%d')
    
    logger.info(f"=== TIER ENGINE v2 ===")
    logger.info(f"Target date: {target_date}")
    
    # Fetch all upcoming NBA games with odds
    raw_games = fetch_games()
    
    # Analyze each game
    analyzed = []
    for g in raw_games:
        result = analyze_game(g)
        if result:
            analyzed.append(result)
    
    logger.info(f"Analyzed {len(analyzed)} games total")
    
    # Filter to target date
    today_games = [g for g in analyzed if g['game_date'] == target_date]
    logger.info(f"Games for {target_date}: {len(today_games)}")
    
    # Also get tomorrow's games if needed for multi-day products
    tomorrow = (datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    tomorrow_games = [g for g in analyzed if g['game_date'] == tomorrow]
    logger.info(f"Games for {tomorrow}: {len(tomorrow_games)}")
    
    all_target_games = today_games + tomorrow_games
    
    # Generate tier picks
    output = {
        'generated_at': datetime.now().isoformat(),
        'target_date': target_date,
        'games_today': len(today_games),
        'games_tomorrow': len(tomorrow_games),
        'all_games': all_target_games,
    }
    
    # Save analyzed games for per-user parlay generation
    try:
        with open('analyzed_games.json', 'w', encoding='utf-8') as f:
            json.dump(all_target_games, f, indent=2, default=str)
        logger.info(f"Saved {len(all_target_games)} analyzed games to analyzed_games.json")
    except Exception as e:
        logger.warning(f"Failed to save analyzed_games.json: {e}")
    
    for tier_id, cfg in TIERS.items():
        legs = cfg['legs']
        count = cfg['count']
        
        # Use today's games for single picks
        # Use all games for multi-leg parlays (more combos available)
        pool = today_games if legs <= 2 else all_target_games
        
        # Need enough games
        if len(pool) < legs:
            pool = all_target_games
        
        picks = generate_parlays(pool, legs, count)
        output[tier_id] = {
            'tier_id': tier_id,
            'legs': legs,
            'picks': picks,
            'game_pool_size': len(pool),
        }
        logger.info(f"  {tier_id}: {len(picks)} picks from {len(pool)} games")
    
    return output


def print_report(output: Dict):
    """Print a human-readable report of the tier picks."""
    print(f"\n{'='*60}")
    print(f"PARLAYGUARANTEE TIER ENGINE v2")
    print(f"Generated: {output['generated_at']}")
    print(f"Date: {output['target_date']}")
    print(f"Games today: {output['games_today']} | Tomorrow: {output['games_tomorrow']}")
    print(f"{'='*60}")
    
    # Print all games
    print(f"\nALL GAMES (spread cover picks):")
    for g in output.get('all_games', []):
        spread_str = g.get('spread_str', 'PK')
        print(f"  {g['away']} @ {g['home']} -> {g['pick']} {spread_str} ({g['cover_prob']:.0%} cover) {g['game_time']}")
    
    # Print tier picks
    for tier_id in ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg']:
        tier_data = output.get(tier_id, {})
        picks = tier_data.get('picks', [])
        if not picks:
            continue
        legs = tier_data.get('legs', '?')
        print(f"\n--- {tier_id.upper()} ({legs}-leg) ---")
        for pick in picks:
            prob = pick['combined_prob']
            payout = pick['implied_payout']
            print(f"  Parlay #{pick['pick_number']} ({prob:.1%} prob, {payout})")
            for g in pick['games']:
                spread_str = g.get('spread_str', 'PK')
                print(f"    {g['away']} @ {g['home']} -> {g['pick']} {spread_str} ({g['cover_prob']:.0%} cover)")


if __name__ == '__main__':
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD')
    parser.add_argument('--output', default='picks_output.json', help='Output file')
    args = parser.parse_args()
    
    output = run_tier_engine(args.date)
    
    # Save to file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=str)
    
    print_report(output)
    print(f"\nSaved to {args.output}")
