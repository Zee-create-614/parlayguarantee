"""
Product-specific engine for ParlayGuarantee
Handles 4 distinct products with different pick mixtures
"""
import sys
import json
import time
import logging
import signal
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import argparse

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams


class APITimeoutException(Exception):
    """Exception raised when API call times out"""
    pass


def timeout_decorator(timeout_seconds=30):
    """Decorator to add timeout to function calls"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            def timeout_handler(signum, frame):
                raise APITimeoutException(f"Function {func.__name__} timed out after {timeout_seconds} seconds")
            
            # Only set up signal handling on Unix-like systems
            if os.name != 'nt':
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_seconds)
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # Clean up signal handler
                if os.name != 'nt':
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    return decorator


def safe_get_data_frames(endpoint_result):
    """Safely convert nba_api endpoint result to list of DataFrames.
    Works around nba_api 1.2.1 get_data_frames() crash on empty data sets."""
    try:
        return endpoint_result.get_data_frames()
    except (IndexError, KeyError):
        data = endpoint_result.get_dict()
        frames = []
        for rs in data.get('resultSets', []):
            headers = rs.get('headers', [])
            rows = rs.get('rowSet', [])
            if headers:
                frames.append(pd.DataFrame(rows, columns=headers))
            else:
                frames.append(pd.DataFrame())
        return frames

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('product_engine.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}

class ProductEngine:
    """
    Multi-product engine for ParlayGuarantee:
    1. Parlay Consistent (Mix A): 4×2-leg, 2×3-leg, 2×4-leg, 1×5-leg, 1×6-leg
    2. Parlay Moonshot (Mix E): 4×2-leg, 2×3-leg, 1×4-leg, 1×5-leg, 1×6-leg, 1×7-leg
    3. Straight Weekday Pack: 10 moneyline picks Mon-Fri
    4. Straight Weekend Pack: 10 moneyline picks Fri-Sun
    """
    
    def __init__(self):
        self.team_stats = {}
        
        # Product configurations
        self.PRODUCTS = {
            'parlay-consistent': {
                'name': 'Parlay Consistent',
                'type': 'parlay',
                'mix': [2, 2, 2, 2, 3, 3, 4, 4, 5, 6],
                'frequency': 'nightly'
            },
            'parlay-moonshot': {
                'name': 'Parlay Moonshot', 
                'type': 'parlay',
                'mix': [2, 2, 2, 2, 3, 3, 4, 5, 6, 7],
                'frequency': 'nightly'
            },
            'parlay-weekday': {
                'name': 'Parlay Weekday',
                'type': 'parlay',
                'mix': [2, 2, 3, 3, 4, 4, 5, 5, 6, 7],
                'frequency': 'weekly',
                'days': 'Mon-Fri',
                'multi_day': True
            },
            'parlay-weekend': {
                'name': 'Parlay Weekend',
                'type': 'parlay',
                'mix': [2, 2, 3, 3, 4, 5, 6],
                'frequency': 'weekly',
                'days': 'Fri-Sun',
                'multi_day': True
            },
            'straight-weekday': {
                'name': 'Straight Weekday Pack',
                'type': 'straight', 
                'count': 10,
                'days': 'Mon-Fri',
                'frequency': 'weekly'
            },
            'referral-bundle': {
                'name': 'Referral Bonus Bundle',
                'type': 'parlay',
                'mix': [2, 3, 4],
                'frequency': 'nightly'
            },
            'straight-weekend': {
                'name': 'Straight Weekend Pack',
                'type': 'straight',
                'count': 10, 
                'days': 'Fri-Sun',
                'frequency': 'weekly'
            }
        }
    
    @timeout_decorator(30)
    def _fetch_team_stats_with_timeout(self, season='2024-25'):
        """Fetch team stats with timeout protection"""
        stats = leaguedashteamstats.LeagueDashTeamStats(season=season)
        return safe_get_data_frames(stats)[0]

    def fetch_team_stats(self):
        """Fetch team stats using the same method as comprehensive_backtest_v2.py"""
        logger.info("Fetching 2024-25 team stats...")
        try:
            df = self._fetch_team_stats_with_timeout('2024-25')
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                gp = row['GP'] if row['GP'] > 0 else 1
                self.team_stats[name] = {
                    'win_pct': row['W_PCT'],
                    'ppg': row['PTS'] / gp,
                }
            logger.info(f"Loaded stats for {len(self.team_stats)} teams")
            time.sleep(1.5)
        except (APITimeoutException, Exception) as e:
            logger.error(f"Error fetching 2024-25 stats: {e}")
            logger.info("Falling back to 2023-24 stats")
            try:
                df = self._fetch_team_stats_with_timeout('2023-24')
                for _, row in df.iterrows():
                    tid = row['TEAM_ID']
                    name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                    gp = row['GP'] if row['GP'] > 0 else 1
                    self.team_stats[name] = {
                        'win_pct': row['W_PCT'],
                        'ppg': row['PTS'] / gp,
                    }
                logger.info(f"Loaded 2023-24 stats for {len(self.team_stats)} teams")
                time.sleep(1.5)
            except (APITimeoutException, Exception) as e2:
                logger.error(f"Fallback also failed: {e2}")
                logger.warning("Using default team stats (0.5 win rate for all teams)")
                # Provide fallback stats so the engine can continue
                default_teams = [t['full_name'] for t in teams.get_teams()]
                for team in default_teams:
                    self.team_stats[team] = {'win_pct': 0.5, 'ppg': 110}

    @timeout_decorator(30)
    def _get_scoreboard_with_timeout(self, date_str):
        """Get scoreboard data with timeout protection"""
        sb = scoreboardv2.ScoreboardV2(game_date=date_str)
        return safe_get_data_frames(sb)

    def fetch_weekly_schedule(self, week_start_date: date) -> List[Dict]:
        """Fetch Mon-Sun games in one batch and save to weekly_schedule.json"""
        # Ensure week_start_date is a Monday
        days_since_monday = week_start_date.weekday()
        monday = week_start_date - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        
        logger.info(f"Fetching weekly schedule: {monday} to {sunday}")
        all_games = self.get_games_for_date_range(monday, sunday)
        
        schedule = {
            'week_start': monday.isoformat(),
            'week_end': sunday.isoformat(),
            'fetched_at': datetime.now().isoformat(),
            'games': all_games,
            'games_by_day': {}
        }
        
        # Group by day
        by_day = defaultdict(list)
        for g in all_games:
            by_day[g['game_date']].append(g)
        schedule['games_by_day'] = dict(by_day)
        
        schedule_path = os.path.join(os.path.dirname(__file__), 'weekly_schedule.json')
        with open(schedule_path, 'w', encoding='utf-8') as f:
            json.dump(schedule, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Weekly schedule saved: {len(all_games)} games across {len(by_day)} days")
        return all_games

    def load_weekly_schedule(self) -> Optional[Dict]:
        """Load previously fetched weekly schedule"""
        schedule_path = os.path.join(os.path.dirname(__file__), 'weekly_schedule.json')
        try:
            with open(schedule_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def analyze_games(self, games: List[Dict]) -> List[Dict]:
        """Analyze games and output with probabilities. Saves to analyzed_games.json."""
        if not self.team_stats:
            self.fetch_team_stats()
        
        analyzed = []
        for game in games:
            winner, prob = self.calculate_log5_probability(game['home_team'], game['away_team'])
            analyzed.append({
                'home': game['home_team'],
                'away': game['away_team'],
                'pick': winner,
                'win_prob': prob,
                'game_date': game.get('game_date', ''),
                'game_time': game.get('game_time', ''),
                'game_id': game.get('game_id', ''),
                'game_status': game.get('game_status', ''),
            })
        
        analyzed_path = os.path.join(os.path.dirname(__file__), 'analyzed_games.json')
        with open(analyzed_path, 'w', encoding='utf-8') as f:
            json.dump(analyzed, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Analyzed {len(analyzed)} games, saved to analyzed_games.json")
        return analyzed

    def get_games_for_date(self, target_date: date) -> List[Dict]:
        """Get games for a specific date"""
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            logger.info(f"Fetching games for {date_str}")
            time.sleep(0.7)
            
            dfs = self._get_scoreboard_with_timeout(date_str)
            header = dfs[0]
            
            if header.empty:
                logger.info(f"No games found for {target_date}")
                return []
            
            games = []
            for _, game in header.iterrows():
                home_id = game['HOME_TEAM_ID']
                away_id = game['VISITOR_TEAM_ID']
                home_team = TEAM_ID_MAP.get(home_id, f"Team_{home_id}")
                away_team = TEAM_ID_MAP.get(away_id, f"Team_{away_id}")
                
                # Extract game time from GAME_STATUS_TEXT (e.g. "7:00 pm ET") or GAME_DATE_EST
                game_time_raw = game.get('GAME_STATUS_TEXT', '')
                game_date_est = game.get('GAME_DATE_EST', '')
                # Try to build an ISO datetime from available data
                game_time = ''
                if game_date_est:
                    game_time = game_date_est  # Often full ISO string
                elif 'pm' in game_time_raw.lower() or 'am' in game_time_raw.lower():
                    game_time = f"{target_date.isoformat()} {game_time_raw.strip()}"
                
                games.append({
                    'game_date': target_date.isoformat(),
                    'home_team': home_team,
                    'away_team': away_team,
                    'game_id': game['GAME_ID'],
                    'game_status': game_time_raw,
                    'game_time': game_time,
                })
            
            logger.info(f"Found {len(games)} games for {target_date}")
            return games
        except APITimeoutException:
            logger.error(f"Timeout fetching games for {target_date}")
            return []
        except Exception as e:
            logger.error(f"Error fetching games for {target_date}: {e}")
            return []
    
    def get_games_for_date_range(self, start_date: date, end_date: date) -> List[Dict]:
        """Get all games in a date range"""
        all_games = []
        current_date = start_date
        
        while current_date <= end_date:
            games = self.get_games_for_date(current_date)
            all_games.extend(games)
            current_date += timedelta(days=1)
        
        return all_games
    
    def calculate_log5_probability(self, home_team: str, away_team: str) -> Tuple[str, float]:
        """
        Calculate win probability using Log5 method with home court advantage
        Same as comprehensive_backtest_v2.py
        """
        home_wp = self.team_stats.get(home_team, {}).get('win_pct', 0.5)
        away_wp = self.team_stats.get(away_team, {}).get('win_pct', 0.5)
        
        # Log5 method: p = (pA * (1 - pB)) / (pA * (1 - pB) + pB * (1 - pA))
        denom = home_wp * (1 - away_wp) + away_wp * (1 - home_wp)
        if denom <= 0:
            home_prob = 0.58  # default home advantage
        else:
            home_prob = (home_wp * (1 - away_wp)) / denom
            
        # Apply home court advantage: multiply by 1.03, then renormalize
        home_prob = home_prob * 1.03
        if home_prob > 1.0:
            home_prob = 1.0
        
        # Renormalize if needed
        if home_prob < 0.25:
            home_prob = 0.25
        elif home_prob > 0.85:
            home_prob = 0.85
            
        if home_prob >= 0.5:
            return home_team, home_prob
        else:
            return away_team, 1 - home_prob
    
    def generate_parlay_picks(self, games: List[Dict], product_config: Dict) -> List[Dict]:
        """Generate parlay picks based on product configuration"""
        if len(games) < 2:
            logger.warning("Not enough games for parlay generation")
            return []
        
        # Calculate probabilities for all games
        game_picks = []
        for game in games:
            winner, prob = self.calculate_log5_probability(game['home_team'], game['away_team'])
            game_picks.append({
                'home': game['home_team'],
                'away': game['away_team'], 
                'pick': winner,
                'win_prob': prob,
                'game_date': game['game_date']
            })
        
        # Sort by probability (highest first)
        game_picks.sort(key=lambda x: x['win_prob'], reverse=True)
        
        parlays = []
        mix = product_config['mix']
        
        for i, legs in enumerate(mix):
            if len(game_picks) < legs:
                logger.warning(f"Not enough games for {legs}-leg parlay")
                continue
                
            # Select games for this parlay, avoiding reuse when possible
            parlay_games = []
            used_games = set()
            
            # For this implementation, we'll reuse games if necessary but try to diversify
            start_idx = (i * 2) % len(game_picks)  # Stagger starting points
            
            for j in range(legs):
                game_idx = (start_idx + j) % len(game_picks)
                game = game_picks[game_idx]
                parlay_games.append(game)
            
            # Calculate combined probability and implied odds
            combined_prob = 1.0
            for game in parlay_games:
                combined_prob *= game['win_prob']
            
            # Convert to American odds format
            if combined_prob > 0.5:
                implied_odds = f"-{int(100 / combined_prob - 100)}"
                payout_mult = 100 / (100 / combined_prob - 100) + 1
            else:
                implied_odds = f"+{int((1 / combined_prob - 1) * 100)}"
                payout_mult = (1 / combined_prob)
            
            parlay = {
                'pick_number': i + 1,
                'type': 'parlay',
                'legs': legs,
                'games': parlay_games,
                'combined_prob': round(combined_prob, 3),
                'implied_payout': f"{payout_mult:.1f}x"
            }
            
            parlays.append(parlay)
        
        return parlays
    
    def generate_straight_picks(self, games: List[Dict], product_config: Dict) -> List[Dict]:
        """Generate straight moneyline picks"""
        if len(games) < product_config['count']:
            logger.warning(f"Not enough games for {product_config['count']} straight picks")
        
        # Calculate probabilities for all games
        game_picks = []
        for game in games:
            winner, prob = self.calculate_log5_probability(game['home_team'], game['away_team'])
            game_picks.append({
                'home': game['home_team'],
                'away': game['away_team'],
                'pick': winner, 
                'win_prob': prob,
                'game_date': game['game_date']
            })
        
        # Sort by probability and take top picks
        game_picks.sort(key=lambda x: x['win_prob'], reverse=True)
        top_picks = game_picks[:product_config['count']]
        
        straight_picks = []
        for i, game in enumerate(top_picks):
            pick = {
                'pick_number': i + 1,
                'type': 'straight',
                'games': [game],
                'combined_prob': game['win_prob'],
                'implied_payout': "1.9x"  # Approximate for ML favorite
            }
            straight_picks.append(pick)
        
        return straight_picks
    
    def generate_picks_for_product(self, product_id: str, target_date: date) -> Optional[Dict]:
        """Generate picks for a specific product"""
        if product_id not in self.PRODUCTS:
            logger.error(f"Unknown product: {product_id}")
            return None
        
        product_config = self.PRODUCTS[product_id]
        logger.info(f"Generating picks for {product_config['name']}")
        
        # Get games based on product type and frequency
        try:
            is_multi_day = product_config.get('multi_day', False)
            days_spec = product_config.get('days', '')
            
            if product_config['frequency'] == 'nightly' and not is_multi_day:
                # Nightly product - get games for target date only
                games = self.get_games_for_date(target_date)
            else:
                # Weekly/multi-day product - get games for the date range
                days_since_monday = target_date.weekday()
                if days_spec == 'Mon-Fri':
                    start_date = target_date - timedelta(days=days_since_monday)
                    end_date = start_date + timedelta(days=4)  # Friday
                elif days_spec == 'Fri-Sun':
                    start_date = target_date - timedelta(days=days_since_monday) + timedelta(days=4)  # Friday
                    end_date = start_date + timedelta(days=2)  # Sunday
                else:
                    # Default to single day
                    start_date = target_date
                    end_date = target_date
                
                # Try loading from weekly schedule first
                schedule = self.load_weekly_schedule()
                if schedule and schedule.get('games'):
                    # Filter to date range
                    games = [g for g in schedule['games'] 
                             if start_date.isoformat() <= g.get('game_date', '') <= end_date.isoformat()]
                    if games:
                        logger.info(f"Loaded {len(games)} games from weekly schedule cache")
                    else:
                        games = self.get_games_for_date_range(start_date, end_date)
                else:
                    games = self.get_games_for_date_range(start_date, end_date)
        
        except Exception as e:
            logger.error(f"Failed to fetch games for {product_config['name']}: {e}")
            games = []
        
        if not games:
            logger.warning(f"No games found for {product_config['name']} - returning empty result")
            # Return structure with empty picks but valid metadata
            return {
                'product': product_id,
                'product_name': product_config['name'],
                'date': target_date.isoformat(),
                'generated_at': datetime.now().isoformat(),
                'picks': [],
                'summary': {
                    'total_picks': 0,
                    'total_games': 0,
                    'product_type': product_config['type']
                }
            }
        
        logger.info(f"Found {len(games)} games for {product_config['name']}")
        
        # Generate picks based on product type
        try:
            if product_config['type'] == 'parlay':
                picks = self.generate_parlay_picks(games, product_config)
            else:
                picks = self.generate_straight_picks(games, product_config)
        except Exception as e:
            logger.error(f"Failed to generate picks for {product_config['name']}: {e}")
            picks = []
        
        if not picks:
            logger.warning(f"No picks generated for {product_config['name']} (insufficient games or error)")
        
        return {
            'product': product_id,
            'product_name': product_config['name'],
            'date': target_date.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'picks': picks,
            'summary': {
                'total_picks': len(picks),
                'total_games': len(games),
                'product_type': product_config['type']
            }
        }
    
    def run(self, product: str, target_date: date, output_file: str = "picks_output.json"):
        """Run the engine for specified product(s)"""
        logger.info(f"Starting Product Engine for: {product}")
        logger.info(f"Target date: {target_date}")
        
        # Fetch team stats
        self.fetch_team_stats()
        
        results = {}
        
        if product == 'all':
            # Generate picks for all products
            for product_id in self.PRODUCTS.keys():
                result = self.generate_picks_for_product(product_id, target_date)
                if result:
                    results[product_id] = result
        else:
            # Generate picks for specific product
            result = self.generate_picks_for_product(product, target_date)
            if result:
                results[product] = result
        
        # Save results
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        logger.info("="*60)
        logger.info("PRODUCT ENGINE RESULTS")
        logger.info("="*60)
        
        for product_id, result in results.items():
            config = self.PRODUCTS[product_id]
            logger.info(f"{config['name']}:")
            logger.info(f"  - Picks: {result['summary']['total_picks']}")
            logger.info(f"  - Games: {result['summary']['total_games']}")
            logger.info(f"  - Type: {result['summary']['product_type']}")
        
        logger.info(f"Results saved to: {output_file}")
        logger.info("="*60)
        
        return results

def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Product Engine')
    parser.add_argument('--product', 
                      choices=['parlay-consistent', 'parlay-moonshot', 'parlay-weekday', 'parlay-weekend',
                               'referral-bundle', 'straight-weekday', 'straight-weekend', 'all'],
                      default='all',
                      help='Product to generate picks for')
    parser.add_argument('--date',
                      help='Target date (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--output',
                      default='picks_output.json',
                      help='Output file path')
    parser.add_argument('--mode',
                      choices=['schedule', 'analyze', 'picks'],
                      default='picks',
                      help='Engine mode: schedule=fetch week games, analyze=update analysis, picks=generate picks')
    
    args = parser.parse_args()
    
    # Parse date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        target_date = date.today()
    
    engine = ProductEngine()
    
    if args.mode == 'schedule':
        # Mode: fetch weekly schedule (run Monday morning)
        engine.fetch_team_stats()
        games = engine.fetch_weekly_schedule(target_date)
        print(f"✅ Weekly schedule fetched: {len(games)} games")
        
    elif args.mode == 'analyze':
        # Mode: analyze/re-analyze games with latest data (run daily)
        engine.fetch_team_stats()
        schedule = engine.load_weekly_schedule()
        if schedule and schedule.get('games'):
            analyzed = engine.analyze_games(schedule['games'])
            print(f"✅ Analyzed {len(analyzed)} games from weekly schedule")
        else:
            # No weekly schedule — analyze today's games
            games = engine.get_games_for_date(target_date)
            if games:
                analyzed = engine.analyze_games(games)
                print(f"✅ Analyzed {len(analyzed)} games for {target_date}")
            else:
                print("❌ No games to analyze")
                sys.exit(1)
    
    elif args.mode == 'picks':
        # Mode: generate picks (run 2hrs before games)
        results = engine.run(args.product, target_date, args.output)
        if results:
            print(f"✅ Success! Generated picks for {len(results)} product(s)")
            print(f"📁 Output saved to: {args.output}")
        else:
            print("❌ Failed to generate picks")
            sys.exit(1)

if __name__ == "__main__":
    main()