"""
DFS Backtesting System V2 - Optimized for NBA API Rate Limits
Smart bulk data collection followed by offline backtesting

Key improvements:
- Phase 1: Bulk data pull with proper rate limiting and caching
- Phase 2: Offline backtest using cached data only  
- Uses LeagueGameLog for ALL player data in one call (vs 5000+ individual calls)
- Robust retry logic with exponential backoff
- Complete separation of data collection and analysis
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import traceback
import random

# NBA API imports
from nba_api.stats.endpoints import (
    scoreboardv2, 
    leaguegamelog,
    commonplayerinfo
)

# Try to import the newer V3 endpoint, fall back to V2 if needed
try:
    from nba_api.stats.endpoints import boxscoretraditionalv3 as boxscore_endpoint
    BOXSCORE_VERSION = 'v3'
except ImportError:
    from nba_api.stats.endpoints import boxscoretraditionalv2 as boxscore_endpoint
    BOXSCORE_VERSION = 'v2'

from nba_api.stats.static import players, teams
from dfs_engine import DFSEngine, DFSScoring, Player, Lineup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dfs_backtest_v2.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class BacktestResults:
    """Results for a single platform"""
    platform: str
    nights_tested: int
    itm_nights: int
    itm_rate: float
    avg_best_score: float
    worst_night_best: float
    best_single_score: float
    strategy_hit_rates: Dict[str, float]
    total_lineups: int
    details: List[Dict]

class APIManager:
    """Handles NBA API calls with rate limiting and retry logic"""
    
    def __init__(self, base_delay: float = 2.0, max_retries: int = 3):
        self.base_delay = base_delay
        self.max_retries = max_retries
        self.call_count = 0
    
    def make_api_call(self, api_func, *args, **kwargs):
        """Make API call with retry logic and rate limiting"""
        for attempt in range(self.max_retries + 1):
            try:
                # Rate limiting - 2 second delay between ALL calls
                if self.call_count > 0:
                    time.sleep(self.base_delay)
                
                self.call_count += 1
                logger.info(f"API call #{self.call_count} - {api_func.__name__}")
                
                result = api_func(*args, **kwargs)
                return result
                
            except Exception as e:
                if attempt < self.max_retries:
                    # Exponential backoff: 5s, 10s, 20s
                    delay = 5 * (2 ** attempt)
                    logger.warning(f"API call failed (attempt {attempt + 1}): {e}")
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"API call failed after {self.max_retries + 1} attempts: {e}")
                    raise

class DFSDataCollector:
    """Phase 1: Bulk NBA data collection with smart caching"""
    
    def __init__(self, cache_file: str = "dfs_cache.json"):
        self.cache_file = cache_file
        self.api = APIManager()
        self.cache = self.load_cache()
        
        # Date range for backtesting  
        self.start_date = datetime(2024, 12, 1)
        self.end_date = datetime(2025, 1, 15)
        
    def load_cache(self) -> Dict:
        """Load existing cache or create new one"""
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
                logger.info(f"Loaded cache from {self.cache_file}")
                return cache
        except FileNotFoundError:
            logger.info(f"No existing cache found, creating new cache")
            return {
                'season_player_logs': {},
                'game_schedules': {},
                'box_scores': {},
                'collection_date': None,
                'season': '2024-25'
            }
    
    def save_cache(self):
        """Save cache to disk"""
        try:
            self.cache['collection_date'] = datetime.now().isoformat()
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.info(f"Cache saved to {self.cache_file}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
    
    def collect_season_player_logs(self) -> bool:
        """Collect ALL player game logs for the season in ONE API call"""
        cache_key = f"all_players_{self.cache['season']}"
        
        if cache_key in self.cache['season_player_logs']:
            logger.info("Season player logs already cached")
            return True
        
        try:
            logger.info("🔥 COLLECTING ALL SEASON PLAYER LOGS IN ONE CALL...")
            
            # THE SILVER BULLET: Get ALL player game logs for entire season
            league_gamelog = self.api.make_api_call(
                leaguegamelog.LeagueGameLog,
                season='2024-25',
                player_or_team_abbreviation='P',  # P = Player (vs T = Team)
                season_type_all_star='Regular Season'
            )
            
            # Get the dataframe
            player_logs_df = league_gamelog.get_data_frames()[0]
            logger.info(f"Retrieved {len(player_logs_df)} player game log entries")
            
            # Debug: Print available columns
            logger.info(f"Available columns: {list(player_logs_df.columns)}")
            
            # Convert to dict format for easy lookup
            player_logs = {}
            for _, row in player_logs_df.iterrows():
                # Handle different possible column names
                player_id_col = None
                for col in ['Player_ID', 'PLAYER_ID', 'player_id', 'personId']:
                    if col in row:
                        player_id_col = col
                        break
                
                if not player_id_col:
                    logger.error(f"Could not find player ID column in: {list(row.index)}")
                    continue
                
                player_id = str(row[player_id_col])
                
                if player_id not in player_logs:
                    player_logs[player_id] = []
                
                # Convert game date to standardized format
                game_date_col = None
                for col in ['GAME_DATE', 'game_date', 'Game_Date', 'gameDate']:
                    if col in row:
                        game_date_col = col
                        break
                
                if not game_date_col:
                    logger.warning(f"Could not find game date column")
                    continue
                
                try:
                    raw_date = row[game_date_col]
                    if isinstance(raw_date, str):
                        # Try different date formats
                        try:
                            game_date = datetime.strptime(raw_date, '%b %d, %Y').strftime('%Y-%m-%d')
                        except:
                            try:
                                game_date = datetime.strptime(raw_date, '%Y-%m-%d').strftime('%Y-%m-%d')
                            except:
                                try:
                                    game_date = datetime.strptime(raw_date, '%m/%d/%Y').strftime('%Y-%m-%d')
                                except:
                                    logger.warning(f"Could not parse date: {raw_date}")
                                    continue
                    else:
                        logger.warning(f"Unexpected date format: {raw_date}")
                        continue
                except Exception as e:
                    logger.warning(f"Date parsing error: {e}")
                    continue
                
                # Handle flexible stat column names
                def get_stat(stat_names):
                    for name in stat_names:
                        if name in row:
                            val = row.get(name, 0)
                            return val if val is not None else 0
                    return 0
                
                game_log = {
                    'GAME_DATE': game_date,
                    'MATCHUP': row.get('MATCHUP', row.get('matchup', '')),
                    'PTS': get_stat(['PTS', 'pts', 'points']),
                    'FG3M': get_stat(['FG3M', 'fg3m', 'threePointersMade']),
                    'REB': get_stat(['REB', 'reb', 'reboundsTotal']),
                    'AST': get_stat(['AST', 'ast', 'assists']),
                    'STL': get_stat(['STL', 'stl', 'steals']),
                    'BLK': get_stat(['BLK', 'blk', 'blocks']),
                    'TOV': get_stat(['TOV', 'tov', 'turnovers']),
                    'MIN': get_stat(['MIN', 'min', 'minutes'])
                }
                
                player_logs[player_id].append(game_log)
            
            # Sort each player's games by date (newest first)
            for player_id in player_logs:
                player_logs[player_id].sort(
                    key=lambda x: x['GAME_DATE'], 
                    reverse=True
                )
            
            # Cache the results
            self.cache['season_player_logs'][cache_key] = player_logs
            logger.info(f"✅ Cached game logs for {len(player_logs)} players")
            
            self.save_cache()
            return True
            
        except Exception as e:
            logger.error(f"Failed to collect season player logs: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def collect_game_schedules(self) -> bool:
        """Collect game schedules for all test dates"""
        logger.info("Collecting game schedules...")
        
        # Generate test dates (sample 20 evenly across range)
        test_dates = self.generate_test_dates(20)
        
        for date_str in test_dates:
            if date_str in self.cache['game_schedules']:
                logger.info(f"Schedule for {date_str} already cached")
                continue
            
            try:
                logger.info(f"Getting games for {date_str}")
                
                scoreboard = self.api.make_api_call(
                    scoreboardv2.ScoreboardV2,
                    game_date=date_str
                )
                
                games_df = scoreboard.get_data_frames()[0]  # GameHeader
                
                games = []
                for _, game in games_df.iterrows():
                    games.append({
                        'game_id': game['GAME_ID'],
                        'date': date_str,
                        'home_team': game['HOME_TEAM_ID'],
                        'away_team': game['VISITOR_TEAM_ID'],
                        'home_team_name': game.get('HOME_TEAM_ABBREVIATION', 'UNK'),
                        'away_team_name': game.get('VISITOR_TEAM_ABBREVIATION', 'UNK')
                    })
                
                self.cache['game_schedules'][date_str] = games
                logger.info(f"Found {len(games)} games on {date_str}")
                
                # Save cache periodically
                if len(self.cache['game_schedules']) % 5 == 0:
                    self.save_cache()
                    
            except Exception as e:
                logger.error(f"Failed to get games for {date_str}: {e}")
                continue
        
        self.save_cache()
        return True
    
    def collect_box_scores(self) -> bool:
        """Collect box scores for all games on test dates"""
        logger.info("Collecting box scores...")
        
        total_games = sum(len(games) for games in self.cache['game_schedules'].values())
        processed = 0
        
        for date_str, games in self.cache['game_schedules'].items():
            for game in games:
                game_id = game['game_id']
                
                if game_id in self.cache['box_scores']:
                    processed += 1
                    continue
                
                try:
                    logger.info(f"Getting box score for game {game_id} ({processed+1}/{total_games})")
                    
                    if BOXSCORE_VERSION == 'v3':
                        boxscore = self.api.make_api_call(
                            boxscore_endpoint.BoxScoreTraditionalV3,
                            game_id=game_id
                        )
                    else:
                        boxscore = self.api.make_api_call(
                            boxscore_endpoint.BoxScoreTraditionalV2,
                            game_id=game_id
                        )
                    
                    player_stats = boxscore.get_data_frames()[0]  # PlayerStats
                    
                    # Convert to list of player stat dicts
                    players_data = []
                    for _, player in player_stats.iterrows():
                        # Handle different API versions
                        minutes = player.get('minutes', player.get('MIN', '0:00'))
                        
                        if minutes is not None and minutes != '0:00' and minutes != 0:  # Player actually played
                            if BOXSCORE_VERSION == 'v3':
                                player_data = {
                                    'PLAYER_ID': player.get('personId'),
                                    'PLAYER_NAME': f"{player.get('firstName', '')} {player.get('familyName', '')}".strip(),
                                    'TEAM_ID': player.get('teamId'),
                                    'MIN': minutes,
                                    'PTS': player.get('points', 0) or 0,
                                    'FG3M': player.get('threePointersMade', 0) or 0,
                                    'REB': player.get('reboundsTotal', 0) or 0,
                                    'AST': player.get('assists', 0) or 0,
                                    'STL': player.get('steals', 0) or 0,
                                    'BLK': player.get('blocks', 0) or 0,
                                    'TOV': player.get('turnovers', 0) or 0,
                                }
                            else:
                                player_data = {
                                    'PLAYER_ID': player.get('PLAYER_ID'),
                                    'PLAYER_NAME': player.get('PLAYER_NAME', 'Unknown'),
                                    'TEAM_ID': player.get('TEAM_ID'),
                                    'MIN': minutes,
                                    'PTS': player.get('PTS', 0) or 0,
                                    'FG3M': player.get('FG3M', 0) or 0,
                                    'REB': player.get('REB', 0) or 0,
                                    'AST': player.get('AST', 0) or 0,
                                    'STL': player.get('STL', 0) or 0,
                                    'BLK': player.get('BLK', 0) or 0,
                                    'TOV': player.get('TOV', 0) or 0,
                                }
                            
                            players_data.append(player_data)
                    
                    self.cache['box_scores'][game_id] = {
                        'players': players_data,
                        'date': date_str
                    }
                    
                    processed += 1
                    logger.info(f"Box score cached: {len(players_data)} players")
                    
                    # Save cache every 10 games
                    if processed % 10 == 0:
                        self.save_cache()
                        logger.info(f"Progress: {processed}/{total_games} games processed")
                        
                except Exception as e:
                    logger.error(f"Failed to get box score for game {game_id}: {e}")
                    processed += 1
                    continue
        
        self.save_cache()
        logger.info(f"✅ Box score collection complete: {processed}/{total_games} games")
        return True
    
    def generate_test_dates(self, num_dates: int) -> List[str]:
        """Generate evenly spaced test dates"""
        total_days = (self.end_date - self.start_date).days + 1
        
        if num_dates >= total_days:
            # If we want more dates than available, use all dates
            dates = []
            current = self.start_date
            while current <= self.end_date:
                dates.append(current.strftime('%Y-%m-%d'))
                current += timedelta(days=1)
            return dates
        
        # Sample evenly across the range
        step = total_days / num_dates
        dates = []
        
        for i in range(num_dates):
            days_offset = int(i * step)
            test_date = self.start_date + timedelta(days=days_offset)
            dates.append(test_date.strftime('%Y-%m-%d'))
        
        return dates
    
    def collect_all_data(self) -> bool:
        """Phase 1: Collect all required data"""
        logger.info("=" * 80)
        logger.info("🚀 PHASE 1: BULK DATA COLLECTION")
        logger.info("=" * 80)
        
        # Step 1: Get ALL season player logs in ONE call
        if not self.collect_season_player_logs():
            return False
        
        # Step 2: Get game schedules for test dates
        if not self.collect_game_schedules():
            return False
        
        # Step 3: Get box scores for actual results
        if not self.collect_box_scores():
            return False
        
        logger.info("✅ Phase 1 complete - all data cached!")
        return True

class DFSBacktesterV2:
    """Phase 2: Offline backtesting using cached data only"""
    
    def __init__(self, cache_file: str = "dfs_cache.json"):
        self.cache_file = cache_file
        self.cache = self.load_cache()
        self.engine = DFSEngine()
        
        # ITM thresholds
        self.ITM_THRESHOLDS = {
            'draftkings': 280.0,  # 8 players
            'fanduel': 300.0      # 9 players
        }
    
    def load_cache(self) -> Dict:
        """Load cached data"""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Cache file {self.cache_file} not found! Run data collection first.")
            raise
    
    def get_player_projections_from_cache(self, target_date: str) -> Dict[str, Tuple[float, float]]:
        """Calculate player projections using cached season data"""
        season_logs = self.cache['season_player_logs'].get(f"all_players_{self.cache['season']}", {})
        target_dt = datetime.strptime(target_date, '%Y-%m-%d')
        
        projections = {}
        
        for player_id, games in season_logs.items():
            # Filter games before target date
            valid_games = []
            for game in games:
                try:
                    game_dt = datetime.strptime(game['GAME_DATE'], '%Y-%m-%d')
                    if game_dt < target_dt:
                        valid_games.append(game)
                except:
                    continue
            
            if not valid_games:
                continue
            
            # Take last 10 games for projection
            recent_games = valid_games[:10]
            
            if len(recent_games) < 3:  # Need at least 3 games
                continue
            
            # Calculate weighted projections
            dk_points = []
            fd_points = []
            weights = []
            
            for i, game in enumerate(recent_games):
                # Linear decay weight
                weight = 1.0 - (i * 0.5 / 9)
                weights.append(weight)
                
                # Calculate fantasy points
                dk_pts = DFSScoring.calculate_dk_points(game)
                fd_pts = DFSScoring.calculate_fd_points(game)
                
                dk_points.append(dk_pts * weight)
                fd_points.append(fd_pts * weight)
            
            if weights:
                dk_proj = sum(dk_points) / sum(weights)
                fd_proj = sum(fd_points) / sum(weights)
                projections[player_id] = (dk_proj, fd_proj)
        
        logger.info(f"Generated projections for {len(projections)} players on {target_date}")
        return projections
    
    def create_player_pool_from_cache(self, target_date: str) -> List[Player]:
        """Create player pool using cached box scores and projections"""
        # Get actual players who played on this date
        games = self.cache['game_schedules'].get(target_date, [])
        
        if not games:
            logger.warning(f"No games found for {target_date}")
            return []
        
        # Get projections
        projections = self.get_player_projections_from_cache(target_date)
        
        # Get all players who actually played
        all_players = {}
        
        for game in games:
            game_id = game['game_id']
            box_score = self.cache['box_scores'].get(game_id, {})
            
            for player_data in box_score.get('players', []):
                player_id = str(player_data['PLAYER_ID'])
                
                if player_id in projections and player_id not in all_players:
                    dk_proj, fd_proj = projections[player_id]
                    
                    if dk_proj > 0 and fd_proj > 0:
                        # Assign position using better logic
                        from better_positions import assign_realistic_position
                        position = assign_realistic_position(player_data['PLAYER_NAME'])
                        
                        # Use engine's salary estimation method
                        dk_salary = self.engine.estimate_salary(dk_proj, fd_proj, 'draftkings')
                        fd_salary = self.engine.estimate_salary(dk_proj, fd_proj, 'fanduel')
                        
                        player = Player(
                            id=player_id,
                            name=player_data['PLAYER_NAME'],
                            position=position,
                            team='UNK',
                            salary_dk=dk_salary,
                            salary_fd=fd_salary,
                            projected_dk=dk_proj,
                            projected_fd=fd_proj,
                            value_dk=dk_proj / (dk_salary / 1000) if dk_salary > 0 else 0,
                            value_fd=fd_proj / (fd_salary / 1000) if fd_salary > 0 else 0,
                            recent_games=[]
                        )
                        
                        all_players[player_id] = player
        
        return list(all_players.values())
    
    def get_actual_stats_from_cache(self, target_date: str) -> Dict[str, Dict]:
        """Get actual player stats for a date from cached box scores"""
        games = self.cache['game_schedules'].get(target_date, [])
        actual_stats = {}
        
        for game in games:
            game_id = game['game_id']
            box_score = self.cache['box_scores'].get(game_id, {})
            
            for player_data in box_score.get('players', []):
                player_id = str(player_data['PLAYER_ID'])
                actual_stats[player_id] = player_data
        
        return actual_stats
    
    def score_lineup_actual(self, lineup: Lineup, actual_stats: Dict[str, Dict]) -> float:
        """Score a lineup using actual game results"""
        total_points = 0.0
        
        for player in lineup.players:
            if player.id in actual_stats:
                stats = actual_stats[player.id]
                
                if lineup.platform == 'draftkings':
                    points = DFSScoring.calculate_dk_points(stats)
                else:
                    points = DFSScoring.calculate_fd_points(stats)
                
                total_points += points
            else:
                # Player didn't play or wasn't found - 0 points
                logger.debug(f"Player {player.name} not found in actual stats")
                
        return total_points
    
    def backtest_single_date(self, target_date: str) -> Optional[Dict]:
        """Backtest a single date using only cached data"""
        logger.info(f"Backtesting {target_date} (offline)...")
        
        # Get player pool from cache
        players = self.create_player_pool_from_cache(target_date)
        
        if not players:
            logger.warning(f"No valid players found for {target_date}")
            return None
        
        # Get actual stats from cache
        actual_stats = self.get_actual_stats_from_cache(target_date)
        
        logger.info(f"Found {len(players)} players with projections")
        
        # Generate lineups for both platforms
        results = {}
        
        for platform in ['draftkings', 'fanduel']:
            platform_results = {
                'lineups': [],
                'actual_scores': [],
                'best_score': 0,
                'itm_count': 0
            }
            
            # Generate 5 lineups using different strategies
            lineups = []
            
            # Strategy 1: Greedy (max projected points)
            lineup1 = self.engine.generate_lineup_greedy(players, platform)
            if lineup1:
                lineups.append(lineup1)
            
            # Strategy 2: Value focus (best points per dollar)
            lineup2 = self.engine.generate_lineup_value(players, platform)
            if lineup2:
                lineups.append(lineup2)
            
            # Strategies 3-5: Mixed approaches
            for i in range(3):
                mixed = self.engine.generate_lineup_mixed(
                    players, platform, f"Mixed {i+1}"
                )
                if mixed:
                    lineups.append(mixed)
            
            # Score all lineups with actual results
            for lineup in lineups:
                actual_score = self.score_lineup_actual(lineup, actual_stats)
                
                platform_results['lineups'].append({
                    'strategy': lineup.strategy,
                    'projected_points': lineup.projected_points,
                    'actual_points': actual_score,
                    'total_salary': lineup.total_salary,
                    'players': [
                        {
                            'name': p.name,
                            'position': p.position,
                            'salary': p.salary_dk if platform == 'draftkings' else p.salary_fd,
                            'projected': p.projected_dk if platform == 'draftkings' else p.projected_fd,
                            'actual_stats': actual_stats.get(p.id, {})
                        }
                        for p in lineup.players
                    ]
                })
                
                platform_results['actual_scores'].append(actual_score)
                platform_results['best_score'] = max(
                    platform_results['best_score'], actual_score
                )
                
                # Check ITM
                if actual_score >= self.ITM_THRESHOLDS[platform]:
                    platform_results['itm_count'] += 1
            
            results[platform] = platform_results
        
        return {
            'date': target_date,
            'players_count': len(players),
            'results': results
        }
    
    def run_backtest(self) -> Dict[str, BacktestResults]:
        """Phase 2: Run complete backtest using cached data"""
        logger.info("=" * 80)
        logger.info("📊 PHASE 2: OFFLINE BACKTESTING")
        logger.info("=" * 80)
        
        # Get test dates from cache
        test_dates = list(self.cache['game_schedules'].keys())
        test_dates.sort()
        
        logger.info(f"Testing {len(test_dates)} nights: {test_dates[0]} to {test_dates[-1]}")
        
        # Initialize results
        platform_results = {
            'draftkings': {
                'nights': [],
                'total_nights': 0,
                'itm_nights': 0,
                'best_scores': [],
                'strategy_results': {}
            },
            'fanduel': {
                'nights': [],
                'total_nights': 0,
                'itm_nights': 0,
                'best_scores': [],
                'strategy_results': {}
            }
        }
        
        # Process each date (no API calls - all from cache!)
        for i, test_date in enumerate(test_dates):
            try:
                logger.info(f"Processing night {i+1}/{len(test_dates)}: {test_date}")
                
                result = self.backtest_single_date(test_date)
                
                if result:
                    # Process results for each platform
                    for platform in ['draftkings', 'fanduel']:
                        platform_data = result['results'][platform]
                        platform_results[platform]['nights'].append(result)
                        platform_results[platform]['total_nights'] += 1
                        platform_results[platform]['best_scores'].append(
                            platform_data['best_score']
                        )
                        
                        # Count ITM nights
                        if platform_data['itm_count'] > 0:
                            platform_results[platform]['itm_nights'] += 1
                        
                        # Track strategy performance
                        for lineup_result in platform_data['lineups']:
                            strategy = lineup_result['strategy']
                            if strategy not in platform_results[platform]['strategy_results']:
                                platform_results[platform]['strategy_results'][strategy] = {
                                    'attempts': 0,
                                    'itm_hits': 0
                                }
                            
                            platform_results[platform]['strategy_results'][strategy]['attempts'] += 1
                            
                            if lineup_result['actual_points'] >= self.ITM_THRESHOLDS[platform]:
                                platform_results[platform]['strategy_results'][strategy]['itm_hits'] += 1
                
            except Exception as e:
                logger.error(f"Error processing {test_date}: {e}")
                continue
        
        # Calculate final statistics
        final_results = {}
        
        for platform in ['draftkings', 'fanduel']:
            data = platform_results[platform]
            
            if data['total_nights'] > 0:
                strategy_hit_rates = {}
                for strategy, stats in data['strategy_results'].items():
                    if stats['attempts'] > 0:
                        strategy_hit_rates[strategy] = stats['itm_hits'] / stats['attempts']
                
                final_results[platform] = BacktestResults(
                    platform=platform,
                    nights_tested=data['total_nights'],
                    itm_nights=data['itm_nights'],
                    itm_rate=data['itm_nights'] / data['total_nights'] if data['total_nights'] > 0 else 0,
                    avg_best_score=sum(data['best_scores']) / len(data['best_scores']) if data['best_scores'] else 0,
                    worst_night_best=min(data['best_scores']) if data['best_scores'] else 0,
                    best_single_score=max(data['best_scores']) if data['best_scores'] else 0,
                    strategy_hit_rates=strategy_hit_rates,
                    total_lineups=sum(stats['attempts'] for stats in data['strategy_results'].values()),
                    details=data['nights']
                )
        
        # Save final results
        self.save_final_results(final_results)
        
        logger.info("✅ Backtesting complete!")
        return final_results
    
    def save_final_results(self, results: Dict[str, BacktestResults]):
        """Save final backtest results"""
        filename = "dfs_backtest_results_v2.json"
        
        try:
            json_results = {}
            
            for platform, result in results.items():
                json_results[platform] = {
                    'nights_tested': result.nights_tested,
                    'itm_nights': result.itm_nights,
                    'itm_rate': f"{result.itm_rate:.2%}",
                    'avg_best_score': f"{result.avg_best_score:.1f}",
                    'worst_night_best': f"{result.worst_night_best:.1f}",
                    'best_single_score': f"{result.best_single_score:.1f}",
                    'total_lineups': result.total_lineups,
                    'strategy_hit_rates': {k: f"{v:.2%}" for k, v in result.strategy_hit_rates.items()}
                }
            
            with open(filename, 'w') as f:
                json.dump(json_results, f, indent=2)
            
            logger.info(f"Final results saved to {filename}")
            
            # Print summary
            print("\n" + "="*80)
            print("🎯 DFS BACKTEST V2 RESULTS SUMMARY")
            print("="*80)
            
            for platform, result in results.items():
                print(f"\n{platform.upper()}:")
                print(f"  Nights tested: {result.nights_tested}")
                print(f"  ITM nights: {result.itm_nights} ({result.itm_rate:.2%})")
                print(f"  ITM threshold: {self.ITM_THRESHOLDS[platform]} points")
                print(f"  Avg best score per night: {result.avg_best_score:.1f}")
                print(f"  Best single score: {result.best_single_score:.1f}")
                print(f"  Worst night best: {result.worst_night_best:.1f}")
                print(f"  Total lineups: {result.total_lineups}")
                print("  Strategy hit rates:")
                for strategy, rate in result.strategy_hit_rates.items():
                    print(f"    {strategy}: {rate:.2%}")
            
            print("\n" + "="*80)
            
        except Exception as e:
            logger.error(f"Failed to save final results: {e}")

def main():
    """Run the complete V2 backtest process"""
    logger.info("🚀 DFS BACKTEST V2 - SMART NBA API USAGE")
    logger.info("=" * 80)
    
    try:
        # Phase 1: Data Collection
        collector = DFSDataCollector()
        
        if not collector.collect_all_data():
            logger.error("❌ Data collection failed!")
            return
        
        # Phase 2: Offline Backtesting  
        backtester = DFSBacktesterV2()
        results = backtester.run_backtest()
        
        logger.info("🎉 BACKTEST V2 COMPLETE!")
        return results
        
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        logger.error(traceback.format_exc())
        return None

if __name__ == "__main__":
    main()