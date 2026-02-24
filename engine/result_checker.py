"""
Result Checker module for ParlayGuarantee Engine
Checks final scores and verifies pick outcomes for tracking performance
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from nba_api.stats.endpoints import scoreboardv2 as scoreboard
from config import *

# Configure logging
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)


@dataclass
class GameResult:
    """Final result of a game"""
    game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    final_status: str
    game_date: str


@dataclass
class PickResult:
    """Result of a single pick"""
    game: str
    pick: str
    pick_type: str
    outcome: str  # 'WIN', 'LOSS', 'PUSH', 'PENDING'
    actual_result: str
    reasoning: str


@dataclass
class ParlayResult:
    """Result of a complete parlay"""
    parlay_id: int
    legs: int
    total_picks: int
    winning_picks: int
    losing_picks: int
    push_picks: int
    pending_picks: int
    overall_outcome: str  # 'WIN', 'LOSS', 'PENDING'
    pick_results: List[PickResult]


class ResultChecker:
    """Checks game results and verifies pick outcomes"""
    
    def __init__(self):
        logger.info("ResultChecker initialized")
    
    def get_game_results(self, game_date: str) -> List[GameResult]:
        """Get final results for games on a specific date"""
        try:
            logger.info(f"Fetching game results for {game_date}")
            
            # Get scoreboard for the date
            scoreboard_data = scoreboard.ScoreBoard(game_date=game_date)
            games_data = scoreboard_data.get_normalized_dict()
            
            results = []
            if 'GameHeader' in games_data:
                for game in games_data['GameHeader']:
                    # Only process completed games
                    if game['GAME_STATUS_TEXT'] == 'Final':
                        result = GameResult(
                            game_id=game['GAME_ID'],
                            home_team=game['HOME_TEAM_NAME'],
                            away_team=game['VISITOR_TEAM_NAME'],
                            home_score=0,  # Need to get from detailed stats
                            away_score=0,  # Need to get from detailed stats
                            final_status=game['GAME_STATUS_TEXT'],
                            game_date=game_date
                        )
                        results.append(result)
            
            # Get detailed scores from LineScore
            if 'LineScore' in games_data:
                score_lookup = {}
                for line in games_data['LineScore']:
                    game_id = line['GAME_ID']
                    team_id = line['TEAM_ID']
                    points = line['PTS'] if line['PTS'] is not None else 0
                    
                    if game_id not in score_lookup:
                        score_lookup[game_id] = {}
                    score_lookup[game_id][team_id] = points
                
                # Update results with scores
                for result in results:
                    if result.game_id in score_lookup:
                        scores = score_lookup[result.game_id]
                        if len(scores) == 2:
                            # Find home and away scores
                            for game in games_data['GameHeader']:
                                if game['GAME_ID'] == result.game_id:
                                    home_team_id = game['HOME_TEAM_ID']
                                    away_team_id = game['VISITOR_TEAM_ID']
                                    
                                    result.home_score = scores.get(home_team_id, 0)
                                    result.away_score = scores.get(away_team_id, 0)
                                    break
            
            logger.info(f"Found {len(results)} completed games for {game_date}")
            return results
            
        except Exception as e:
            logger.error(f"Error fetching game results: {str(e)}")
            return []
    
    def check_spread_pick(self, pick: str, game_result: GameResult) -> Tuple[str, str]:
        """Check if a spread pick won, lost, or pushed"""
        try:
            # Parse spread pick (e.g., "Celtics -4.5")
            if '-' in pick:
                parts = pick.split('-')
                team = parts[0].strip()
                spread = float(parts[1].strip())
                
                # Determine if this team is home or away
                if team in game_result.home_team:
                    team_score = game_result.home_score
                    opp_score = game_result.away_score
                else:
                    team_score = game_result.away_score
                    opp_score = game_result.home_score
                
                # Calculate cover
                cover_margin = team_score - opp_score + spread
                
                if cover_margin > 0:
                    return 'WIN', f"{team} covered {spread} point spread"
                elif cover_margin < 0:
                    return 'LOSS', f"{team} failed to cover {spread} point spread"
                else:
                    return 'PUSH', f"Spread push at {spread}"
            
            elif '+' in pick:
                parts = pick.split('+')
                team = parts[0].strip()
                spread = float(parts[1].strip())
                
                # Similar logic for + spreads
                if team in game_result.home_team:
                    team_score = game_result.home_score
                    opp_score = game_result.away_score
                else:
                    team_score = game_result.away_score
                    opp_score = game_result.home_score
                
                cover_margin = team_score - opp_score - spread
                
                if cover_margin > 0:
                    return 'WIN', f"{team} covered +{spread} point spread"
                elif cover_margin < 0:
                    return 'LOSS', f"{team} failed to cover +{spread} point spread"
                else:
                    return 'PUSH', f"Spread push at +{spread}"
            
            else:
                return 'PENDING', 'Could not parse spread pick'
                
        except Exception as e:
            logger.error(f"Error checking spread pick: {str(e)}")
            return 'PENDING', f'Error parsing pick: {str(e)}'
    
    def check_moneyline_pick(self, pick: str, game_result: GameResult) -> Tuple[str, str]:
        """Check if a moneyline pick won or lost"""
        try:
            # Parse moneyline pick (e.g., "Celtics ML")
            team = pick.replace('ML', '').strip()
            
            # Determine if team won
            if team in game_result.home_team:
                team_score = game_result.home_score
                opp_score = game_result.away_score
            else:
                team_score = game_result.away_score
                opp_score = game_result.home_score
            
            if team_score > opp_score:
                return 'WIN', f"{team} won {team_score}-{opp_score}"
            elif team_score < opp_score:
                return 'LOSS', f"{team} lost {team_score}-{opp_score}"
            else:
                return 'PUSH', f"Game tied {team_score}-{opp_score}"
                
        except Exception as e:
            logger.error(f"Error checking moneyline pick: {str(e)}")
            return 'PENDING', f'Error parsing pick: {str(e)}'
    
    def check_total_pick(self, pick: str, game_result: GameResult) -> Tuple[str, str]:
        """Check if a total (over/under) pick won, lost, or pushed"""
        try:
            total_points = game_result.home_score + game_result.away_score
            
            if pick.startswith('Over'):
                line = float(pick.split()[-1])
                if total_points > line:
                    return 'WIN', f"Over {line} hit with {total_points} total points"
                elif total_points < line:
                    return 'LOSS', f"Over {line} missed with {total_points} total points"
                else:
                    return 'PUSH', f"Total push at {line} with {total_points} points"
            
            elif pick.startswith('Under'):
                line = float(pick.split()[-1])
                if total_points < line:
                    return 'WIN', f"Under {line} hit with {total_points} total points"
                elif total_points > line:
                    return 'LOSS', f"Under {line} missed with {total_points} total points"
                else:
                    return 'PUSH', f"Total push at {line} with {total_points} points"
            
            else:
                return 'PENDING', 'Could not parse total pick'
                
        except Exception as e:
            logger.error(f"Error checking total pick: {str(e)}")
            return 'PENDING', f'Error parsing pick: {str(e)}'
    
    def check_pick_result(self, pick: Dict, game_results: List[GameResult]) -> PickResult:
        """Check the result of a single pick"""
        game_name = pick['game']
        pick_text = pick['pick']
        pick_type = pick['type']
        
        # Find matching game result
        matching_result = None
        for result in game_results:
            result_name = f"{result.away_team} vs {result.home_team}"
            alt_name = f"{result.home_team} vs {result.away_team}"
            
            if game_name in [result_name, alt_name]:
                matching_result = result
                break
        
        if not matching_result:
            return PickResult(
                game=game_name,
                pick=pick_text,
                pick_type=pick_type,
                outcome='PENDING',
                actual_result='Game not found or not completed',
                reasoning=pick.get('reasoning', '')
            )
        
        # Check pick based on type
        if pick_type == 'spread':
            outcome, explanation = self.check_spread_pick(pick_text, matching_result)
        elif pick_type == 'moneyline':
            outcome, explanation = self.check_moneyline_pick(pick_text, matching_result)
        elif pick_type == 'total':
            outcome, explanation = self.check_total_pick(pick_text, matching_result)
        else:
            outcome, explanation = 'PENDING', 'Unknown pick type'
        
        return PickResult(
            game=game_name,
            pick=pick_text,
            pick_type=pick_type,
            outcome=outcome,
            actual_result=explanation,
            reasoning=pick.get('reasoning', '')
        )
    
    def check_parlay_results(self, parlays_file: str, game_date: str) -> List[ParlayResult]:
        """Check results for all parlays in a file"""
        try:
            logger.info(f"Checking parlay results from {parlays_file}")
            
            # Load parlay data
            with open(parlays_file, 'r', encoding='utf-8') as f:
                parlay_data = json.load(f)
            
            # Get game results
            game_results = self.get_game_results(game_date)
            
            # Check each parlay
            parlay_results = []
            for parlay in parlay_data.get('parlays', []):
                pick_results = []
                win_count = 0
                loss_count = 0
                push_count = 0
                pending_count = 0
                
                # Check each pick in the parlay
                for pick in parlay['picks']:
                    result = self.check_pick_result(pick, game_results)
                    pick_results.append(result)
                    
                    if result.outcome == 'WIN':
                        win_count += 1
                    elif result.outcome == 'LOSS':
                        loss_count += 1
                    elif result.outcome == 'PUSH':
                        push_count += 1
                    else:
                        pending_count += 1
                
                # Determine parlay outcome
                total_picks = len(parlay['picks'])
                if pending_count > 0:
                    overall_outcome = 'PENDING'
                elif loss_count > 0:
                    overall_outcome = 'LOSS'  # Any loss kills the parlay
                elif push_count > 0 and win_count + push_count == total_picks:
                    overall_outcome = 'PUSH'  # All wins or pushes
                elif win_count == total_picks:
                    overall_outcome = 'WIN'  # All wins
                else:
                    overall_outcome = 'PENDING'
                
                parlay_result = ParlayResult(
                    parlay_id=parlay['id'],
                    legs=parlay['legs'],
                    total_picks=total_picks,
                    winning_picks=win_count,
                    losing_picks=loss_count,
                    push_picks=push_count,
                    pending_picks=pending_count,
                    overall_outcome=overall_outcome,
                    pick_results=pick_results
                )
                
                parlay_results.append(parlay_result)
            
            logger.info(f"Checked {len(parlay_results)} parlays")
            return parlay_results
            
        except Exception as e:
            logger.error(f"Error checking parlay results: {str(e)}")
            return []
    
    def generate_results_report(self, parlay_results: List[ParlayResult], output_file: str = None) -> Dict:
        """Generate a comprehensive results report"""
        logger.info("Generating results report")
        
        # Calculate summary statistics
        total_parlays = len(parlay_results)
        winning_parlays = sum(1 for p in parlay_results if p.overall_outcome == 'WIN')
        losing_parlays = sum(1 for p in parlay_results if p.overall_outcome == 'LOSS')
        push_parlays = sum(1 for p in parlay_results if p.overall_outcome == 'PUSH')
        pending_parlays = sum(1 for p in parlay_results if p.overall_outcome == 'PENDING')
        
        # Calculate individual pick accuracy
        total_picks = sum(p.total_picks for p in parlay_results)
        total_wins = sum(p.winning_picks for p in parlay_results)
        total_losses = sum(p.losing_picks for p in parlay_results)
        
        pick_accuracy = (total_wins / (total_wins + total_losses)) * 100 if (total_wins + total_losses) > 0 else 0
        parlay_success_rate = (winning_parlays / total_parlays) * 100 if total_parlays > 0 else 0
        
        # Create report
        report = {
            'generated_at': datetime.now().isoformat() + 'Z',
            'summary': {
                'total_parlays': total_parlays,
                'winning_parlays': winning_parlays,
                'losing_parlays': losing_parlays,
                'push_parlays': push_parlays,
                'pending_parlays': pending_parlays,
                'parlay_success_rate': round(parlay_success_rate, 1),
                'total_individual_picks': total_picks,
                'individual_pick_accuracy': round(pick_accuracy, 1)
            },
            'parlay_details': []
        }
        
        # Add details for each parlay
        for result in parlay_results:
            parlay_detail = {
                'parlay_id': result.parlay_id,
                'legs': result.legs,
                'outcome': result.overall_outcome,
                'record': f"{result.winning_picks}-{result.losing_picks}-{result.push_picks}",
                'picks': []
            }
            
            for pick_result in result.pick_results:
                pick_detail = {
                    'game': pick_result.game,
                    'pick': pick_result.pick,
                    'type': pick_result.pick_type,
                    'outcome': pick_result.outcome,
                    'result': pick_result.actual_result
                }
                parlay_detail['picks'].append(pick_detail)
            
            report['parlay_details'].append(parlay_detail)
        
        # Save report if output file specified
        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                logger.info(f"Results report saved to {output_file}")
            except Exception as e:
                logger.error(f"Error saving results report: {str(e)}")
        
        return report
    
    def update_track_record(self, results_report: Dict, history_dir: str = "history") -> None:
        """Update historical track record with new results"""
        try:
            import os
            
            # Create history directory if it doesn't exist
            os.makedirs(history_dir, exist_ok=True)
            
            # Save daily results
            date_str = datetime.now().strftime('%Y-%m-%d')
            daily_file = os.path.join(history_dir, f"results_{date_str}.json")
            
            with open(daily_file, 'w', encoding='utf-8') as f:
                json.dump(results_report, f, indent=2, ensure_ascii=False)
            
            # Update cumulative track record
            track_record_file = os.path.join(history_dir, "track_record.json")
            
            if os.path.exists(track_record_file):
                with open(track_record_file, 'r', encoding='utf-8') as f:
                    track_record = json.load(f)
            else:
                track_record = {
                    'started_date': date_str,
                    'total_days': 0,
                    'cumulative_stats': {
                        'total_parlays': 0,
                        'winning_parlays': 0,
                        'losing_parlays': 0,
                        'push_parlays': 0,
                        'overall_success_rate': 0,
                        'total_picks': 0,
                        'pick_accuracy': 0
                    },
                    'daily_history': []
                }
            
            # Update cumulative stats
            summary = results_report['summary']
            track_record['total_days'] += 1
            track_record['cumulative_stats']['total_parlays'] += summary['total_parlays']
            track_record['cumulative_stats']['winning_parlays'] += summary['winning_parlays']
            track_record['cumulative_stats']['losing_parlays'] += summary['losing_parlays']
            track_record['cumulative_stats']['push_parlays'] += summary['push_parlays']
            track_record['cumulative_stats']['total_picks'] += summary['total_individual_picks']
            
            # Recalculate rates
            cum_stats = track_record['cumulative_stats']
            total_decided_parlays = cum_stats['winning_parlays'] + cum_stats['losing_parlays']
            total_decided_picks = cum_stats['total_picks'] - summary.get('pending_picks', 0)
            
            if total_decided_parlays > 0:
                cum_stats['overall_success_rate'] = round((cum_stats['winning_parlays'] / total_decided_parlays) * 100, 1)
            
            if total_decided_picks > 0:
                # This would need more sophisticated tracking of individual pick wins/losses
                cum_stats['pick_accuracy'] = summary['individual_pick_accuracy']
            
            # Add daily entry
            track_record['daily_history'].append({
                'date': date_str,
                'parlays': summary['total_parlays'],
                'wins': summary['winning_parlays'],
                'losses': summary['losing_parlays'],
                'success_rate': summary['parlay_success_rate']
            })
            
            # Save updated track record
            with open(track_record_file, 'w', encoding='utf-8') as f:
                json.dump(track_record, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Track record updated: {cum_stats['overall_success_rate']}% success rate over {track_record['total_days']} days")
            
        except Exception as e:
            logger.error(f"Error updating track record: {str(e)}")


if __name__ == "__main__":
    # Test result checker
    checker = ResultChecker()
    
    # Test with a sample date (would need actual picks file)
    test_date = "2026-02-15"
    
    print(f"Testing result checker for {test_date}")
    
    # Get game results
    results = checker.get_game_results(test_date)
    print(f"Found {len(results)} completed games")
    
    for result in results:
        print(f"{result.away_team} @ {result.home_team}: {result.away_score}-{result.home_score}")
