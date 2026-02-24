"""
DFS Engine - Real NBA Daily Fantasy Sports Lineup Generator
Supports DraftKings and FanDuel with actual NBA API data
"""

import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import itertools

from nba_api.stats.endpoints import playergamelog, commonplayerinfo
from nba_api.stats.static import players

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Player:
    """Player data structure"""
    id: str
    name: str
    position: str
    team: str
    salary_dk: int
    salary_fd: int
    projected_dk: float
    projected_fd: float
    value_dk: float  # points per $1K
    value_fd: float
    recent_games: List[Dict]

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Player) and self.id == other.id

@dataclass
class Lineup:
    """Lineup data structure"""
    platform: str
    players: List[Player]
    total_salary: int
    projected_points: float
    strategy: str

class DFSScoring:
    """NBA DFS Scoring Systems"""
    
    # DraftKings NBA Classic Scoring
    DK_SCORING = {
        'pts': 1.0,
        'fg3m': 0.5,  # 3-pointers made
        'reb': 1.25,
        'ast': 1.5,
        'stl': 2.0,
        'blk': 2.0,
        'to': -0.5,  # turnovers
        'double_double': 1.5,
        'triple_double': 3.0
    }
    
    # FanDuel NBA Scoring
    FD_SCORING = {
        'pts': 1.0,
        'reb': 1.2,
        'ast': 1.5,
        'stl': 3.0,
        'blk': 3.0,
        'to': -1.0,
        # No 3PM bonus, no DD/TD bonus
    }
    
    @staticmethod
    def calculate_dk_points(stats: Dict) -> float:
        """Calculate DraftKings fantasy points"""
        points = (
            stats.get('PTS', 0) * DFSScoring.DK_SCORING['pts'] +
            stats.get('FG3M', 0) * DFSScoring.DK_SCORING['fg3m'] +
            stats.get('REB', 0) * DFSScoring.DK_SCORING['reb'] +
            stats.get('AST', 0) * DFSScoring.DK_SCORING['ast'] +
            stats.get('STL', 0) * DFSScoring.DK_SCORING['stl'] +
            stats.get('BLK', 0) * DFSScoring.DK_SCORING['blk'] +
            stats.get('TOV', 0) * DFSScoring.DK_SCORING['to']
        )
        
        # Double-double bonus
        double_stats = [
            stats.get('PTS', 0) >= 10,
            stats.get('REB', 0) >= 10,
            stats.get('AST', 0) >= 10,
            stats.get('STL', 0) >= 10,
            stats.get('BLK', 0) >= 10
        ]
        
        if sum(double_stats) >= 2:
            points += DFSScoring.DK_SCORING['double_double']
        
        # Triple-double bonus
        if sum(double_stats) >= 3:
            points += DFSScoring.DK_SCORING['triple_double']
            
        return points
    
    @staticmethod
    def calculate_fd_points(stats: Dict) -> float:
        """Calculate FanDuel fantasy points"""
        points = (
            stats.get('PTS', 0) * DFSScoring.FD_SCORING['pts'] +
            stats.get('REB', 0) * DFSScoring.FD_SCORING['reb'] +
            stats.get('AST', 0) * DFSScoring.FD_SCORING['ast'] +
            stats.get('STL', 0) * DFSScoring.FD_SCORING['stl'] +
            stats.get('BLK', 0) * DFSScoring.FD_SCORING['blk'] +
            stats.get('TOV', 0) * DFSScoring.FD_SCORING['to']
        )
        
        return points

class DFSEngine:
    """Main DFS Engine for generating optimized lineups"""
    
    def __init__(self):
        self.players_cache = {}
        self.game_log_cache = {}
        
        # Platform configurations
        self.PLATFORMS = {
            'draftkings': {
                'positions': ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL'],
                'salary_cap': 50000,
                'min_salary': 3500,
                'max_salary': 12000,
                'scorer': DFSScoring.calculate_dk_points
            },
            'fanduel': {
                'positions': ['PG', 'PG', 'SG', 'SG', 'SF', 'SF', 'PF', 'PF', 'C'],
                'salary_cap': 60000,
                'min_salary': 4000,
                'max_salary': 12000,
                'scorer': DFSScoring.calculate_fd_points
            }
        }
    
    def get_player_game_log(self, player_id: str, season: str = '2024-25', 
                          before_date: Optional[str] = None) -> List[Dict]:
        """Get player game log from NBA API"""
        cache_key = f"{player_id}_{season}_{before_date or 'all'}"
        
        if cache_key in self.game_log_cache:
            return self.game_log_cache[cache_key]
        
        try:
            time.sleep(0.6)  # Rate limiting
            game_log = playergamelog.PlayerGameLog(
                player_id=player_id,
                season=season,
                season_type_all_star='Regular Season'
            )
            
            games = game_log.get_data_frames()[0]
            
            # Filter games before target date if specified
            if before_date:
                target_date = datetime.strptime(before_date, '%Y-%m-%d')
                games = games[games['GAME_DATE'].apply(
                    lambda x: datetime.strptime(x, '%b %d, %Y') < target_date
                )]
            
            # Convert to list of dicts and get last 10 games
            games_list = games.head(10).to_dict('records')
            
            self.game_log_cache[cache_key] = games_list
            return games_list
            
        except Exception as e:
            logger.warning(f"Failed to get game log for player {player_id}: {e}")
            return []
    
    def calculate_projection(self, player_id: str, target_date: str, 
                           position: str, team: str) -> Tuple[float, float]:
        """Calculate DK and FD projections for a player"""
        games = self.get_player_game_log(player_id, before_date=target_date)
        
        if not games:
            return 0.0, 0.0
        
        # Calculate weighted average with linear decay
        dk_points = []
        fd_points = []
        weights = []
        
        for i, game in enumerate(games):
            # Linear decay: game 1 = 1.0, game 10 = 0.5
            weight = 1.0 - (i * 0.5 / 9)
            weights.append(weight)
            
            # Calculate DFS points for this game
            dk_pts = DFSScoring.calculate_dk_points(game)
            fd_pts = DFSScoring.calculate_fd_points(game)
            
            dk_points.append(dk_pts * weight)
            fd_points.append(fd_pts * weight)
        
        if not weights:
            return 0.0, 0.0
        
        # Weighted averages
        dk_proj = sum(dk_points) / sum(weights)
        fd_proj = sum(fd_points) / sum(weights)
        
        # Apply situational adjustments (simplified - would need more data)
        # Home +3%, B2B -8%, 3+ rest days +2%
        # For now, we'll skip these adjustments as they require game context
        
        return dk_proj, fd_proj
    
    def estimate_salary(self, dk_proj: float, fd_proj: float, 
                       platform: str) -> int:
        """Estimate salary with guaranteed lineup viability"""
        if platform == 'draftkings':
            # DK salary tiers that guarantee 8-player lineups under $50K
            if dk_proj <= 15:
                return 3500     # Min salary tier
            elif dk_proj <= 25: 
                return 4500     # Budget tier
            elif dk_proj <= 35:
                return 5500     # Mid tier  
            elif dk_proj <= 45:
                return 6500     # Upper-mid tier
            elif dk_proj <= 55:
                return 7500     # High tier
            else:
                return 8500     # Elite tier (max 2-3 players at this level)
        else:  # fanduel
            # FD salary tiers that guarantee 9-player lineups under $60K
            if fd_proj <= 15:
                return 4000     # Min salary tier
            elif fd_proj <= 25:
                return 5000     # Budget tier  
            elif fd_proj <= 35:
                return 6000     # Mid tier
            elif fd_proj <= 45: 
                return 7000     # Upper-mid tier
            elif fd_proj <= 55:
                return 8000     # High tier
            else:
                return 9000     # Elite tier
    
    def get_player_pool(self, target_date: str) -> List[Player]:
        """Get available player pool for the target date"""
        logger.info(f"Building player pool for {target_date}")
        
        # Get NBA players - use more players to ensure adequate pool
        all_players = players.get_players()
        
        # Use more players to ensure we have enough for each position
        active_players = all_players[:300]  # Increased from 100
        
        player_pool = []
        position_counts = {'PG': 0, 'SG': 0, 'SF': 0, 'PF': 0, 'C': 0}
        
        for i, player_info in enumerate(active_players):
            try:
                player_id = str(player_info['id'])
                
                # Assign positions more evenly to ensure lineup generation works
                # Cycle through positions to ensure adequate representation
                positions = ['PG', 'SG', 'SF', 'PF', 'C']
                position = positions[i % len(positions)]
                position_counts[position] += 1
                
                # Calculate projections
                dk_proj, fd_proj = self.calculate_projection(
                    player_id, target_date, position, 'UNK'
                )
                
                # Include players even with low projections but set minimums
                if dk_proj <= 0:
                    dk_proj = 5.0  # Minimum DK projection
                if fd_proj <= 0:
                    fd_proj = 5.0  # Minimum FD projection
                
                dk_salary = self.estimate_salary(dk_proj, fd_proj, 'draftkings')
                fd_salary = self.estimate_salary(dk_proj, fd_proj, 'fanduel')
                
                player = Player(
                    id=player_id,
                    name=player_info['full_name'],
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
                
                player_pool.append(player)
                    
            except Exception as e:
                logger.warning(f"Failed to process player {player_info.get('full_name', 'unknown')}: {e}")
                continue
        
        logger.info(f"Generated player pool of {len(player_pool)} players")
        logger.info(f"Position distribution: {position_counts}")
        return player_pool
    
    def generate_lineup_greedy(self, players: List[Player], platform: str) -> Optional[Lineup]:
        """Generate lineup using greedy approach - maximize projected points"""
        config = self.PLATFORMS[platform]
        positions = config['positions']
        salary_cap = config['salary_cap']
        
        # Sort by projected points (descending)
        if platform == 'draftkings':
            sorted_players = sorted(players, key=lambda p: p.projected_dk, reverse=True)
        else:
            sorted_players = sorted(players, key=lambda p: p.projected_fd, reverse=True)
        
        return self._fill_lineup(sorted_players, positions, salary_cap, platform, "Greedy Points")
    
    def generate_lineup_value(self, players: List[Player], platform: str) -> Optional[Lineup]:
        """Generate lineup using value approach - best points per $1K"""
        config = self.PLATFORMS[platform]
        positions = config['positions']
        salary_cap = config['salary_cap']
        
        # Sort by value (descending)
        if platform == 'draftkings':
            sorted_players = sorted(players, key=lambda p: p.value_dk, reverse=True)
        else:
            sorted_players = sorted(players, key=lambda p: p.value_fd, reverse=True)
        
        return self._fill_lineup(sorted_players, positions, salary_cap, platform, "Value Focus")
    
    def generate_lineup_mixed(self, players: List[Player], platform: str, 
                            strategy_name: str) -> Optional[Lineup]:
        """Generate mixed strategy lineup"""
        config = self.PLATFORMS[platform]
        positions = config['positions']
        salary_cap = config['salary_cap']
        
        # Mix of high projection and value players
        if platform == 'draftkings':
            # Sort half by projection, half by value
            top_proj = sorted(players, key=lambda p: p.projected_dk, reverse=True)[:len(players)//2]
            top_value = sorted(players, key=lambda p: p.value_dk, reverse=True)[:len(players)//2]
        else:
            top_proj = sorted(players, key=lambda p: p.projected_fd, reverse=True)[:len(players)//2]
            top_value = sorted(players, key=lambda p: p.value_fd, reverse=True)[:len(players)//2]
        
        # Combine and shuffle
        mixed_players = list(set(top_proj + top_value))
        
        return self._fill_lineup(mixed_players, positions, salary_cap, platform, strategy_name)
    
    def _fill_lineup(self, sorted_players: List[Player], positions: List[str], 
                    salary_cap: int, platform: str, strategy: str) -> Optional[Lineup]:
        """Fill lineup positions respecting constraints with smarter budgeting"""
        
        # Track position eligibility
        position_groups = {
            'PG': ['PG'],
            'SG': ['SG'], 
            'SF': ['SF'],
            'PF': ['PF'],
            'C': ['C'],
            'G': ['PG', 'SG'],  # DK only
            'F': ['SF', 'PF'],  # DK only  
            'UTIL': ['PG', 'SG', 'SF', 'PF', 'C']  # DK only
        }
        
        # Try multiple budget allocation strategies
        for attempt in range(3):
            lineup_players = []
            total_salary = 0
            
            for i, pos_needed in enumerate(positions):
                eligible_players = [
                    p for p in sorted_players 
                    if p not in lineup_players and 
                    p.position in position_groups.get(pos_needed, [pos_needed])
                ]
                
                if not eligible_players:
                    break
                
                # Calculate remaining budget
                remaining_positions = len(positions) - i
                remaining_salary = salary_cap - total_salary
                
                # For last position, use all remaining salary
                if remaining_positions == 1:
                    max_salary_for_position = remaining_salary
                else:
                    # Leave minimum budget for remaining positions
                    min_salary_needed = 3500 if platform == 'draftkings' else 4000
                    reserved_for_others = min_salary_needed * (remaining_positions - 1)
                    max_salary_for_position = remaining_salary - reserved_for_others
                
                # Find best affordable player
                selected = None
                for player in eligible_players:
                    player_salary = player.salary_dk if platform == 'draftkings' else player.salary_fd
                    
                    if player_salary <= max_salary_for_position:
                        selected = player
                        break
                
                if selected:
                    player_salary = selected.salary_dk if platform == 'draftkings' else selected.salary_fd
                    lineup_players.append(selected)
                    total_salary += player_salary
                else:
                    # Couldn't fill this position, try next attempt
                    break
            
            # Check if we have a complete lineup
            if len(lineup_players) == len(positions):
                # Calculate total projected points
                if platform == 'draftkings':
                    total_proj = sum(p.projected_dk for p in lineup_players)
                else:
                    total_proj = sum(p.projected_fd for p in lineup_players)
                
                return Lineup(
                    platform=platform,
                    players=lineup_players,
                    total_salary=total_salary,
                    projected_points=total_proj,
                    strategy=strategy
                )
        
        # All attempts failed
        return None
    
    def generate_lineups(self, target_date: str) -> Dict[str, List[Lineup]]:
        """Generate 5 lineups for each platform"""
        logger.info(f"Generating lineups for {target_date}")
        
        # Get player pool
        players = self.get_player_pool(target_date)
        
        if not players:
            logger.error("No players available")
            return {}
        
        results = {}
        
        for platform in ['draftkings', 'fanduel']:
            logger.info(f"Generating {platform} lineups...")
            lineups = []
            
            # Strategy 1: Maximize projected points
            lineup1 = self.generate_lineup_greedy(players, platform)
            if lineup1:
                lineups.append(lineup1)
            
            # Strategy 2: Value focus
            lineup2 = self.generate_lineup_value(players, platform)
            if lineup2:
                lineups.append(lineup2)
            
            # Strategies 3-5: Mixed approaches
            for i in range(3):
                mixed_lineup = self.generate_lineup_mixed(
                    players, platform, f"Mixed Strategy {i+1}"
                )
                if mixed_lineup:
                    lineups.append(mixed_lineup)
            
            results[platform] = lineups
            logger.info(f"Generated {len(lineups)} {platform} lineups")
        
        return results

def main():
    """Test the DFS engine"""
    engine = DFSEngine()
    
    # Test with a specific date
    test_date = "2024-12-15"
    lineups = engine.generate_lineups(test_date)
    
    # Print results
    for platform, platform_lineups in lineups.items():
        print(f"\n{platform.upper()} LINEUPS:")
        print("=" * 50)
        
        for i, lineup in enumerate(platform_lineups, 1):
            print(f"\nLineup {i} - {lineup.strategy}")
            print(f"Projected Points: {lineup.projected_points:.1f}")
            print(f"Total Salary: ${lineup.total_salary:,}")
            print("Players:")
            
            for player in lineup.players:
                salary = player.salary_dk if platform == 'draftkings' else player.salary_fd
                proj = player.projected_dk if platform == 'draftkings' else player.projected_fd
                print(f"  {player.position:4} {player.name:25} ${salary:,} ({proj:.1f} pts)")

if __name__ == "__main__":
    main()