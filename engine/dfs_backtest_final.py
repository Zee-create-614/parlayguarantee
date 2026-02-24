#!/usr/bin/env python3
"""
DFS Backtest Engine - Complete Working Implementation

This script backtests DraftKings and FanDuel NBA lineups using historical data.
It fetches real box scores, calculates actual fantasy scores, builds lineups
using a greedy algorithm, and evaluates performance.

Key Features:
- Real NBA data via nba_api
- Accurate DK/FD scoring with bonuses
- Position eligibility mapping
- Multiple lineup construction strategies
- Rate limiting and retry logic
- Comprehensive results tracking
"""

import json
import time
import random
import traceback
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

# NBA API imports
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3

@dataclass
class Player:
    """Player data structure"""
    person_id: str
    name: str
    position: str
    team: str
    stats: Dict[str, Any]
    dk_score: float = 0.0
    fd_score: float = 0.0
    projected_dk: float = 0.0
    projected_fd: float = 0.0
    estimated_salary: int = 0
    
    def __post_init__(self):
        self.calculate_scores()
        self.generate_projections()
        self.estimate_salary()
    
    def calculate_scores(self):
        """Calculate actual DK and FD fantasy scores"""
        stats = self.stats
        
        pts = stats.get('points', 0) or 0
        tpm = stats.get('threePointersMade', 0) or 0
        reb = stats.get('reboundsTotal', 0) or 0
        ast = stats.get('assists', 0) or 0
        stl = stats.get('steals', 0) or 0
        blk = stats.get('blocks', 0) or 0
        to = stats.get('turnovers', 0) or 0
        
        # DraftKings scoring with bonuses
        self.dk_score = (pts + tpm*0.5 + reb*1.25 + ast*1.5 + 
                        stl*2 + blk*2 + to*(-0.5))
        
        # Double-double and triple-double bonuses
        dd_categories = [pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10]
        dd_count = sum(dd_categories)
        
        if dd_count >= 2:
            self.dk_score += 1.5  # Double-double bonus
        if dd_count >= 3:
            self.dk_score += 3.0  # Triple-double bonus (additional)
        
        # FanDuel scoring (no bonuses)
        self.fd_score = (pts + reb*1.2 + ast*1.5 + stl*3 + blk*3 + to*(-1))
    
    def generate_projections(self):
        """Generate fake projections based on actual scores"""
        # Simulate projection error with 70-130% of actual
        self.projected_dk = self.dk_score * random.uniform(0.7, 1.3)
        self.projected_fd = self.fd_score * random.uniform(0.7, 1.3)
    
    def estimate_salary(self):
        """Estimate salary based on projected DK score"""
        base_salary = int(self.projected_dk * 200 + 3000)
        self.estimated_salary = max(3500, min(12000, base_salary))
    
    def get_position_eligibility(self) -> List[str]:
        """Get list of eligible positions for this player"""
        pos = (self.position or '').upper().strip()
        
        # Position mappings based on API position
        if pos in ['G', 'G-F']:
            return ['PG', 'SG', 'G', 'UTIL']
        elif pos in ['F', 'F-G']:
            return ['SF', 'PF', 'F', 'UTIL']
        elif pos in ['C', 'C-F', 'F-C']:
            return ['C', 'PF', 'F', 'UTIL']
        else:
            # Empty or unknown position
            return ['UTIL']

class DFSBacktester:
    """Main backtesting engine"""
    
    def __init__(self):
        self.test_dates = [
            '2024-12-01', '2024-12-03', '2024-12-05', '2024-12-10',
            '2024-12-15', '2024-12-20', '2024-12-25', '2024-12-30',
            '2025-01-05', '2025-01-10'
        ]
        
        # Lineup configurations
        self.dk_config = {
            'positions': ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL'],
            'salary_cap': 50000,
            'num_players': 8
        }
        
        self.fd_config = {
            'positions': ['PG', 'PG', 'SG', 'SG', 'SF', 'SF', 'PF', 'PF', 'C'],
            'salary_cap': 60000,
            'num_players': 9
        }
        
        self.results = {
            'draftkings': {
                'nights': 0,
                'itm_nights': 0,
                'total_lineups': 0,
                'successful_lineups': 0,
                'scores': [],
                'best_scores': []
            },
            'fanduel': {
                'nights': 0,
                'itm_nights': 0,
                'total_lineups': 0,
                'successful_lineups': 0,
                'scores': [],
                'best_scores': []
            }
        }
    
    def make_api_call_with_retry(self, api_call, max_retries=3):
        """Make API call with retry logic and rate limiting"""
        for attempt in range(max_retries):
            try:
                time.sleep(2)  # Rate limiting
                result = api_call()
                return result
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  API call failed (attempt {attempt + 1}), retrying in 5s...")
                    time.sleep(5)
                else:
                    print(f"  API call failed after {max_retries} attempts: {e}")
                    return None
    
    def get_games_for_date(self, date_str: str) -> List[str]:
        """Get list of game IDs for a given date"""
        print(f"  Fetching games for {date_str}...")
        
        def api_call():
            sb = scoreboardv2.ScoreboardV2(game_date=date_str)
            return sb.get_normalized_dict()
        
        data = self.make_api_call_with_retry(api_call)
        if not data:
            return []
        
        games = data.get('GameHeader', [])
        game_ids = [game['GAME_ID'] for game in games]
        print(f"  Found {len(game_ids)} games")
        return game_ids
    
    def get_players_from_game(self, game_id: str) -> List[Player]:
        """Get all players and stats from a game"""
        def api_call():
            bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
            return bs.get_dict()
        
        data = self.make_api_call_with_retry(api_call)
        if not data:
            return []
        
        players = []
        box_score = data.get('boxScoreTraditional', {})
        
        # Process both teams
        for team_key in ['homeTeam', 'awayTeam']:
            team = box_score.get(team_key, {})
            team_name = team.get('teamName', 'Unknown')
            team_players = team.get('players', [])
            
            for player_data in team_players:
                # Skip players with no minutes
                minutes = player_data.get('statistics', {}).get('minutes', '')
                if not minutes or minutes == '0:00':
                    continue
                
                player = Player(
                    person_id=str(player_data.get('personId', '')),
                    name=f"{player_data.get('firstName', '')} {player_data.get('familyName', '')}".strip(),
                    position=player_data.get('position', ''),
                    team=team_name,
                    stats=player_data.get('statistics', {})
                )
                
                if player.name and player.dk_score > 0:  # Valid player
                    players.append(player)
        
        return players
    
    def get_all_players_for_date(self, date_str: str) -> List[Player]:
        """Get all players for all games on a given date"""
        game_ids = self.get_games_for_date(date_str)
        if not game_ids:
            return []
        
        all_players = []
        for i, game_id in enumerate(game_ids):
            print(f"  Fetching game {i+1}/{len(game_ids)}: {game_id}")
            players = self.get_players_from_game(game_id)
            all_players.extend(players)
        
        print(f"  Total players collected: {len(all_players)}")
        return all_players
    
    def build_lineup_greedy(self, players: List[Player], positions: List[str], 
                           salary_cap: int, sort_key) -> Optional[List[Player]]:
        """Build a lineup using greedy algorithm"""
        # Sort players by value (projected score / salary)
        available_players = sorted(players, key=sort_key, reverse=True)
        lineup = []
        used_players = set()
        remaining_salary = salary_cap
        
        for pos in positions:
            best_player = None
            
            for player in available_players:
                if (player.person_id in used_players or 
                    player.estimated_salary > remaining_salary):
                    continue
                
                # Check position eligibility
                if pos in player.get_position_eligibility():
                    best_player = player
                    break
            
            if best_player:
                lineup.append(best_player)
                used_players.add(best_player.person_id)
                remaining_salary -= best_player.estimated_salary
            else:
                # Cannot fill this position
                return None
        
        return lineup
    
    def generate_lineups(self, players: List[Player], platform: str) -> List[List[Player]]:
        """Generate 5 different lineups using various strategies"""
        config = self.dk_config if platform == 'draftkings' else self.fd_config
        positions = config['positions']
        salary_cap = config['salary_cap']
        
        lineups = []
        
        # Strategy 1: Pure greedy by value (projected / salary)
        lineup = self.build_lineup_greedy(
            players, positions, salary_cap,
            lambda p: p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0
        )
        if lineup:
            lineups.append(lineup)
        
        # Strategy 2: Start with highest projected, then greedy
        sorted_players = sorted(players, key=lambda p: p.projected_dk, reverse=True)
        if sorted_players:
            # Find the highest projected player we can afford
            for top_player in sorted_players[:10]:  # Try top 10
                if top_player.estimated_salary <= salary_cap:
                    # Build lineup starting with this player
                    temp_positions = positions.copy()
                    temp_salary = salary_cap - top_player.estimated_salary
                    
                    # Remove one position this player can fill
                    eligible_positions = top_player.get_position_eligibility()
                    for pos in temp_positions:
                        if pos in eligible_positions:
                            temp_positions.remove(pos)
                            break
                    
                    # Fill remaining positions
                    remaining_players = [p for p in players if p.person_id != top_player.person_id]
                    partial_lineup = self.build_lineup_greedy(
                        remaining_players, temp_positions, temp_salary,
                        lambda p: p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0
                    )
                    
                    if partial_lineup:
                        lineup = [top_player] + partial_lineup
                        lineups.append(lineup)
                        break
        
        # Strategies 3-5: Randomized position order
        for _ in range(3):
            random_positions = positions.copy()
            random.shuffle(random_positions)
            lineup = self.build_lineup_greedy(
                players, random_positions, salary_cap,
                lambda p: p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0
            )
            if lineup:
                lineups.append(lineup)
        
        return lineups
    
    def score_lineup(self, lineup: List[Player], platform: str) -> float:
        """Calculate total fantasy score for a lineup using actual stats"""
        if platform == 'draftkings':
            return sum(player.dk_score for player in lineup)
        else:
            return sum(player.fd_score for player in lineup)
    
    def run_backtest_for_date(self, date_str: str):
        """Run backtest for a single date"""
        print(f"\n{'='*50}")
        print(f"BACKTESTING: {date_str}")
        print(f"{'='*50}")
        
        # Get all players for this date
        players = self.get_all_players_for_date(date_str)
        if not players:
            print("No players found for this date!")
            return
        
        # Show top 5 DK scorers for verification
        top_dk_players = sorted(players, key=lambda p: p.dk_score, reverse=True)[:5]
        print(f"\nTop 5 DK Scorers:")
        for i, player in enumerate(top_dk_players, 1):
            stats = player.stats
            print(f"{i}. {player.name} ({player.team}) - {player.dk_score:.1f} DK pts")
            print(f"   Stats: {stats.get('points', 0)}pts, {stats.get('threePointersMade', 0)}x3pm, "
                  f"{stats.get('reboundsTotal', 0)}reb, {stats.get('assists', 0)}ast, "
                  f"{stats.get('steals', 0)}stl, {stats.get('blocks', 0)}blk, {stats.get('turnovers', 0)}to")
        
        # Test both platforms
        for platform in ['draftkings', 'fanduel']:
            print(f"\n{platform.upper()} LINEUPS:")
            print("-" * 30)
            
            lineups = self.generate_lineups(players, platform)
            platform_results = self.results[platform]
            
            if not lineups:
                print("Failed to generate any valid lineups!")
                continue
            
            platform_results['nights'] += 1
            platform_results['total_lineups'] += len(lineups)
            
            best_score = 0
            night_itm = False
            
            for i, lineup in enumerate(lineups, 1):
                total_salary = sum(player.estimated_salary for player in lineup)
                actual_score = self.score_lineup(lineup, platform)
                
                print(f"\nLineup {i}:")
                for j, player in enumerate(lineup, 1):
                    pos_eligible = '/'.join(player.get_position_eligibility())
                    print(f"  {j}. {player.name} ({player.team}) - ${player.estimated_salary} - {pos_eligible}")
                    if platform == 'draftkings':
                        print(f"     Projected: {player.projected_dk:.1f}, Actual: {player.dk_score:.1f}")
                    else:
                        print(f"     Projected: {player.projected_fd:.1f}, Actual: {player.fd_score:.1f}")
                
                print(f"Total Salary: ${total_salary:,}")
                print(f"Total Actual Score: {actual_score:.1f}")
                
                # Simple ITM check (score > 100 for DK, > 120 for FD)
                itm_threshold = 100 if platform == 'draftkings' else 120
                is_itm = actual_score >= itm_threshold
                print(f"ITM Status: {'✅ IN THE MONEY' if is_itm else '❌ OUT OF MONEY'}")
                
                if is_itm:
                    night_itm = True
                
                platform_results['successful_lineups'] += 1
                platform_results['scores'].append(actual_score)
                best_score = max(best_score, actual_score)
            
            if night_itm:
                platform_results['itm_nights'] += 1
            
            platform_results['best_scores'].append(best_score)
            print(f"\nBest {platform} score for the night: {best_score:.1f}")
    
    def run_full_backtest(self):
        """Run backtest across all test dates"""
        print("Starting DFS Backtest...")
        print(f"Testing {len(self.test_dates)} dates: {', '.join(self.test_dates)}")
        
        start_time = time.time()
        
        try:
            for date_str in self.test_dates:
                try:
                    self.run_backtest_for_date(date_str)
                except Exception as e:
                    print(f"\nError processing {date_str}: {e}")
                    print(traceback.format_exc())
                    continue
        
        except KeyboardInterrupt:
            print("\n\nBacktest interrupted by user!")
        
        finally:
            # Calculate final results
            self.calculate_final_results()
            
            # Save results
            self.save_results()
            
            end_time = time.time()
            print(f"\nBacktest completed in {end_time - start_time:.1f} seconds")
    
    def calculate_final_results(self):
        """Calculate summary statistics"""
        print(f"\n{'='*50}")
        print("FINAL RESULTS")
        print(f"{'='*50}")
        
        for platform in ['draftkings', 'fanduel']:
            results = self.results[platform]
            
            if results['nights'] > 0:
                itm_rate = (results['itm_nights'] / results['nights']) * 100
                avg_best_score = sum(results['best_scores']) / len(results['best_scores'])
                avg_all_scores = sum(results['scores']) / len(results['scores']) if results['scores'] else 0
                
                results['itm_rate'] = f"{itm_rate:.1f}%"
                results['avg_best_score'] = f"{avg_best_score:.1f}"
                results['avg_all_scores'] = f"{avg_all_scores:.1f}"
                
                print(f"\n{platform.upper()}:")
                print(f"  Nights tested: {results['nights']}")
                print(f"  ITM nights: {results['itm_nights']}")
                print(f"  ITM rate: {results['itm_rate']}")
                print(f"  Total lineups: {results['total_lineups']}")
                print(f"  Successful lineups: {results['successful_lineups']}")
                print(f"  Average best score per night: {results['avg_best_score']}")
                print(f"  Average score (all lineups): {results['avg_all_scores']}")
            else:
                print(f"\n{platform.upper()}: No successful nights")
    
    def save_results(self):
        """Save results to JSON file"""
        # Clean up results for JSON serialization
        clean_results = {}
        for platform, data in self.results.items():
            clean_results[platform] = {
                'nights': data['nights'],
                'itm_nights': data['itm_nights'],
                'itm_rate': data.get('itm_rate', '0%'),
                'avg_best_score': data.get('avg_best_score', '0'),
                'avg_all_scores': data.get('avg_all_scores', '0'),
                'total_lineups': data['total_lineups'],
                'successful_lineups': data['successful_lineups']
            }
        
        output_file = 'dfs_backtest_results_final.json'
        with open(output_file, 'w') as f:
            json.dump(clean_results, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")

def main():
    """Main execution function"""
    print("DFS Backtest Engine v1.0")
    print("=" * 50)
    
    # Initialize and run backtest
    backtester = DFSBacktester()
    backtester.run_full_backtest()

if __name__ == "__main__":
    main()