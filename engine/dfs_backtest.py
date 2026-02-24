"""
DFS Backtesting System - Test DFS Engine Performance with Real NBA Data
Date Range: Dec 1, 2024 - Jan 15, 2025
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import traceback

from nba_api.stats.endpoints import (
    scoreboardv2, playergamelog, 
    commonplayerinfo, leaguegamefinder
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dfs_backtest.log'),
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

class DFSBacktester:
    """Comprehensive DFS backtesting system"""
    
    def __init__(self):
        self.engine = DFSEngine()
        self.game_cache = {}
        self.boxscore_cache = {}
        
        # ITM thresholds (points needed to be "in the money")
        self.ITM_THRESHOLDS = {
            'draftkings': 280.0,  # 8 players
            'fanduel': 300.0      # 9 players
        }
        
        # Date range for backtesting
        self.start_date = datetime(2024, 12, 1)
        self.end_date = datetime(2025, 1, 15)
        
    def get_games_for_date(self, date_str: str) -> List[Dict]:
        """Get all NBA games for a specific date"""
        if date_str in self.game_cache:
            return self.game_cache[date_str]
        
        try:
            time.sleep(0.6)  # Rate limiting
            
            scoreboard = scoreboardv2.ScoreboardV2(game_date=date_str)
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
            
            self.game_cache[date_str] = games
            logger.info(f"Found {len(games)} games on {date_str}")
            return games
            
        except Exception as e:
            logger.error(f"Failed to get games for {date_str}: {e}")
            return []
    
    def get_box_score(self, game_id: str) -> Dict[str, List[Dict]]:
        """Get box score data for a game"""
        if game_id in self.boxscore_cache:
            return self.boxscore_cache[game_id]
        
        try:
            time.sleep(0.6)  # Rate limiting
            
            if BOXSCORE_VERSION == 'v3':
                boxscore = boxscore_endpoint.BoxScoreTraditionalV3(game_id=game_id)
            else:
                boxscore = boxscore_endpoint.BoxScoreTraditionalV2(game_id=game_id)
            
            player_stats = boxscore.get_data_frames()[0]  # PlayerStats
            
            # Debug: Print available columns on first call
            if game_id not in self.boxscore_cache:
                logger.info(f"Available columns: {list(player_stats.columns)}")
            
            # Convert to list of player stat dicts
            players_data = []
            for _, player in player_stats.iterrows():
                # Handle different API versions - V3 uses camelCase, V2 uses uppercase
                minutes = player.get('minutes', player.get('MIN', '0:00'))
                
                if minutes is not None and minutes != '0:00' and minutes != 0:  # Player actually played
                    # Map columns based on API version
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
            
            result = {'players': players_data}
            self.boxscore_cache[game_id] = result
            
            logger.info(f"Got box score for game {game_id}: {len(players_data)} players")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get box score for game {game_id}: {e}")
            return {'players': []}
    
    def get_player_position_mapping(self) -> Dict[str, str]:
        """Create a basic player position mapping"""
        # This is a simplified mapping - in reality you'd use roster API
        # For now, we'll make educated guesses based on player names
        position_hints = {
            'Guard': ['PG', 'SG'],
            'Forward': ['SF', 'PF'], 
            'Center': ['C']
        }
        
        # Return a basic mapping - in real implementation, use roster data
        return {}
    
    def create_player_from_boxscore(self, player_data: Dict, target_date: str) -> Optional[Player]:
        """Create Player object with projections based on games before target date"""
        player_id = str(player_data['PLAYER_ID'])
        player_name = player_data['PLAYER_NAME']
        
        # Assign position (simplified - would use roster API in production)
        positions = ['PG', 'SG', 'SF', 'PF', 'C']
        position = positions[hash(player_name) % len(positions)]
        
        try:
            # Calculate projections using engine
            dk_proj, fd_proj = self.engine.calculate_projection(
                player_id, target_date, position, 'UNK'
            )
            
            if dk_proj <= 0 and fd_proj <= 0:
                return None
            
            # Estimate salaries
            dk_salary = self.engine.estimate_salary(dk_proj, fd_proj, 'draftkings')
            fd_salary = self.engine.estimate_salary(dk_proj, fd_proj, 'fanduel')
            
            return Player(
                id=player_id,
                name=player_name,
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
            
        except Exception as e:
            logger.warning(f"Failed to create player projection for {player_name}: {e}")
            return None
    
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
                logger.warning(f"Player {player.name} not found in actual stats")
                
        return total_points
    
    def backtest_single_date(self, target_date: str) -> Dict:
        """Backtest a single date"""
        logger.info(f"Backtesting {target_date}...")
        
        # Get games for this date
        games = self.get_games_for_date(target_date)
        
        if not games:
            logger.warning(f"No games found for {target_date}")
            return None
        
        # Get all players who played on this date
        all_players = {}
        actual_stats = {}
        
        for game in games:
            try:
                boxscore = self.get_box_score(game['game_id'])
                
                for player_data in boxscore['players']:
                    player_id = str(player_data['PLAYER_ID'])
                    
                    # Store actual stats for scoring
                    actual_stats[player_id] = player_data
                    
                    # Create player with projections (using data before target date)
                    if player_id not in all_players:
                        player = self.create_player_from_boxscore(player_data, target_date)
                        if player:
                            all_players[player_id] = player
                            
            except Exception as e:
                logger.error(f"Error processing game {game['game_id']}: {e}")
                continue
        
        if not all_players:
            logger.warning(f"No valid players found for {target_date}")
            return None
        
        logger.info(f"Found {len(all_players)} players for {target_date}")
        
        # Generate lineups using projections
        player_list = list(all_players.values())
        results = {}
        
        for platform in ['draftkings', 'fanduel']:
            platform_results = {
                'lineups': [],
                'actual_scores': [],
                'best_score': 0,
                'itm_count': 0
            }
            
            # Generate 5 lineups
            lineups = []
            
            # Strategy 1: Greedy
            lineup1 = self.engine.generate_lineup_greedy(player_list, platform)
            if lineup1:
                lineups.append(lineup1)
            
            # Strategy 2: Value
            lineup2 = self.engine.generate_lineup_value(player_list, platform)
            if lineup2:
                lineups.append(lineup2)
            
            # Strategies 3-5: Mixed
            for i in range(3):
                mixed = self.engine.generate_lineup_mixed(
                    player_list, platform, f"Mixed {i+1}"
                )
                if mixed:
                    lineups.append(mixed)
            
            # Score lineups with actual results
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
                            'actual': actual_stats.get(p.id, {}).get('PTS', 0)  # Just points for summary
                        }
                        for p in lineup.players
                    ]
                })
                
                platform_results['actual_scores'].append(actual_score)
                platform_results['best_score'] = max(
                    platform_results['best_score'], actual_score
                )
                
                # Check if ITM
                if actual_score >= self.ITM_THRESHOLDS[platform]:
                    platform_results['itm_count'] += 1
            
            results[platform] = platform_results
        
        result = {
            'date': target_date,
            'games_count': len(games),
            'players_count': len(all_players),
            'results': results
        }
        
        logger.info(f"Backtest complete for {target_date}")
        return result
    
    def run_backtest(self, sample_nights: Optional[int] = None) -> Dict[str, BacktestResults]:
        """Run full backtest over date range"""
        logger.info("Starting DFS backtesting...")
        logger.info(f"Date range: {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}")
        
        # Generate list of dates
        all_dates = []
        current_date = self.start_date
        
        while current_date <= self.end_date:
            all_dates.append(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
        
        logger.info(f"Total possible nights: {len(all_dates)}")
        
        # Sample dates if requested
        if sample_nights and sample_nights < len(all_dates):
            # Sample evenly across the range
            step = len(all_dates) // sample_nights
            test_dates = [all_dates[i] for i in range(0, len(all_dates), step)][:sample_nights]
            logger.info(f"Sampling {len(test_dates)} nights for faster testing")
        else:
            test_dates = all_dates
            logger.info(f"Testing all {len(test_dates)} nights")
        
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
        
        # Process each date
        successful_nights = 0
        
        for i, test_date in enumerate(test_dates):
            try:
                logger.info(f"Processing night {i+1}/{len(test_dates)}: {test_date}")
                
                result = self.backtest_single_date(test_date)
                
                if result:
                    successful_nights += 1
                    
                    # Process results for each platform
                    for platform in ['draftkings', 'fanduel']:
                        platform_data = result['results'][platform]
                        platform_results[platform]['nights'].append(result)
                        platform_results[platform]['total_nights'] += 1
                        platform_results[platform]['best_scores'].append(
                            platform_data['best_score']
                        )
                        
                        # Count ITM nights (nights with at least one ITM lineup)
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
                
                # Progress update every 5 nights
                if (i + 1) % 5 == 0:
                    logger.info(f"Progress: {i+1}/{len(test_dates)} nights completed. Success rate: {successful_nights}/{i+1}")
                
                # Save intermediate results every 10 nights
                if (i + 1) % 10 == 0:
                    self.save_intermediate_results(platform_results, i + 1)
                
            except Exception as e:
                logger.error(f"Error processing {test_date}: {e}")
                logger.error(traceback.format_exc())
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
        
        logger.info("Backtesting complete!")
        return final_results
    
    def save_intermediate_results(self, results: Dict, nights_completed: int):
        """Save intermediate results"""
        filename = f"dfs_backtest_intermediate_{nights_completed}.json"
        
        try:
            # Convert to JSON-serializable format
            json_results = {}
            for platform, data in results.items():
                json_results[platform] = {
                    'total_nights': data['total_nights'],
                    'itm_nights': data['itm_nights'],
                    'best_scores': data['best_scores'],
                    'strategy_results': data['strategy_results'],
                    'sample_nights': data['nights'][:5]  # Just save a sample
                }
            
            with open(filename, 'w') as f:
                json.dump(json_results, f, indent=2)
            
            logger.info(f"Intermediate results saved to {filename}")
            
        except Exception as e:
            logger.error(f"Failed to save intermediate results: {e}")
    
    def save_final_results(self, results: Dict[str, BacktestResults]):
        """Save final backtest results"""
        filename = "dfs_backtest_results.json"
        
        try:
            json_results = {}
            
            for platform, result in results.items():
                json_results[platform] = {
                    'nights': result.nights_tested,
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
            print("DFS BACKTEST RESULTS SUMMARY")
            print("="*80)
            
            for platform, result in results.items():
                print(f"\n{platform.upper()}:")
                print(f"  Nights tested: {result.nights_tested}")
                print(f"  ITM nights: {result.itm_nights} ({result.itm_rate:.2%})")
                print(f"  Avg best score: {result.avg_best_score:.1f}")
                print(f"  Best single score: {result.best_single_score:.1f}")
                print(f"  Worst night best: {result.worst_night_best:.1f}")
                print(f"  Total lineups: {result.total_lineups}")
                print("  Strategy hit rates:")
                for strategy, rate in result.strategy_hit_rates.items():
                    print(f"    {strategy}: {rate:.2%}")
            
        except Exception as e:
            logger.error(f"Failed to save final results: {e}")

def main():
    """Run the backtest"""
    backtester = DFSBacktester()
    
    # Run backtest with sampling for faster testing (20 nights)
    # Remove sample_nights parameter to test all nights (will be very slow)
    results = backtester.run_backtest(sample_nights=20)
    
    return results

if __name__ == "__main__":
    main()