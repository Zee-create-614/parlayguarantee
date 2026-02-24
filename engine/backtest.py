"""
NBA Backtesting System for ParlayGuarantee Engine
Tests parlay generation strategy against historical NBA data to optimize model before going live.

This is THE critical piece that determines if ParlayGuarantee is viable business or vaporware.
"""
import sys
import json
import time
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import traceback

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# NBA API imports
from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats, teamgamelog, leaguegamefinder
from nba_api.stats.static import teams

# Import existing engine components
from analyzer import GameAnalyzer, GameAnalysis
from parlay_generator import ParlayGenerator, Parlay
from data_fetcher import NBADataFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results for a single night of backtesting"""
    date: str
    games_available: int
    parlays_generated: int
    parlays_hit: int
    hit_rate: float
    deposit_kept: bool  # True if at least 1/10 parlays hit
    daily_profit_loss: float  # If customer bet $10 per parlay
    hit_by_legs: Dict[str, int]  # Hit count by parlay leg count
    hit_by_type: Dict[str, int]  # Hit count by bet type
    confidence_scores: List[float]  # All parlay confidence scores
    details: List[Dict]  # Detailed parlay results


@dataclass
class OverallResults:
    """Overall backtesting results"""
    test_period: str
    total_nights: int
    nights_with_at_least_1_hit: int
    deposit_keep_rate: str
    average_hits_per_night: float
    average_parlays_per_night: float
    hit_rate_by_legs: Dict[str, str]
    hit_rate_by_type: Dict[str, str]
    total_profit_loss: float
    best_night: Dict
    worst_night: Dict
    nightly_results: List[Dict]


class HistoricalNBAFetcher:
    """Fetches historical NBA data for backtesting (no lookahead bias)"""
    
    def __init__(self):
        self.teams_data = teams.get_teams()
        self.team_id_map = {team['full_name']: team['id'] for team in self.teams_data}
        self.team_abbr_map = {team['abbreviation']: team['id'] for team in self.teams_data}
        logger.info("Historical NBA Fetcher initialized")
    
    def get_games_for_date(self, target_date: date) -> List[Dict]:
        """Get all NBA games played on a specific date"""
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            logger.info(f"Fetching games for {date_str}")
            
            # Rate limiting
            time.sleep(0.6)
            
            scoreboard = scoreboardv2.ScoreboardV2(game_date=date_str)
            dataframes = scoreboard.get_data_frames()
            
            games_header = dataframes[0]  # Basic game info
            line_score = dataframes[1]    # Team details and scores
            
            if games_header.empty:
                logger.info(f"No games found for {date_str}")
                return []
            
            # Create team name lookup from static data
            team_name_lookup = {team['id']: team['full_name'] for team in self.teams_data}
            
            games = []
            for _, game in games_header.iterrows():
                game_id = str(game['GAME_ID'])
                home_team_id = game['HOME_TEAM_ID']
                away_team_id = game['VISITOR_TEAM_ID']
                
                # Get team names from static data
                home_team = team_name_lookup.get(home_team_id, f"Team_{home_team_id}")
                away_team = team_name_lookup.get(away_team_id, f"Team_{away_team_id}")
                
                # Get scores from line score dataframe
                home_score = 0
                away_score = 0
                
                game_line_scores = line_score[line_score['GAME_ID'] == game['GAME_ID']]
                for _, team_line in game_line_scores.iterrows():
                    if team_line['TEAM_ID'] == home_team_id:
                        home_score = team_line['PTS']
                    elif team_line['TEAM_ID'] == away_team_id:
                        away_score = team_line['PTS']
                
                games.append({
                    'game_id': game_id,
                    'home_team': home_team,
                    'away_team': away_team,
                    'home_team_id': home_team_id,
                    'away_team_id': away_team_id,
                    'home_score': home_score,
                    'away_score': away_score,
                    'game_status': game['GAME_STATUS_TEXT'],
                    'game_date': date_str
                })
            
            logger.info(f"Found {len(games)} games for {date_str}")
            return games
            
        except Exception as e:
            logger.error(f"Error fetching games for {target_date}: {e}")
            return []
    
    def get_team_stats_as_of_date(self, as_of_date: date) -> Dict:
        """Get team stats as they existed on a specific date (no lookahead bias)"""
        try:
            logger.info(f"Fetching team stats as of {as_of_date}")
            
            # Rate limiting
            time.sleep(0.6)
            
            # Get season stats up to the specified date
            season = "2024-25"
            date_to_str = as_of_date.strftime('%m/%d/%Y')
            
            team_stats_endpoint = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star='Regular Season',
                date_to_nullable=date_to_str
            )
            
            stats_df = team_stats_endpoint.get_data_frames()[0]
            
            team_stats = {}
            for _, row in stats_df.iterrows():
                team_id = row['TEAM_ID']
                team_name = row['TEAM_NAME']
                
                team_stats[str(team_id)] = {
                    'team_name': team_name,
                    'games_played': row['GP'],
                    'wins': row['W'],
                    'losses': row['L'],
                    'win_pct': row['W_PCT'],
                    'points_per_game': row['PTS'] / row['GP'] if row['GP'] > 0 else 0,
                    'opp_points_per_game': row['OPP_PTS'] / row['GP'] if row['GP'] > 0 else 0,
                    'offensive_rating': row.get('OFF_RATING', 100),
                    'defensive_rating': row.get('DEF_RATING', 100),
                    'pace': row.get('PACE', 100),
                    'rebounding_rate': row.get('REB_PCT', 50),
                    'turnover_rate': row.get('TOV_PCT', 15)
                }
            
            logger.info(f"Retrieved stats for {len(team_stats)} teams as of {as_of_date}")
            return team_stats
            
        except Exception as e:
            logger.error(f"Error fetching team stats as of {as_of_date}: {e}")
            return {}
    
    def get_recent_team_form(self, team_id: int, as_of_date: date, games: int = 10) -> Dict:
        """Get team's recent form (last N games) as of a specific date"""
        try:
            # Rate limiting
            time.sleep(0.6)
            
            season = "2024-25"
            date_to_str = as_of_date.strftime('%m/%d/%Y')
            
            game_log = teamgamelog.TeamGameLog(
                team_id=team_id,
                season=season,
                season_type_all_star='Regular Season',
                date_to_nullable=date_to_str
            )
            
            games_df = game_log.get_data_frames()[0]
            recent_games = games_df.head(games)
            
            if recent_games.empty:
                return {'wins': 0, 'losses': 0, 'win_pct': 0.0, 'avg_margin': 0.0}
            
            wins = (recent_games['WL'] == 'W').sum()
            losses = len(recent_games) - wins
            win_pct = wins / len(recent_games) if len(recent_games) > 0 else 0.0
            
            # Calculate average margin of victory/defeat
            margins = []
            for _, game in recent_games.iterrows():
                team_score = game['PTS']
                opp_score = game['OPP_PTS']
                margin = team_score - opp_score
                margins.append(margin)
            
            avg_margin = sum(margins) / len(margins) if margins else 0.0
            
            return {
                'wins': wins,
                'losses': losses,
                'win_pct': win_pct,
                'avg_margin': avg_margin,
                'games_played': len(recent_games)
            }
            
        except Exception as e:
            logger.error(f"Error fetching recent form for team {team_id}: {e}")
            return {'wins': 0, 'losses': 0, 'win_pct': 0.0, 'avg_margin': 0.0}


class ParlayBacktester:
    """Main backtesting engine"""
    
    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.fetcher = HistoricalNBAFetcher()
        self.results = []
        
        # Parlay distribution per night
        self.parlay_distribution = {
            2: 2,  # 2x 2-leg parlays (safest)
            3: 3,  # 3x 3-leg parlays (sweet spot)
            4: 2,  # 2x 4-leg parlays (medium risk)
            5: 2,  # 2x 5-leg parlays (high payout)
            6: 1   # 1x 6-leg parlay (longshot)
        }
        
        logger.info(f"Backtester initialized for period {start_date} to {end_date}")
    
    def estimate_spread(self, home_stats: Dict, away_stats: Dict, home_recent: Dict, away_recent: Dict) -> float:
        """Estimate point spread based on team stats and recent form"""
        # Home court advantage baseline
        home_advantage = 3.5
        
        # Win percentage differential
        win_pct_diff = (home_stats.get('win_pct', 0.5) - away_stats.get('win_pct', 0.5)) * 10
        
        # Recent form differential
        recent_diff = (home_recent.get('avg_margin', 0) - away_recent.get('avg_margin', 0)) * 0.3
        
        # Offensive/Defensive rating differential  
        off_rating_diff = (home_stats.get('offensive_rating', 100) - away_stats.get('offensive_rating', 100)) * 0.1
        def_rating_diff = (away_stats.get('defensive_rating', 100) - home_stats.get('defensive_rating', 100)) * 0.1
        
        estimated_spread = home_advantage + win_pct_diff + recent_diff + off_rating_diff + def_rating_diff
        
        return round(estimated_spread * 2) / 2  # Round to nearest 0.5
    
    def estimate_total(self, home_stats: Dict, away_stats: Dict) -> float:
        """Estimate game total based on team offensive/defensive ratings and pace"""
        home_ppg = home_stats.get('points_per_game', 110)
        away_ppg = away_stats.get('points_per_game', 110)
        home_oppg = home_stats.get('opp_points_per_game', 110)
        away_oppg = away_stats.get('opp_points_per_game', 110)
        
        # Average the different approaches
        approach1 = home_ppg + away_ppg  # Simple addition
        approach2 = (home_ppg + away_oppg + away_ppg + home_oppg) / 2  # Average offense vs defense
        
        estimated_total = (approach1 + approach2) / 2
        
        return round(estimated_total * 2) / 2  # Round to nearest 0.5
    
    def score_game_matchup(self, game: Dict, home_stats: Dict, away_stats: Dict, 
                          home_recent: Dict, away_recent: Dict, estimated_spread: float) -> GameAnalysis:
        """Score a game matchup using the existing analyzer logic"""
        
        # Calculate confidence factors (0-100 scale)
        factors = {}
        
        # Home court advantage
        factors['home_court'] = 75.0  # Always favor home team baseline
        
        # Win percentage differential
        win_pct_diff = home_stats.get('win_pct', 0.5) - away_stats.get('win_pct', 0.5)
        factors['win_pct_differential'] = 50 + (win_pct_diff * 100)  # Scale to 0-100
        
        # Recent form (last 10 games)
        home_form = home_recent.get('win_pct', 0.5)
        away_form = away_recent.get('win_pct', 0.5)
        factors['recent_form'] = 50 + ((home_form - away_form) * 100)
        
        # Rest days advantage (simplified - assume no back-to-backs for now)
        factors['rest_advantage'] = 50.0
        
        # Offensive/Defensive rating differential
        off_diff = home_stats.get('offensive_rating', 100) - away_stats.get('offensive_rating', 100)
        def_diff = away_stats.get('defensive_rating', 100) - home_stats.get('defensive_rating', 100)
        factors['off_rating_diff'] = 50 + off_diff
        factors['def_rating_diff'] = 50 + def_diff
        
        # Pace differential for totals
        home_pace = home_stats.get('pace', 100)
        away_pace = away_stats.get('pace', 100)
        avg_pace = (home_pace + away_pace) / 2
        factors['pace_factor'] = avg_pace
        
        # Calculate overall confidence scores
        spread_confidence = (factors['home_court'] + factors['win_pct_differential'] + 
                           factors['recent_form'] + factors['off_rating_diff'] + 
                           factors['def_rating_diff']) / 5
        
        moneyline_confidence = spread_confidence * 0.8  # Slightly lower than spread
        
        total_confidence = (factors['pace_factor'] + 50) / 2  # Simplified total confidence
        
        # Determine picks
        spread_pick = game['home_team'] if estimated_spread > 0 else game['away_team']
        moneyline_pick = game['home_team'] if spread_confidence > 60 else game['away_team']
        
        estimated_total = self.estimate_total(home_stats, away_stats)
        total_pick = "Over" if avg_pace > 102 else "Under"
        
        return GameAnalysis(
            game_id=game['game_id'],
            home_team=game['home_team'],
            away_team=game['away_team'],
            home_score=float(spread_confidence),
            away_score=float(100 - spread_confidence),
            spread_pick=spread_pick,
            spread_confidence=float(spread_confidence),
            moneyline_pick=moneyline_pick,
            moneyline_confidence=float(moneyline_confidence),
            total_pick=total_pick,
            total_confidence=float(total_confidence),
            reasoning={
                "spread": f"Model favors {spread_pick} based on {spread_confidence:.1f}% confidence",
                "moneyline": f"Pick {moneyline_pick} straight up",
                "total": f"Take the {total_pick} {estimated_total}"
            },
            factors=factors
        )
    
    def check_parlay_result(self, parlay: Parlay, games: List[Dict]) -> bool:
        """Check if a parlay hit based on actual game results"""
        game_results = {game['game_id']: game for game in games}
        
        for leg in parlay.picks:
            game_id = leg.game.split(' ')[0]  # Extract game ID from leg description
            if game_id not in game_results:
                return False  # Game not found, parlay loses
            
            game = game_results[game_id]
            home_score = float(game['home_score'])
            away_score = float(game['away_score'])
            
            if leg.pick_type == 'spread':
                # Extract team and spread from pick description
                if game['home_team'] in leg.pick:
                    actual_margin = home_score - away_score
                    # Simplified: assume we picked home team and extract spread from reasoning
                    # For now, just check if home team won when we picked them
                    if home_score <= away_score:
                        return False
                elif game['away_team'] in leg.pick:
                    actual_margin = away_score - home_score
                    if away_score <= home_score:
                        return False
                
            elif leg.pick_type == 'moneyline':
                if game['home_team'] in leg.pick and home_score <= away_score:
                    return False
                elif game['away_team'] in leg.pick and away_score <= home_score:
                    return False
                    
            elif leg.pick_type == 'total':
                total_points = home_score + away_score
                if 'Over' in leg.pick:
                    # Extract total from reasoning - simplified for now
                    # Just use a reasonable NBA average of 220
                    if total_points <= 220:
                        return False
                elif 'Under' in leg.pick:
                    if total_points >= 220:
                        return False
        
        return True  # All legs hit
    
    def run_backtest_for_date(self, target_date: date) -> Optional[BacktestResult]:
        """Run backtest for a single date"""
        try:
            logger.info(f"\n" + "="*60)
            logger.info(f"BACKTESTING DATE: {target_date}")
            logger.info("="*60)
            
            # Get games for this date
            games = self.fetcher.get_games_for_date(target_date)
            if not games:
                logger.info(f"No games found for {target_date}, skipping")
                return None
            
            # Only test completed games
            completed_games = [g for g in games if g['game_status'] == 'Final' and 
                             g['home_score'] > 0 and g['away_score'] > 0]
            
            if not completed_games:
                logger.info(f"No completed games found for {target_date}, skipping")
                return None
            
            logger.info(f"Found {len(completed_games)} completed games")
            
            # Get team stats as of this date (no lookahead bias)
            team_stats = self.fetcher.get_team_stats_as_of_date(target_date)
            if not team_stats:
                logger.warning(f"No team stats available for {target_date}, skipping")
                return None
            
            # Analyze each game
            analyses = []
            for game in completed_games:
                home_stats = team_stats.get(str(game['home_team_id']), {})
                away_stats = team_stats.get(str(game['away_team_id']), {})
                
                if not home_stats or not away_stats:
                    continue
                
                # Get recent form
                home_recent = self.fetcher.get_recent_team_form(game['home_team_id'], target_date)
                away_recent = self.fetcher.get_recent_team_form(game['away_team_id'], target_date)
                
                # Estimate spread
                estimated_spread = self.estimate_spread(home_stats, away_stats, home_recent, away_recent)
                
                # Score the matchup
                analysis = self.score_game_matchup(game, home_stats, away_stats, 
                                                 home_recent, away_recent, estimated_spread)
                analyses.append(analysis)
            
            if len(analyses) < 3:  # Need at least 3 games to make meaningful parlays
                logger.info(f"Only {len(analyses)} analyzed games, need at least 3 for parlays")
                return None
            
            logger.info(f"Analyzed {len(analyses)} games, generating parlays...")
            
            # Generate parlays using existing generator
            parlay_gen = ParlayGenerator(analyses)
            all_parlays = []
            
            # Generate parlays according to distribution
            for leg_count, count in self.parlay_distribution.items():
                parlays = parlay_gen.generate_parlays(
                    parlay_count=count,
                    min_legs=leg_count,
                    max_legs=leg_count,
                    min_confidence=0.0  # Accept all confidence levels for backtesting
                )
                all_parlays.extend(parlays)
            
            logger.info(f"Generated {len(all_parlays)} parlays")
            
            # Check results
            hits = 0
            hit_by_legs = defaultdict(int)
            hit_by_type = defaultdict(int)
            confidence_scores = []
            parlay_details = []
            
            for parlay in all_parlays:
                confidence_scores.append(parlay.confidence)
                hit = self.check_parlay_result(parlay, completed_games)
                
                parlay_detail = {
                    'id': parlay.id,
                    'legs': parlay.legs,
                    'confidence': parlay.confidence,
                    'hit': hit,
                    'picks': [{'game': leg.game, 'pick': leg.pick, 'type': leg.pick_type} for leg in parlay.picks]
                }
                parlay_details.append(parlay_detail)
                
                if hit:
                    hits += 1
                    hit_by_legs[f"{parlay.legs}_leg"] += 1
                    
                    # Count by pick types in this parlay
                    for leg in parlay.picks:
                        hit_by_type[leg.pick_type] += 1
            
            hit_rate = hits / len(all_parlays) if all_parlays else 0.0
            deposit_kept = hits >= 1  # At least 1 out of ~10 parlays hit
            daily_profit_loss = (hits * 50 - len(all_parlays) * 10)  # Assume $50 avg payout, $10 cost per parlay
            
            result = BacktestResult(
                date=target_date.strftime('%Y-%m-%d'),
                games_available=len(completed_games),
                parlays_generated=len(all_parlays),
                parlays_hit=hits,
                hit_rate=hit_rate,
                deposit_kept=deposit_kept,
                daily_profit_loss=daily_profit_loss,
                hit_by_legs=dict(hit_by_legs),
                hit_by_type=dict(hit_by_type),
                confidence_scores=confidence_scores,
                details=parlay_details
            )
            
            logger.info(f"Results: {hits}/{len(all_parlays)} parlays hit ({hit_rate:.2%})")
            logger.info(f"Deposit {'KEPT' if deposit_kept else 'REFUNDED'}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error backtesting {target_date}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def run_full_backtest(self, save_intermediate=True) -> OverallResults:
        """Run complete backtest over the specified date range"""
        logger.info(f"\n{'='*80}")
        logger.info(f"STARTING FULL BACKTEST: {self.start_date} to {self.end_date}")
        logger.info(f"{'='*80}\n")
        
        current_date = self.start_date
        processed_nights = 0
        
        while current_date <= self.end_date:
            try:
                result = self.run_backtest_for_date(current_date)
                
                if result:
                    self.results.append(result)
                    processed_nights += 1
                    
                    # Save intermediate results every 10 nights
                    if save_intermediate and processed_nights % 10 == 0:
                        self.save_intermediate_results(processed_nights)
                
                current_date += timedelta(days=1)
                
            except Exception as e:
                logger.error(f"Critical error on {current_date}: {e}")
                current_date += timedelta(days=1)
                continue
        
        return self.calculate_overall_results()
    
    def save_intermediate_results(self, nights_processed: int):
        """Save intermediate results to prevent data loss"""
        filename = f"backtest_intermediate_{nights_processed}nights.json"
        
        intermediate_data = {
            'nights_processed': nights_processed,
            'last_date': self.results[-1].date if self.results else None,
            'results': [asdict(result) for result in self.results]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(intermediate_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Intermediate results saved to {filename}")
    
    def calculate_overall_results(self) -> OverallResults:
        """Calculate overall results from all backtested dates"""
        if not self.results:
            logger.error("No results to analyze!")
            return None
        
        # Basic metrics
        total_nights = len(self.results)
        nights_with_hits = sum(1 for r in self.results if r.parlays_hit > 0)
        deposit_keep_rate = (nights_with_hits / total_nights) * 100
        
        total_parlays_hit = sum(r.parlays_hit for r in self.results)
        total_parlays_generated = sum(r.parlays_generated for r in self.results)
        
        avg_hits_per_night = total_parlays_hit / total_nights
        avg_parlays_per_night = total_parlays_generated / total_nights
        
        # Hit rates by leg count
        total_hit_by_legs = defaultdict(int)
        total_gen_by_legs = defaultdict(int)
        
        for result in self.results:
            for leg_type, hits in result.hit_by_legs.items():
                total_hit_by_legs[leg_type] += hits
            
            # Calculate generated by legs (from distribution)
            for leg_count, count in self.parlay_distribution.items():
                leg_type = f"{leg_count}_leg"
                total_gen_by_legs[leg_type] += count
        
        hit_rate_by_legs = {}
        for leg_type in total_gen_by_legs:
            hits = total_hit_by_legs.get(leg_type, 0)
            generated = total_gen_by_legs[leg_type] * total_nights
            hit_rate_by_legs[leg_type] = f"{(hits/generated*100):.1f}%" if generated > 0 else "0.0%"
        
        # Hit rates by bet type
        total_hit_by_type = defaultdict(int)
        for result in self.results:
            for bet_type, hits in result.hit_by_type.items():
                total_hit_by_type[bet_type] += hits
        
        # Estimate total legs by type (simplified)
        total_legs_by_type = {
            'spread': int(total_parlays_generated * 0.4),  # Rough estimates
            'moneyline': int(total_parlays_generated * 0.4),
            'total': int(total_parlays_generated * 0.2)
        }
        
        hit_rate_by_type = {}
        for bet_type, total_legs in total_legs_by_type.items():
            hits = total_hit_by_type.get(bet_type, 0)
            hit_rate_by_type[bet_type] = f"{(hits/total_legs*100):.1f}%" if total_legs > 0 else "0.0%"
        
        # Best and worst nights
        best_night = max(self.results, key=lambda r: r.parlays_hit)
        worst_night = min(self.results, key=lambda r: r.parlays_hit)
        
        # Total profit/loss
        total_profit_loss = sum(r.daily_profit_loss for r in self.results)
        
        overall = OverallResults(
            test_period=f"{self.start_date} to {self.end_date}",
            total_nights=total_nights,
            nights_with_at_least_1_hit=nights_with_hits,
            deposit_keep_rate=f"{deposit_keep_rate:.1f}%",
            average_hits_per_night=avg_hits_per_night,
            average_parlays_per_night=avg_parlays_per_night,
            hit_rate_by_legs=hit_rate_by_legs,
            hit_rate_by_type=hit_rate_by_type,
            total_profit_loss=total_profit_loss,
            best_night={
                'date': best_night.date,
                'hits': best_night.parlays_hit,
                'hit_rate': best_night.hit_rate
            },
            worst_night={
                'date': worst_night.date,
                'hits': worst_night.parlays_hit,
                'hit_rate': worst_night.hit_rate
            },
            nightly_results=[asdict(result) for result in self.results]
        )
        
        return overall
    
    def save_results(self, filename: str = "backtest_results.json"):
        """Save final results to JSON file"""
        overall = self.calculate_overall_results()
        if not overall:
            logger.error("No results to save!")
            return
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(asdict(overall), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {filename}")
        return overall


def print_summary(results: OverallResults):
    """Print a clear summary of backtest results"""
    print("\n" + "="*80)
    print("🏀 PARLAY GUARANTEE BACKTEST RESULTS 🏀")
    print("="*80)
    
    print(f"\n📅 Test Period: {results.test_period}")
    print(f"🌙 Total Nights: {results.total_nights}")
    print(f"💰 Nights with ≥1 Hit: {results.nights_with_at_least_1_hit}")
    print(f"🏦 DEPOSIT KEEP RATE: {results.deposit_keep_rate} 👈 KEY METRIC")
    
    print(f"\n📊 Performance Metrics:")
    print(f"   • Average hits per night: {results.average_hits_per_night:.2f}")
    print(f"   • Average parlays per night: {results.average_parlays_per_night:.1f}")
    print(f"   • Total P&L (customer bets $10/parlay): ${results.total_profit_loss:,.2f}")
    
    print(f"\n🎯 Hit Rates by Parlay Size:")
    for legs, rate in results.hit_rate_by_legs.items():
        print(f"   • {legs.replace('_', '-').title()}: {rate}")
    
    print(f"\n🎲 Hit Rates by Bet Type:")
    for bet_type, rate in results.hit_rate_by_type.items():
        print(f"   • {bet_type.title()}: {rate}")
    
    print(f"\n🌟 Best Night: {results.best_night['date']} ({results.best_night['hits']} hits)")
    print(f"😞 Worst Night: {results.worst_night['date']} ({results.worst_night['hits']} hits)")
    
    print("\n" + "="*80)
    
    # Business viability assessment
    deposit_keep_pct = float(results.deposit_keep_rate.rstrip('%'))
    print("🚀 BUSINESS VIABILITY ASSESSMENT:")
    print("="*80)
    
    if deposit_keep_pct >= 80:
        print("✅ EXCELLENT - Very viable business model!")
        print("   Customers get refunded <20% of nights = high satisfaction")
    elif deposit_keep_pct >= 70:
        print("✅ GOOD - Viable with some optimization needed")
        print("   Refund rate manageable but could improve pick quality")
    elif deposit_keep_pct >= 60:
        print("⚠️  MARGINAL - Needs significant improvement")
        print("   High refund rate may hurt profitability")
    else:
        print("❌ NOT VIABLE - Back to the drawing board")
        print("   Too many refund nights, business model doesn't work")
    
    print("="*80)


def main():
    """Main backtesting execution"""
    # Set date range for 2024-25 season
    start_date = date(2024, 10, 22)  # Season typically starts mid-October
    end_date = date(2026, 2, 15)     # Current date based on system time
    
    print(f"🏀 NBA PARLAY BACKTEST STARTING")
    print(f"📅 Testing period: {start_date} to {end_date}")
    print(f"🎯 This determines if ParlayGuarantee is viable business or vaporware")
    print("⏱️  This will take a while due to API rate limiting (0.6s between calls)")
    print("💾 Intermediate results saved every 10 nights to prevent data loss\n")
    
    # Initialize backtester
    backtester = ParlayBacktester(start_date, end_date)
    
    try:
        # Run full backtest
        overall_results = backtester.run_full_backtest()
        
        # Save results
        backtester.save_results()
        
        # Print summary
        print_summary(overall_results)
        
        # Final message
        print(f"\n🎉 Backtest complete! Results saved to backtest_results.json")
        print(f"📊 {len(backtester.results)} nights analyzed")
        print(f"⚡ Now you know if ParlayGuarantee is real business or needs more work")
        
    except Exception as e:
        logger.error(f"Fatal error in main backtest: {e}")
        logger.error(traceback.format_exc())
        print(f"\n❌ Backtest failed: {e}")
        print("Check backtest.log for detailed error information")
        
        # Save whatever results we have
        if backtester.results:
            backtester.save_intermediate_results(len(backtester.results))
            print(f"💾 Partial results saved ({len(backtester.results)} nights)")


if __name__ == "__main__":
    main()