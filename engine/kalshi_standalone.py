"""
Kalshi Standalone Client — Fetches game-level NBA prediction market data.
NOT auto-wired into the engine pipeline. Manual A/B testing only.
Created: 2026-02-23
"""
import requests
import json
import logging
from datetime import datetime, date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

KALSHI_TO_FULL = {
    'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
    'LAC': 'LA Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
    'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards',
}
FULL_TO_KALSHI = {v: k for k, v in KALSHI_TO_FULL.items()}


def fetch_kalshi_games(target_date: Optional[str] = None) -> Dict[str, Dict]:
    """Fetch Kalshi NBA moneyline markets for a given date."""
    if not target_date:
        target_date = date.today().strftime('%Y-%m-%d')
    
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    kalshi_date = dt.strftime('%y%b%d').upper()  # 26FEB23
    
    results = {}
    
    r = requests.get(f"{BASE_URL}/events", params={
        'limit': 50, 'status': 'open', 'series_ticker': 'KXNBAGAME',
        'with_nested_markets': 'true'
    }, timeout=15)
    r.raise_for_status()
    
    for event in r.json().get('events', []):
        ticker = event.get('event_ticker', '')
        if kalshi_date not in ticker:
            continue
        
        teams = {}
        for market in event.get('markets', []):
            mticker = market.get('ticker', '')
            parts = mticker.rsplit('-', 1)
            if len(parts) < 2:
                continue
            abbr = parts[1]
            full = KALSHI_TO_FULL.get(abbr)
            if not full:
                continue
            
            yb = market.get('yes_bid', 0)
            ya = market.get('yes_ask', 0)
            lp = market.get('last_price', 0)
            vol = market.get('volume', 0)
            
            prob = ((yb + ya) / 200.0) if (yb > 0 and ya > 0) else (lp / 100.0 if lp > 0 else None)
            
            teams[full] = {'prob': prob, 'yes_bid': yb/100, 'yes_ask': ya/100, 'volume': vol}
        
        if len(teams) == 2:
            results[ticker] = teams
    
    return results


def generate_comparison(engine_picks: List[Dict], target_date: Optional[str] = None) -> Dict:
    """Compare engine picks with Kalshi consensus. Returns blended picks."""
    kalshi_data = fetch_kalshi_games(target_date)
    
    comparison = []
    blended_picks = []
    changes = []
    KALSHI_WEIGHT = 0.25
    
    # Build lookup: team name -> kalshi game data
    kalshi_lookup = {}
    for ticker, teams in kalshi_data.items():
        for team_name in teams:
            kalshi_lookup[team_name] = (ticker, teams)
    
    for pick in engine_picks:
        home = pick.get('home_team', '')
        away = pick.get('away_team', '')
        engine_winner = pick.get('predicted_winner', '')
        engine_conf = pick.get('confidence', 0.5)
        
        blended = pick.copy()
        comp = {
            'game': f"{away} @ {home}",
            'engine_pick': engine_winner,
            'engine_conf': engine_conf,
            'kalshi_home_prob': None,
            'kalshi_away_prob': None,
            'kalshi_favors': None,
            'blended_pick': engine_winner,
            'blended_conf': engine_conf,
            'divergence': None,
            'changed': False,
            'kalshi_volume': None
        }
        
        # Try to find this game in Kalshi data
        match = None
        for ticker, teams in kalshi_data.items():
            if home in teams and away in teams:
                match = teams
                break
        
        if match and match[home]['prob'] is not None and match[away]['prob'] is not None:
            h_prob = match[home]['prob']
            a_prob = match[away]['prob']
            h_vol = match[home]['volume']
            a_vol = match[away]['volume']
            
            kalshi_favors = home if h_prob > a_prob else away
            
            # Get Kalshi prob for the engine's picked team
            pick_kalshi_prob = h_prob if engine_winner == home else a_prob
            
            # Blend
            blended_conf = (engine_conf * (1 - KALSHI_WEIGHT)) + (pick_kalshi_prob * KALSHI_WEIGHT)
            divergence = abs(engine_conf - pick_kalshi_prob)
            
            # If blended drops below 50% AND Kalshi disagrees, flip
            if blended_conf < 0.50 and pick_kalshi_prob < 0.45:
                new_winner = away if engine_winner == home else home
                blended['predicted_winner'] = new_winner
                blended['pick_spread'] = -pick.get('pick_spread', 0)
                blended['confidence'] = round(1.0 - blended_conf, 4)
                blended['kalshi_flipped'] = True
                comp['changed'] = True
                comp['blended_pick'] = new_winner
                comp['blended_conf'] = round(1.0 - blended_conf, 4)
                changes.append(f"{away} @ {home}: {engine_winner} → {new_winner} (divergence {divergence:.1%})")
            else:
                blended['confidence'] = round(blended_conf, 4)
                comp['blended_conf'] = round(blended_conf, 4)
            
            comp['kalshi_home_prob'] = h_prob
            comp['kalshi_away_prob'] = a_prob
            comp['kalshi_favors'] = kalshi_favors
            comp['divergence'] = round(divergence, 4)
            comp['kalshi_volume'] = h_vol + a_vol
            
            blended['kalshi_prob'] = pick_kalshi_prob
            blended['kalshi_divergence'] = round(divergence, 4)
        
        comparison.append(comp)
        blended_picks.append(blended)
    
    return {
        'generated_at': datetime.now().isoformat(),
        'kalshi_weight': KALSHI_WEIGHT,
        'total_games': len(engine_picks),
        'games_with_kalshi': sum(1 for c in comparison if c['kalshi_home_prob'] is not None),
        'picks_changed': len(changes),
        'changes': changes,
        'comparison': comparison,
        'blended_picks': blended_picks,
        'kalshi_raw': {k: {t: d for t, d in v.items()} for k, v in kalshi_data.items()}
    }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    data = fetch_kalshi_games()
    print(f"Found {len(data)} games on Kalshi today:")
    for ticker, teams in data.items():
        print(f"\n  {ticker}:")
        for team, info in teams.items():
            p = info['prob']
            print(f"    {team}: {p:.1%} (vol: {info['volume']:,})" if p else f"    {team}: N/A")
