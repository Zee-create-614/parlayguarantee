"""
Full Day Capture — Opening & Closing Line Picks + O/U + NCAAB
Generates picks at current lines, saves as opening or closing snapshot.
Run twice: once early (opening), once before tipoff (closing).
Then compare for flips.

Usage:
  python full_day_capture.py opening    # Morning run
  python full_day_capture.py closing    # Pre-tipoff run  
  python full_day_capture.py compare    # Compare open vs close
  python full_day_capture.py score      # Score against results
"""
import sys, os, json, argparse, requests, time
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(os.path.abspath(__file__))
API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
BASE = "https://api.the-odds-api.com/v4"
EST = timezone(timedelta(hours=-5))
TODAY = datetime.now(EST).strftime('%Y-%m-%d')

SPORTS = {
    'NBA': 'basketball_nba',
    'NCAAB': 'basketball_ncaab',
}

def fetch_odds(sport_key):
    """Fetch all odds for a sport."""
    r = requests.get(f"{BASE}/sports/{sport_key}/odds/", params={
        'apiKey': API_KEY, 'regions': 'us',
        'markets': 'h2h,spreads,totals', 'oddsFormat': 'american',
    }, timeout=20)
    r.raise_for_status()
    rem = r.headers.get('x-requests-remaining', '?')
    print(f"  API credits remaining: {rem}")
    return r.json()

def parse_game(event):
    """Extract structured pick data from an odds event."""
    game = {
        'id': event['id'],
        'home': event['home_team'],
        'away': event['away_team'],
        'commence': event['commence_time'],
        'bookmakers': {},
    }
    
    consensus_spreads = []
    consensus_totals = []
    consensus_h2h_home = []
    consensus_h2h_away = []
    
    for bk in event.get('bookmakers', []):
        bk_data = {}
        for mkt in bk.get('markets', []):
            if mkt['key'] == 'spreads':
                for o in mkt['outcomes']:
                    if o['name'] == event['home_team']:
                        bk_data['home_spread'] = o['point']
                        bk_data['home_spread_price'] = o['price']
                        consensus_spreads.append(o['point'])
                    elif o['name'] == event['away_team']:
                        bk_data['away_spread'] = o['point']
                        bk_data['away_spread_price'] = o['price']
            elif mkt['key'] == 'totals':
                for o in mkt['outcomes']:
                    if o['name'] == 'Over':
                        bk_data['over'] = o['point']
                        bk_data['over_price'] = o['price']
                        consensus_totals.append(o['point'])
                    elif o['name'] == 'Under':
                        bk_data['under'] = o['point']
                        bk_data['under_price'] = o['price']
            elif mkt['key'] == 'h2h':
                for o in mkt['outcomes']:
                    if o['name'] == event['home_team']:
                        bk_data['home_ml'] = o['price']
                        consensus_h2h_home.append(o['price'])
                    elif o['name'] == event['away_team']:
                        bk_data['away_ml'] = o['price']
                        consensus_h2h_away.append(o['price'])
        game['bookmakers'][bk['key']] = bk_data
    
    # Consensus lines
    game['consensus_spread'] = round(sum(consensus_spreads) / len(consensus_spreads), 1) if consensus_spreads else None
    game['consensus_total'] = round(sum(consensus_totals) / len(consensus_totals), 1) if consensus_totals else None
    game['consensus_home_ml'] = round(sum(consensus_h2h_home) / len(consensus_h2h_home)) if consensus_h2h_home else None
    game['consensus_away_ml'] = round(sum(consensus_h2h_away) / len(consensus_h2h_away)) if consensus_h2h_away else None
    
    return game

def american_to_implied(ml):
    if ml is None: return 0.5
    if ml > 0:
        return 100 / (ml + 100)
    else:
        return abs(ml) / (abs(ml) + 100)

def generate_picks(games, sport):
    """Generate spread + O/U picks from consensus odds."""
    picks = []
    for g in games:
        spread = g['consensus_spread']  # home perspective
        total = g['consensus_total']
        home_ml = g['consensus_home_ml']
        away_ml = g['consensus_away_ml']
        
        home_prob = american_to_implied(home_ml)
        away_prob = american_to_implied(away_ml)
        # Normalize
        total_prob = home_prob + away_prob
        home_prob /= total_prob
        away_prob /= total_prob
        
        # Spread pick: favorite covers
        if home_prob > away_prob:
            spread_pick = g['home']
            spread_conf = home_prob
        else:
            spread_pick = g['away']
            spread_conf = away_prob
        
        # Upset composite (simplified): big home dog at home
        upset_score = 0
        upset_flip = False
        if home_prob < 0.4 and spread and spread > 3:
            upset_score = (0.4 - home_prob) * 100 + (spread / 2)
            if upset_score > 15:
                upset_flip = True
        elif away_prob < 0.4 and spread and spread < -3:
            upset_score = (0.4 - away_prob) * 100 + (abs(spread) / 2)
        
        # O/U pick: use pace/total analysis
        # Simple heuristic: if total > sport avg, lean under; if under, lean over
        # NBA avg ~225, NCAAB avg ~145
        sport_avg = 225 if sport == 'NBA' else 145
        if total:
            if total > sport_avg + 5:
                ou_pick = 'UNDER'
                ou_conf = min(0.55 + (total - sport_avg) * 0.003, 0.65)
            elif total < sport_avg - 5:
                ou_pick = 'OVER'
                ou_conf = min(0.55 + (sport_avg - total) * 0.003, 0.65)
            else:
                ou_pick = 'OVER' if total < sport_avg else 'UNDER'
                ou_conf = 0.52
        else:
            ou_pick = None
            ou_conf = 0
        
        pick = {
            'sport': sport,
            'home': g['home'],
            'away': g['away'],
            'commence': g['commence'],
            'consensus_spread': spread,
            'consensus_total': total,
            'home_ml': home_ml,
            'away_ml': away_ml,
            'home_prob': round(home_prob, 4),
            'away_prob': round(away_prob, 4),
            'spread_pick': spread_pick,
            'spread_conf': round(spread_conf, 4),
            'upset_score': round(upset_score, 1),
            'upset_flip': upset_flip,
            'ou_pick': ou_pick,
            'ou_line': total,
            'ou_conf': round(ou_conf, 4),
        }
        picks.append(pick)
    
    # Sort by confidence
    picks.sort(key=lambda x: x['spread_conf'], reverse=True)
    return picks

def run_engine_picks(sport_label, sport_key):
    """Run the actual engine for a sport and return analyzed picks."""
    # Try running the real engine
    if sport_label == 'NBA':
        try:
            from run_engine import main as run_nba
            # The engine writes analyzed_games files
            print(f"  Running NBA engine...")
            run_nba()
            with open(os.path.join(DIR, f'analyzed_games_{TODAY}.json')) as f:
                return json.load(f)
        except Exception as e:
            print(f"  NBA engine error: {e}")
            return None
    elif sport_label == 'NCAAB':
        try:
            from ncaab_data_fetcher import NCAABDataFetcher
            fetcher = NCAABDataFetcher()
            games = fetcher.fetch_and_analyze()
            return games
        except Exception as e:
            print(f"  NCAAB engine error: {e}")
            return None

def snapshot(phase):
    """Take opening or closing snapshot."""
    out_dir = os.path.join(DIR, 'daily_captures', TODAY)
    os.makedirs(out_dir, exist_ok=True)
    
    all_picks = {}
    
    for sport, key in SPORTS.items():
        print(f"\n--- {sport} ({phase}) ---")
        try:
            raw = fetch_odds(key)
            print(f"  {len(raw)} games found")
            games = [parse_game(e) for e in raw]
            picks = generate_picks(games, sport)
            all_picks[sport] = picks
            
            for p in picks:
                flip_tag = " ** UPSET FLIP **" if p['upset_flip'] else ""
                ou_tag = f" | O/U: {p['ou_pick']} {p['ou_line']}" if p['ou_pick'] else ""
                print(f"  {p['away']} @ {p['home']}: "
                      f"Pick {p['spread_pick']} ({p['spread_conf']:.0%}) "
                      f"Spread {p['consensus_spread']}{ou_tag}{flip_tag}")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_picks[sport] = []
    
    # Skip engine run to avoid argparse conflicts
    engine_picks = {}
    
    # Save
    out = {
        'phase': phase,
        'timestamp': datetime.now(EST).isoformat(),
        'date': TODAY,
        'odds_picks': all_picks,
        'engine_picks': engine_picks,
    }
    
    path = os.path.join(out_dir, f'{phase}_picks.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {path}")
    
    # Summary
    for sport, picks in all_picks.items():
        print(f"\n{sport}: {len(picks)} games")
        ou_count = sum(1 for p in picks if p['ou_pick'])
        upset_count = sum(1 for p in picks if p['upset_flip'])
        print(f"  O/U picks: {ou_count}, Upset flips: {upset_count}")

def compare():
    """Compare opening vs closing picks for flips."""
    cap_dir = os.path.join(DIR, 'daily_captures', TODAY)
    
    try:
        with open(os.path.join(cap_dir, 'opening_picks.json')) as f:
            opening = json.load(f)
        with open(os.path.join(cap_dir, 'closing_picks.json')) as f:
            closing = json.load(f)
    except FileNotFoundError as e:
        print(f"Missing file: {e}")
        print("Run both 'opening' and 'closing' first.")
        return
    
    print(f"\n{'='*60}")
    print(f"  OPENING vs CLOSING LINE COMPARISON — {TODAY}")
    print(f"{'='*60}")
    
    for sport in SPORTS:
        open_picks = {f"{p['away']}@{p['home']}": p for p in opening['odds_picks'].get(sport, [])}
        close_picks = {f"{p['away']}@{p['home']}": p for p in closing['odds_picks'].get(sport, [])}
        
        print(f"\n--- {sport} ---")
        flips = 0
        ou_flips = 0
        
        for key in open_picks:
            op = open_picks[key]
            cl = close_picks.get(key)
            if not cl:
                continue
            
            spread_flip = op['spread_pick'] != cl['spread_pick']
            ou_flip = op['ou_pick'] != cl['ou_pick'] if op['ou_pick'] and cl['ou_pick'] else False
            upset_change = op['upset_flip'] != cl['upset_flip']
            spread_move = (cl['consensus_spread'] or 0) - (op['consensus_spread'] or 0)
            total_move = (cl['consensus_total'] or 0) - (op['consensus_total'] or 0)
            
            if spread_flip or ou_flip or upset_change or abs(spread_move) >= 1 or abs(total_move) >= 1:
                print(f"\n  {op['away']} @ {op['home']}:")
                if spread_flip:
                    flips += 1
                    print(f"    SPREAD FLIP: {op['spread_pick']} -> {cl['spread_pick']}")
                if abs(spread_move) >= 0.5:
                    print(f"    Spread moved: {op['consensus_spread']} -> {cl['consensus_spread']} ({spread_move:+.1f})")
                if ou_flip:
                    ou_flips += 1
                    print(f"    O/U FLIP: {op['ou_pick']} -> {cl['ou_pick']}")
                if abs(total_move) >= 0.5:
                    print(f"    Total moved: {op['consensus_total']} -> {cl['consensus_total']} ({total_move:+.1f})")
                if upset_change:
                    print(f"    Upset composite: {op['upset_flip']} -> {cl['upset_flip']}")
        
        print(f"\n  Spread flips: {flips}, O/U flips: {ou_flips}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['opening', 'closing', 'compare', 'score'])
    args = parser.parse_args()
    
    if args.phase in ('opening', 'closing'):
        snapshot(args.phase)
    elif args.phase == 'compare':
        compare()
    elif args.phase == 'score':
        print("Score mode — run score_all_feb20.py pattern for today")
