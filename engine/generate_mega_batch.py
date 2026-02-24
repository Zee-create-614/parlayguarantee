"""
Comprehensive parlay generator for ParlayGuarantee.
Generates ALL unique parlays across multiple product types for tonight's games.

Product Types:
1. NBA Over/Under Parlays
2. NCAAB Spread/ML Picks + ALL Parlays  
3. NCAAB Over/Under Parlays
4. NBA Over/Under Parlays (full batch)
5. Mixed Parlays (NBA spread + O/U)
6. Mixed Parlays (NCAAB spread + O/U)  
7. Cross-Sport Mixed Parlays (NBA + NCAAB)
8. Ultimate Mixed (NBA spread + NBA O/U + NCAAB spread + NCAAB O/U)
"""

import requests
import json
import itertools
import os
import sys
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List, Tuple
import time

# Windows UTF-8 encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Tank teams for NBA 2025-26 (win% < .35 as of mid-Feb)
TANK_TEAMS = {
    "Washington Wizards", "Charlotte Hornets", "Brooklyn Nets",
    "Portland Trail Blazers", "Utah Jazz",
}

def fetch_nba_odds():
    """Fetch NBA odds (h2h, spreads, totals)"""
    r = requests.get(
        "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/",
        params={
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "dateFormat": "iso",
        },
        timeout=20,
    )
    r.raise_for_status()
    remaining = r.headers.get("x-requests-remaining", "?")
    print(f"NBA Odds API: {len(r.json())} events (remaining: {remaining})")
    return r.json()

def fetch_ncaab_odds():
    """Fetch NCAAB odds (h2h, spreads, totals)"""
    r = requests.get(
        "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds/",
        params={
            "apiKey": API_KEY,
            "regions": "us", 
            "markets": "h2h,spreads,totals",
            "dateFormat": "iso",
        },
        timeout=20,
    )
    r.raise_for_status()
    remaining = r.headers.get("x-requests-remaining", "?")
    print(f"NCAAB Odds API: {len(r.json())} events (remaining: {remaining})")
    return r.json()

def avg_odds(bookmakers, market_key, team):
    """Average decimal odds for a team across bookmakers."""
    prices = []
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == market_key:
                for o in mkt["outcomes"]:
                    if o["name"] == team:
                        prices.append(o["price"])
    return sum(prices) / len(prices) if prices else None

def avg_spread(bookmakers, team):
    """Average spread point for a team across bookmakers."""
    points = []
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == "spreads":
                for o in mkt["outcomes"]:
                    if o["name"] == team:
                        points.append(o.get("point", 0))
    return sum(points) / len(points) if points else 0

def avg_total(bookmakers):
    """Average total line across bookmakers."""
    totals = []
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == "totals":
                for o in mkt["outcomes"]:
                    if o["name"] == "Over":
                        totals.append(o.get("point", 0))
    return sum(totals) / len(totals) if totals else None

def get_total_odds_breakdown(bookmakers):
    """Get Over/Under odds from each bookmaker for consensus logic."""
    over_odds = []
    under_odds = []
    
    for bm in bookmakers:
        for mkt in bm.get("markets", []):
            if mkt["key"] == "totals":
                for o in mkt["outcomes"]:
                    if o["name"] == "Over":
                        over_odds.append(o["price"])
                    elif o["name"] == "Under":
                        under_odds.append(o["price"])
    
    return over_odds, under_odds

def predict_over_under(bookmakers, total_line):
    """
    Predict OVER or UNDER based on bookmaker consensus.
    Logic: If 60%+ of books have Over odds < -110, pick OVER. Vice versa for UNDER.
    Confidence = percentage of books agreeing with the pick direction.
    """
    over_odds, under_odds = get_total_odds_breakdown(bookmakers)
    
    if not over_odds or not under_odds:
        return None, 0, 0
    
    # Convert to American odds for easier -110 comparison
    over_american = [(1 - o) / o * 100 if o > 2 else (1 - o) / o * -100 for o in over_odds]
    under_american = [(1 - u) / u * 100 if u > 2 else (1 - u) / u * -100 for u in under_odds]
    
    # Count books favoring over (over odds < -110) 
    over_favored = sum(1 for odds in over_american if odds < -110)
    under_favored = sum(1 for odds in under_american if odds < -110)
    
    total_books = len(over_odds)
    over_consensus = over_favored / total_books if total_books > 0 else 0
    under_consensus = under_favored / total_books if total_books > 0 else 0
    
    if over_consensus >= 0.6:
        pick = "OVER"
        confidence = over_consensus
    elif under_consensus >= 0.6:
        pick = "UNDER"  
        confidence = under_consensus
    else:
        # Tie-breaker: go with average odds (lower odds = more favored)
        avg_over = sum(over_odds) / len(over_odds)
        avg_under = sum(under_odds) / len(under_odds)
        if avg_over <= avg_under:
            pick = "OVER"
            confidence = 0.55  # neutral-ish confidence
        else:
            pick = "UNDER"
            confidence = 0.55
    
    # Simple edge calculation
    market_total = total_line
    predicted_total = market_total + (1 if pick == "OVER" else -1)  # Simple +/- 1 point edge
    edge = abs(predicted_total - market_total) / market_total
    
    return pick, confidence, edge

def build_nba_spread_games(odds_data, target_date: str) -> List[Dict]:
    """Build NBA spread/ML games (similar to generate_from_odds.py)"""
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])

        home_h2h = avg_odds(bm, "h2h", home)
        away_h2h = avg_odds(bm, "h2h", away)
        if not home_h2h or not away_h2h:
            continue

        # Check if game is for target date
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        est = timezone(timedelta(hours=-5))
        ct_est = ct.astimezone(est)
        game_date_str = ct_est.strftime("%Y-%m-%d")
        target_dt = date.fromisoformat(target_date)
        game_dt = ct_est.date()
        if game_dt != target_dt and game_dt != target_dt + timedelta(days=1):
            continue

        # Implied probabilities from average h2h odds (remove vig proportionally)
        raw_home = 1 / home_h2h
        raw_away = 1 / away_h2h
        total = raw_home + raw_away
        home_prob = raw_home / total
        away_prob = raw_away / total

        spread = avg_spread(bm, home)  # negative = home favored

        pick = home if home_prob >= away_prob else away
        win_prob = max(home_prob, away_prob)

        # Upset potential scoring (same as reference)
        upset_score = 0.0
        upset_reasons = []
        spread_abs = abs(spread)

        if spread_abs < 5:
            upset_score += 0.3
            upset_reasons.append(f"Tight spread ({spread:+.1f})")
        if spread > 0:  # home is underdog
            upset_score += 0.4
            upset_reasons.append("Home underdog")
        if spread_abs >= 7 and win_prob < 0.55:
            upset_score += 0.5
            upset_reasons.append(f"Big dog +{spread_abs:.1f}")

        # Edge vs market
        market_fav_prob = 0.5 + (spread_abs / 25.0)
        market_fav_prob = max(0.3, min(0.85, market_fav_prob))
        edge = win_prob - market_fav_prob if win_prob > 0.5 else 0
        if edge > 0.05:
            upset_score += 0.4
            upset_reasons.append("Model edge vs market")

        # Value score
        value_score = win_prob
        if edge > 0.05:
            value_score += edge * 2.0
        elif edge > 0.02:
            value_score += edge * 1.5
        if pick == home:
            value_score += 0.03
        value_score = max(0.1, min(1.0, value_score))

        # Tank bowl
        tank_bowl = home in TANK_TEAMS and away in TANK_TEAMS

        # Pick label
        if value_score >= 0.72:
            pick_label = "LOCK"
        elif edge > 0.05:
            pick_label = "VALUE"
        elif upset_score >= 0.5:
            pick_label = "UPSET"
        else:
            pick_label = "LEAN"

        games.append({
            "home": home,
            "away": away,
            "pick": pick,
            "win_prob": round(win_prob, 4),
            "home_probability": round(home_prob, 4),
            "away_probability": round(away_prob, 4),
            "game_date": game_date_str,
            "game_time": ct.isoformat(),
            "game_id": g["id"],
            "spread": round(spread, 1),
            "pick_spread": round(spread, 1) if pick == home else round(-spread, 1),
            "value_score": round(value_score, 4),
            "edge_vs_market": round(edge, 4),
            "pick_label": pick_label,
            "upset_potential": round(upset_score, 3),
            "upset_score": round(upset_score, 3),
            "upset_reasons": upset_reasons,
            "tank_bowl": tank_bowl,
            "type": "spread",
            "sport": "NBA",
        })

    games.sort(key=lambda x: x["value_score"], reverse=True)
    return games

def build_nba_ou_games(odds_data, target_date: str) -> List[Dict]:
    """Build NBA Over/Under games"""
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])

        total_line = avg_total(bm)
        if not total_line:
            continue

        # Check if game is for target date
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        est = timezone(timedelta(hours=-5))
        ct_est = ct.astimezone(est)
        game_date_str = ct_est.strftime("%Y-%m-%d")
        target_dt = date.fromisoformat(target_date)
        game_dt = ct_est.date()
        if game_dt != target_dt and game_dt != target_dt + timedelta(days=1):
            continue

        # Predict Over/Under
        ou_pick, confidence, edge = predict_over_under(bm, total_line)
        if not ou_pick:
            continue

        predicted_total = total_line + (1 if ou_pick == "OVER" else -1)

        games.append({
            "home": home,
            "away": away,
            "pick": ou_pick,
            "win_prob": round(confidence, 4),
            "confidence": round(confidence, 4),
            "game_date": game_date_str,
            "game_time": ct.isoformat(),
            "game_id": g["id"],
            "total_line": round(total_line, 1),
            "predicted_total": round(predicted_total, 1),
            "edge": round(edge, 4),
            "type": "over_under",
            "sport": "NBA",
        })

    games.sort(key=lambda x: x["confidence"], reverse=True)
    return games

def build_ncaab_spread_games(odds_data, target_date: str) -> List[Dict]:
    """Build NCAAB spread/ML games (similar to generate_ncaab_from_odds.py)"""
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])

        home_h2h = avg_odds(bm, "h2h", home)
        away_h2h = avg_odds(bm, "h2h", away)
        if not home_h2h or not away_h2h:
            continue

        # Check if game is for target date
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        est = timezone(timedelta(hours=-5))
        ct_est = ct.astimezone(est)
        game_date_str = ct_est.strftime("%Y-%m-%d")
        target_dt = date.fromisoformat(target_date)
        game_dt = ct_est.date()
        if game_dt != target_dt and game_dt != target_dt + timedelta(days=1):
            continue

        # Implied probabilities (vig-removed)
        raw_home = 1 / home_h2h
        raw_away = 1 / away_h2h
        total_raw = raw_home + raw_away
        home_prob = raw_home / total_raw
        away_prob = raw_away / total_raw

        spread = avg_spread(bm, home)

        pick = home if home_prob >= away_prob else away
        win_prob = max(home_prob, away_prob)

        # Upset potential scoring (same logic as NBA engine)
        upset_score = 0.0
        upset_reasons = []
        spread_abs = abs(spread)

        if spread_abs < 5:
            upset_score += 0.3
            upset_reasons.append(f"Tight spread ({spread:+.1f})")
        if spread > 0:  # home is underdog
            upset_score += 0.4
            upset_reasons.append("Home underdog")
        if spread_abs >= 7 and win_prob < 0.55:
            upset_score += 0.5
            upset_reasons.append(f"Big dog +{spread_abs:.1f}")

        # Edge vs market
        market_fav_prob = 0.5 + (spread_abs / 25.0)
        market_fav_prob = max(0.3, min(0.85, market_fav_prob))
        edge = win_prob - market_fav_prob if win_prob > 0.5 else 0
        if edge > 0.05:
            upset_score += 0.4
            upset_reasons.append("Model edge vs market")

        # Value score
        value_score = win_prob
        if edge > 0.05:
            value_score += edge * 2.0
        elif edge > 0.02:
            value_score += edge * 1.5
        # Home court advantage is bigger in college
        if pick == home:
            value_score += 0.04
        value_score = max(0.1, min(1.0, value_score))

        # Pick label
        if value_score >= 0.72:
            pick_label = "LOCK"
        elif edge > 0.05:
            pick_label = "VALUE"
        elif upset_score >= 0.5:
            pick_label = "UPSET"
        else:
            pick_label = "LEAN"

        games.append({
            "home": home,
            "away": away,
            "pick": pick,
            "win_prob": round(win_prob, 4),
            "home_probability": round(home_prob, 4),
            "away_probability": round(away_prob, 4),
            "game_date": game_date_str,
            "game_time": ct.isoformat(),
            "game_id": g["id"],
            "spread": round(spread, 1),
            "value_score": round(value_score, 4),
            "edge_vs_market": round(edge, 4),
            "pick_label": pick_label,
            "upset_potential": round(upset_score, 3),
            "upset_score": round(upset_score, 3),
            "upset_reasons": upset_reasons,
            "type": "spread",
            "sport": "NCAAB",
        })

    games.sort(key=lambda x: x["value_score"], reverse=True)
    return games

def build_ncaab_ou_games(odds_data, target_date: str) -> List[Dict]:
    """Build NCAAB Over/Under games"""
    games = []
    for g in odds_data:
        home = g["home_team"]
        away = g["away_team"]
        bm = g.get("bookmakers", [])

        total_line = avg_total(bm)
        if not total_line:
            continue

        # Check if game is for target date
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        est = timezone(timedelta(hours=-5))
        ct_est = ct.astimezone(est)
        game_date_str = ct_est.strftime("%Y-%m-%d")
        target_dt = date.fromisoformat(target_date)
        game_dt = ct_est.date()
        if game_dt != target_dt and game_dt != target_dt + timedelta(days=1):
            continue

        # Predict Over/Under
        ou_pick, confidence, edge = predict_over_under(bm, total_line)
        if not ou_pick:
            continue

        predicted_total = total_line + (1 if ou_pick == "OVER" else -1)

        games.append({
            "home": home,
            "away": away,
            "pick": ou_pick,
            "win_prob": round(confidence, 4),
            "confidence": round(confidence, 4),
            "game_date": game_date_str,
            "game_time": ct.isoformat(),
            "game_id": g["id"],
            "total_line": round(total_line, 1),
            "predicted_total": round(predicted_total, 1),
            "edge": round(edge, 4),
            "type": "over_under",
            "sport": "NCAAB",
        })

    games.sort(key=lambda x: x["confidence"], reverse=True)
    return games

def generate_all_parlays_from_games(games, product_name, max_legs=None):
    """Generate all unique parlays from a list of games (like generate_all_parlays.py)"""
    if not games:
        return {}
    
    game_date = games[0].get('game_date', date.today().isoformat())
    
    # Cap combo generation based on pool size
    pool_size = len(games)
    if max_legs is None:
        if pool_size > 20:
            max_legs = 4
            print(f"  Large pool ({pool_size} games) - capping at {max_legs}-leg combos")
        elif pool_size > 15:
            max_legs = 5
            print(f"  Medium pool ({pool_size} games) - capping at {max_legs}-leg combos")
        else:
            max_legs = min(8, pool_size)  # Normal cap at 8 legs
    
    all_bets = {
        'date': game_date,
        'product': product_name,
        'generated_at': datetime.now().isoformat(),
        'total_games': len(games),
        'games': [],
        'bets': {},
        'summary': {}
    }
    
    # Store game info
    for i, g in enumerate(games):
        game_info = {
            'game_num': i + 1,
            'home': g['home'],
            'away': g['away'],
            'pick': g['pick'],
            'win_prob': round(g['win_prob'], 4),
            'type': g.get('type', 'unknown'),
            'sport': g.get('sport', 'unknown'),
        }
        
        # Add type-specific info
        if g.get('type') == 'spread':
            game_info.update({
                'spread': g.get('spread', 0),
                'pick_label': g.get('pick_label', '?'),
                'value_score': round(g.get('value_score', 0), 3),
            })
        elif g.get('type') == 'over_under':
            game_info.update({
                'total_line': g.get('total_line', 0),
                'predicted_total': g.get('predicted_total', 0),
                'edge': round(g.get('edge', 0), 4),
            })
        
        all_bets['games'].append(game_info)
    
    total_bets = 0
    
    # Generate every possible combo for each leg count
    for legs in range(1, min(max_legs + 1, len(games) + 1)):
        tier_name = 'single' if legs == 1 else f'{legs}leg'
        combos = list(itertools.combinations(range(len(games)), legs))
        
        tier_bets = []
        for combo in combos:
            combo_games = [games[i] for i in combo]
            
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
                pick_info = {
                    'home': g['home'],
                    'away': g['away'],
                    'pick': g['pick'],
                    'win_prob': round(g['win_prob'], 4),
                    'type': g.get('type', 'unknown'),
                    'sport': g.get('sport', 'unknown'),
                    'result': None,  # W/L filled by scorer
                }
                
                # Add type-specific fields
                if g.get('type') == 'spread':
                    pick_info['spread'] = g.get('spread', 0)
                    pick_info['pick_label'] = g.get('pick_label', '?')
                elif g.get('type') == 'over_under':
                    pick_info['total_line'] = g.get('total_line', 0)
                    pick_info['predicted_total'] = g.get('predicted_total', 0)
                    pick_info['edge'] = round(g.get('edge', 0), 4)
                
                bet['picks'].append(pick_info)
            
            tier_bets.append(bet)
        
        # Sort by combined probability descending
        tier_bets.sort(key=lambda x: x['combined_prob'], reverse=True)
        
        all_bets['bets'][tier_name] = tier_bets
        total_bets += len(tier_bets)
        
        print(f"    {tier_name}: {len(tier_bets)} unique parlays (best prob: {tier_bets[0]['combined_prob']:.4f} = ${tier_bets[0]['implied_payout_per_100']:.0f} payout)")
    
    # Summary
    all_bets['summary'] = {
        'total_bets': total_bets,
        'by_tier': {k: len(v) for k, v in all_bets['bets'].items()},
        'high_confidence_bets': sum(
            1 for tier_bets in all_bets['bets'].values() 
            for b in tier_bets if b['all_high_confidence']
        ),
    }
    
    print(f"    TOTAL: {total_bets} unique bets generated")
    print(f"    High confidence (all legs 60%+): {all_bets['summary']['high_confidence_bets']}")
    
    return all_bets

def save_parlay_data(data, filename):
    """Save parlay data to engine directory"""
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(engine_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved: {filename}")
    return filepath

def main():
    target_date = date.today().isoformat()
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    
    print(f"🚀 GENERATING MEGA BATCH FOR {target_date}")
    print("=" * 60)
    print("Starting up...")
    
    # Fetch odds data (single API call per sport)
    print("📊 Fetching Odds Data...")
    print("About to fetch NBA odds...")
    nba_odds = fetch_nba_odds()
    time.sleep(1)  # Rate limit courtesy
    ncaab_odds = fetch_ncaab_odds()
    
    print(f"✅ Got {len(nba_odds)} NBA games, {len(ncaab_odds)} NCAAB games")
    print()
    
    # Build analyzed games for all types
    print("🔍 Analyzing Games...")
    nba_spread_games = build_nba_spread_games(nba_odds, target_date)
    nba_ou_games = build_nba_ou_games(nba_odds, target_date)
    ncaab_spread_games = build_ncaab_spread_games(ncaab_odds, target_date)
    ncaab_ou_games = build_ncaab_ou_games(ncaab_odds, target_date)
    
    print(f"  NBA Spread: {len(nba_spread_games)} games")
    print(f"  NBA O/U: {len(nba_ou_games)} games")
    print(f"  NCAAB Spread: {len(ncaab_spread_games)} games")
    print(f"  NCAAB O/U: {len(ncaab_ou_games)} games")
    print()
    
    if not (nba_spread_games or nba_ou_games or ncaab_spread_games or ncaab_ou_games):
        print("❌ No games found for target date. Exiting.")
        return
    
    # Product generation
    all_products = {}
    
    print("🎯 GENERATING PRODUCTS:")
    print()
    
    # 1. NBA Over/Under Parlays  
    if nba_ou_games:
        print("1️⃣  NBA Over/Under Parlays")
        data = generate_all_parlays_from_games(nba_ou_games, "nba_ou")
        save_parlay_data(data, f"nba_ou_all_parlays_{target_date}.json")
        all_products['nba_ou'] = len(data.get('bets', {}))
        print()
    
    # 2. NCAAB Spread/ML Picks + ALL Parlays
    if ncaab_spread_games:
        print("2️⃣  NCAAB Spread/ML All Parlays")
        data = generate_all_parlays_from_games(ncaab_spread_games, "ncaab_spread")
        save_parlay_data(data, f"ncaab_all_parlays_{target_date}.json")
        all_products['ncaab_spread'] = len(data.get('bets', {}))
        print()
    
    # 3. NCAAB Over/Under Parlays
    if ncaab_ou_games:
        print("3️⃣  NCAAB Over/Under Parlays")
        data = generate_all_parlays_from_games(ncaab_ou_games, "ncaab_ou")
        save_parlay_data(data, f"ncaab_ou_all_parlays_{target_date}.json")
        all_products['ncaab_ou'] = len(data.get('bets', {}))
        print()
    
    # 4. NBA Over/Under Parlays (already done above as #1, but mentioned separately)
    
    # 5. Mixed Parlays (NBA spread + O/U)
    if nba_spread_games and nba_ou_games:
        print("5️⃣  NBA Mixed Parlays (Spread + O/U)")
        mixed_pool = nba_spread_games + nba_ou_games
        data = generate_all_parlays_from_games(mixed_pool, "nba_mixed", max_legs=8)
        save_parlay_data(data, f"nba_mixed_all_parlays_{target_date}.json")
        all_products['nba_mixed'] = len(data.get('bets', {}))
        print()
    
    # 6. Mixed Parlays (NCAAB spread + O/U)
    if ncaab_spread_games and ncaab_ou_games:
        print("6️⃣  NCAAB Mixed Parlays (Spread + O/U)")
        mixed_pool = ncaab_spread_games + ncaab_ou_games
        data = generate_all_parlays_from_games(mixed_pool, "ncaab_mixed", max_legs=8)
        save_parlay_data(data, f"ncaab_mixed_all_parlays_{target_date}.json")
        all_products['ncaab_mixed'] = len(data.get('bets', {}))
        print()
    
    # 7. Cross-Sport Mixed Parlays (NBA + NCAAB spreads)
    if nba_spread_games and ncaab_spread_games:
        print("7️⃣  Cross-Sport Mixed Parlays (NBA + NCAAB Spreads)")
        cross_pool = nba_spread_games + ncaab_spread_games
        data = generate_all_parlays_from_games(cross_pool, "cross_sport", max_legs=6)
        save_parlay_data(data, f"cross_sport_all_parlays_{target_date}.json")
        all_products['cross_sport'] = len(data.get('bets', {}))
        print()
    
    # 8. Ultimate Mixed (All four types)
    if nba_spread_games and nba_ou_games and ncaab_spread_games and ncaab_ou_games:
        print("8️⃣  Ultimate Mixed Parlays (NBA spread + NBA O/U + NCAAB spread + NCAAB O/U)")
        ultimate_pool = nba_spread_games + nba_ou_games + ncaab_spread_games + ncaab_ou_games
        data = generate_all_parlays_from_games(ultimate_pool, "ultimate_mixed", max_legs=5)
        save_parlay_data(data, f"ultimate_mixed_parlays_{target_date}.json")
        all_products['ultimate_mixed'] = len(data.get('bets', {}))
        print()
    
    # Grand summary
    print("🏆 GRAND SUMMARY")
    print("=" * 60)
    total_products = len(all_products)
    total_bets = 0
    
    for product, tiers in all_products.items():
        if isinstance(tiers, dict):
            bet_count = sum(len(tier_data) for tier_data in tiers.values())
        else:
            bet_count = tiers  # fallback if it's just a number
        total_bets += bet_count if isinstance(bet_count, int) else 0
        print(f"  {product:>20}: {bet_count if isinstance(bet_count, int) else 'N/A'} bets")
    
    print("=" * 60)
    print(f"  {'TOTAL PRODUCTS':<20}: {total_products}")
    print(f"  {'TOTAL BETS':<20}: {total_bets}")
    print(f"  {'DATE':<20}: {target_date}")
    print("=" * 60)
    
    print("\n✅ MEGA BATCH COMPLETE!")
    print(f"All files saved to engine directory")

if __name__ == "__main__":
    main()