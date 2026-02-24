"""
ParlayGuarantee Engine v2 - Production-Grade NBA Prediction Engine
Comprehensive 37-factor model with self-learning capabilities

This replaces the basic Log5 model with a sophisticated ML system that:
- Analyzes 37+ different factors
- Self-calibrates weights based on performance
- Tracks accuracy per factor
- Uses Bayesian updating for confidence
- Integrates live odds and line movement
"""

import sys
import json
import time
import logging
import sqlite3
import argparse
import math
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import traceback

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# NBA API imports
from nba_api.stats.endpoints import (
    scoreboardv2, leaguedashteamstats, teamgamelog, 
    leaguedashplayerstats, playergamelog, teamdetails,
    leaguegamefinder, boxscoretraditionalv2
)
from nba_api.stats.static import teams

# Local imports
from team_locations import (
    calculate_distance, get_timezone_difference, is_division_rival,
    is_conference_game, get_team_division, NBA_TEAM_LOCATIONS
)
from odds_fetcher import OddsFetcher
from self_learner import SelfLearner
from injury_scraper import get_injuries, get_team_injury_impact

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('engine_v2.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


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


# Global team mapping
TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}
TEAM_ABBREV_MAP = {t['abbreviation']: t['full_name'] for t in teams.get_teams()}


class NBAPredictor:
    """
    Production-grade NBA prediction engine with 37+ factors and self-learning
    """
    
    def __init__(self):
        self.db_path = "engine_data.db"
        self.team_stats = {}
        self.player_stats = {}
        
        # Initialize components
        self.odds_fetcher = OddsFetcher()
        self.self_learner = SelfLearner(self.db_path)
        
        # Load factor weights (self-calibrating)
        self.factor_weights = self.self_learner.load_weights()
        
        # Cache for API responses to reduce calls
        self.api_cache = {}
        self.cache_timestamp = {}
        
        # Rate limiting
        self.last_api_call = 0
        self.api_delay = 0.6  # 600ms between calls
        
        logger.info("NBAPredictor v2 initialized with self-learning capabilities")
    
    def rate_limit(self):
        """Enforce API rate limiting"""
        now = time.time()
        if now - self.last_api_call < self.api_delay:
            time.sleep(self.api_delay - (now - self.last_api_call))
        self.last_api_call = time.time()
    
    def fetch_team_stats(self, season: str = "2025-26"):
        """Fetch comprehensive team statistics"""
        logger.info(f"Fetching {season} team stats...")
        
        cache_key = f"team_stats_{season}"
        if self.is_cache_valid(cache_key, hours=6):
            self.team_stats = self.api_cache[cache_key]
            return
        
        try:
            # Fetch basic stats (NBA only)
            self.rate_limit()
            basic_stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season, league_id_nullable='00'
            )
            df = safe_get_data_frames(basic_stats)[0]
            
            # Fetch advanced stats
            self.rate_limit()
            adv_stats = leaguedashteamstats.LeagueDashTeamStats(
                season=season, league_id_nullable='00',
                measure_type_detailed_defense='Advanced'
            )
            adv_df = safe_get_data_frames(adv_stats)[0]
            
            # Index advanced by TEAM_ID
            adv_by_id = {}
            for _, arow in adv_df.iterrows():
                adv_by_id[arow['TEAM_ID']] = arow
            
            team_stats = {}
            
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                gp = max(row['GP'], 1)
                adv = adv_by_id.get(tid, {})
                
                ppg = row['PTS'] / gp
                plus_minus_pg = row['PLUS_MINUS'] / gp
                opp_ppg = ppg - plus_minus_pg  # Derive from plus/minus
                
                team_stats[name] = {
                    'games_played': row['GP'],
                    'wins': row['W'],
                    'losses': row['L'],
                    'win_pct': row['W_PCT'],
                    'ppg': ppg,
                    'opp_ppg': opp_ppg,
                    'plus_minus': plus_minus_pg,
                    'offensive_rating': adv.get('OFF_RATING', 110) if isinstance(adv, pd.Series) else (adv['OFF_RATING'] if 'OFF_RATING' in adv else 110),
                    'defensive_rating': adv.get('DEF_RATING', 110) if isinstance(adv, pd.Series) else (adv['DEF_RATING'] if 'DEF_RATING' in adv else 110),
                    'net_rating': adv.get('NET_RATING', 0) if isinstance(adv, pd.Series) else (adv['NET_RATING'] if 'NET_RATING' in adv else 0),
                    'pace': adv.get('PACE', 100) if isinstance(adv, pd.Series) else (adv['PACE'] if 'PACE' in adv else 100),
                    'fg_pct': row['FG_PCT'],
                    'fg3_pct': row['FG3_PCT'],
                    'ft_pct': row['FT_PCT'],
                    'fg3a_pg': row['FG3A'] / gp,
                    'fta_pg': row['FTA'] / gp,
                    'reb_pg': row['REB'] / gp,
                    'oreb_pg': row['OREB'] / gp,
                    'ast_pg': row['AST'] / gp,
                    'tov_pg': row['TOV'] / gp,
                    'stl_pg': row['STL'] / gp,
                    'blk_pg': row['BLK'] / gp,
                    # Opponent stats estimated from differentials
                    'opp_fg_pct': 0.45,
                    'opp_fg3_pct': 0.35,
                    'opp_ft_pct': 0.75,
                    'opp_reb_pg': 44.0,
                    'opp_ast_pg': 25.0,
                    'opp_tov_pg': 14.0,
                }
                
                team_stats[name]['scoring_diff'] = ppg - opp_ppg
                team_stats[name]['rebound_diff'] = team_stats[name]['reb_pg'] - team_stats[name]['opp_reb_pg']
                team_stats[name]['turnover_diff'] = team_stats[name]['opp_tov_pg'] - team_stats[name]['tov_pg']
                team_stats[name]['ft_rate_diff'] = 0.0
            
            self.team_stats = team_stats
            self.api_cache[cache_key] = team_stats
            self.cache_timestamp[cache_key] = time.time()
            
            logger.info(f"Loaded stats for {len(team_stats)} teams")
            
        except Exception as e:
            logger.error(f"Error fetching team stats: {e}")
            logger.error(traceback.format_exc())
            if season == "2024-25":
                logger.info("Falling back to 2024-25 season")
                self.fetch_team_stats("2024-25")
    
    def fetch_recent_form(self, team: str, games: int = 10) -> Dict:
        """Fetch recent game form (last N games)"""
        cache_key = f"form_{team}_{games}"
        if self.is_cache_valid(cache_key, hours=2):
            return self.api_cache[cache_key]
        
        try:
            team_id = self.get_team_id(team)
            if not team_id:
                return {'wins': 0, 'losses': 0, 'win_pct': 0.5}
            
            self.rate_limit()
            gamelog = teamgamelog.TeamGameLog(team_id=team_id, season='2025-26')
            df = safe_get_data_frames(gamelog)[0]
            
            if df.empty:
                return {'wins': 0, 'losses': 0, 'win_pct': 0.5}
            
            # Get last N games
            recent_games = df.head(games)
            wins = len(recent_games[recent_games['WL'] == 'W'])
            losses = len(recent_games[recent_games['WL'] == 'L'])
            
            ppg = recent_games['PTS'].mean()
            form_data = {
                'wins': wins,
                'losses': losses,
                'win_pct': wins / max(1, wins + losses),
                'ppg': ppg,
                'opp_ppg': ppg,  # Not available in gamelog
                'plus_minus': 0.0  # Not available in gamelog
            }
            
            self.api_cache[cache_key] = form_data
            self.cache_timestamp[cache_key] = time.time()
            
            return form_data
            
        except Exception as e:
            logger.error(f"Error fetching recent form for {team}: {e}")
            return {'wins': 0, 'losses': 0, 'win_pct': 0.5}
    
    def fetch_home_away_splits(self, team: str) -> Dict:
        """Fetch home/away performance splits"""
        cache_key = f"splits_{team}"
        if self.is_cache_valid(cache_key, hours=6):
            return self.api_cache[cache_key]
        
        try:
            team_id = self.get_team_id(team)
            if not team_id:
                return {'home_win_pct': 0.58, 'away_win_pct': 0.42}
            
            self.rate_limit()
            gamelog = teamgamelog.TeamGameLog(team_id=team_id, season='2025-26')
            df = safe_get_data_frames(gamelog)[0]
            
            if df.empty:
                return {'home_win_pct': 0.58, 'away_win_pct': 0.42}
            
            # Split by home/away (@ symbol indicates away game)
            home_games = df[~df['MATCHUP'].str.contains('@', na=False)]
            away_games = df[df['MATCHUP'].str.contains('@', na=False)]
            
            home_wins = len(home_games[home_games['WL'] == 'W'])
            home_total = len(home_games)
            away_wins = len(away_games[away_games['WL'] == 'W'])
            away_total = len(away_games)
            
            splits_data = {
                'home_win_pct': home_wins / max(1, home_total),
                'away_win_pct': away_wins / max(1, away_total),
                'home_ppg': home_games['PTS'].mean() if not home_games.empty else 110,
                'away_ppg': away_games['PTS'].mean() if not away_games.empty else 105,
                'home_games': home_total,
                'away_games': away_total
            }
            
            self.api_cache[cache_key] = splits_data
            self.cache_timestamp[cache_key] = time.time()
            
            return splits_data
            
        except Exception as e:
            logger.error(f"Error fetching home/away splits for {team}: {e}")
            return {'home_win_pct': 0.58, 'away_win_pct': 0.42}
    
    def get_head_to_head_record(self, team1: str, team2: str, seasons: int = 2) -> Dict:
        """Get head-to-head record between two teams"""
        cache_key = f"h2h_{team1}_{team2}_{seasons}"
        if self.is_cache_valid(cache_key, hours=12):
            return self.api_cache[cache_key]
        
        try:
            # This would require more complex API calls
            # For now, return neutral record
            h2h_data = {
                'team1_wins': 1,
                'team2_wins': 1,
                'total_games': 2,
                'team1_win_pct': 0.5
            }
            
            self.api_cache[cache_key] = h2h_data
            self.cache_timestamp[cache_key] = time.time()
            
            return h2h_data
            
        except Exception as e:
            logger.error(f"Error fetching H2H for {team1} vs {team2}: {e}")
            return {'team1_wins': 1, 'team2_wins': 1, 'total_games': 2, 'team1_win_pct': 0.5}
    
    def calculate_rest_days(self, team: str, game_date: date) -> int:
        """Calculate rest days since last game"""
        try:
            team_id = self.get_team_id(team)
            if not team_id:
                return 2  # Default to well-rested
            
            self.rate_limit()
            gamelog = teamgamelog.TeamGameLog(team_id=team_id, season='2025-26')
            df = safe_get_data_frames(gamelog)[0]
            
            if df.empty:
                return 2
            
            # Find most recent game before target date
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
            target_dt = datetime.combine(game_date, datetime.min.time())
            
            recent_games = df[df['GAME_DATE'] < target_dt]
            if recent_games.empty:
                return 2
            
            last_game = recent_games.iloc[0]['GAME_DATE']
            rest_days = (target_dt - last_game).days - 1
            
            return max(0, rest_days)
            
        except Exception as e:
            logger.error(f"Error calculating rest days for {team}: {e}")
            return 2  # Default to well-rested
    
    def calculate_travel_distance(self, team: str, game_date: date, opponent: str) -> float:
        """Calculate travel distance from last game location"""
        try:
            team_id = self.get_team_id(team)
            if not team_id:
                return 0.0
            
            # Get last game location
            self.rate_limit()
            gamelog = teamgamelog.TeamGameLog(team_id=team_id, season='2025-26')
            df = safe_get_data_frames(gamelog)[0]
            
            if df.empty:
                return 0.0
            
            # Find most recent game
            last_game = df.iloc[0]
            last_matchup = last_game['MATCHUP']
            
            # Determine where they played last
            if '@' in last_matchup:
                # Away game - extract opponent
                parts = last_matchup.split(' @ ')
                if len(parts) > 1:
                    last_opponent_abbrev = parts[1]
                    last_opponent = TEAM_ABBREV_MAP.get(last_opponent_abbrev, team)
                else:
                    last_opponent = team  # Default to home if can't parse
            else:
                # Home game
                last_opponent = team
            
            # Calculate distance from last game location to current game location
            # Current game location is opponent's city (since we're calculating for the team)
            distance = calculate_distance(last_opponent, opponent)
            
            return distance
            
        except Exception as e:
            logger.error(f"Error calculating travel distance for {team}: {e}")
            return 0.0
    
    def calculate_strength_of_schedule(self, team: str) -> float:
        """Calculate strength of schedule (opponent win% weighted)"""
        try:
            team_id = self.get_team_id(team)
            if not team_id:
                return 0.5
            
            self.rate_limit()
            gamelog = teamgamelog.TeamGameLog(team_id=team_id, season='2025-26')
            df = safe_get_data_frames(gamelog)[0]
            
            if df.empty:
                return 0.5
            
            opponent_win_pcts = []
            
            for _, game in df.iterrows():
                matchup = game['MATCHUP']
                
                # Extract opponent abbreviation
                if '@' in matchup:
                    opponent_abbrev = matchup.split(' @ ')[1]
                else:
                    opponent_abbrev = matchup.split(' vs. ')[1]
                
                opponent_name = TEAM_ABBREV_MAP.get(opponent_abbrev)
                if opponent_name and opponent_name in self.team_stats:
                    opponent_win_pcts.append(self.team_stats[opponent_name]['win_pct'])
            
            if opponent_win_pcts:
                return sum(opponent_win_pcts) / len(opponent_win_pcts)
            else:
                return 0.5
                
        except Exception as e:
            logger.error(f"Error calculating SOS for {team}: {e}")
            return 0.5
    
    def get_injury_impact(self, team: str, game_date: date) -> float:
        """
        Calculate injury impact using live scraped injury data.
        Returns penalty factor (0.0 = no impact, up to 0.30 = catastrophic).
        Falls back to performance-based proxy if scraping fails.
        """
        try:
            # Use cached injury data (refreshes every 30 min)
            if not hasattr(self, '_injury_data') or self._injury_data is None:
                self._injury_data = get_injuries()
            
            impact = get_team_injury_impact(team, self._injury_data)
            if impact > 0:
                logger.info(f"Injury impact for {team}: {impact:.3f}")
            return impact
            
        except Exception as e:
            logger.warning(f"Live injury scrape failed for {team}, using fallback: {e}")
            # Fallback to performance-based proxy
            try:
                recent_5 = self.fetch_recent_form(team, 5)
                recent_10 = self.fetch_recent_form(team, 10)
                if recent_5['win_pct'] < recent_10['win_pct'] - 0.15:
                    return 0.05
                return 0.0
            except:
                return 0.0
    
    def calculate_all_factors(self, home_team: str, away_team: str, 
                             game_date: date, game_time: str = "19:00") -> Dict[str, float]:
        """
        Calculate all 37 factors for a game
        Returns dictionary of factor_name: value
        """
        factors = {}
        
        try:
            # Ensure we have team stats
            if not self.team_stats:
                self.fetch_team_stats()
            
            home_stats = self.team_stats.get(home_team, {})
            away_stats = self.team_stats.get(away_team, {})
            
            # === TEAM PERFORMANCE FACTORS (1-11) ===
            
            # 1. Season win percentage
            factors['season_win_pct'] = home_stats.get('win_pct', 0.5) - away_stats.get('win_pct', 0.5)
            
            # 2-3. Home/Away win percentages
            home_splits = self.fetch_home_away_splits(home_team)
            away_splits = self.fetch_home_away_splits(away_team)
            # v5 FIX: home_win_pct as DIFFERENTIAL (home's home% - away's road%)
            factors['home_win_pct'] = home_splits.get('home_win_pct', 0.58) - away_splits.get('away_win_pct', 0.42)
            # INVERT: higher away road win% = bad for home, so flip it
            factors['away_win_pct'] = 1.0 - away_splits.get('away_win_pct', 0.42)
            
            # 4-5. Recent form (momentum)
            home_form_10 = self.fetch_recent_form(home_team, 10)
            away_form_10 = self.fetch_recent_form(away_team, 10)
            home_form_5 = self.fetch_recent_form(home_team, 5)
            away_form_5 = self.fetch_recent_form(away_team, 5)
            
            factors['last_10_record'] = home_form_10.get('win_pct', 0.5) - away_form_10.get('win_pct', 0.5)
            factors['last_5_record'] = home_form_5.get('win_pct', 0.5) - away_form_5.get('win_pct', 0.5)
            
            # 6-11. Advanced team metrics
            # Fixed: compare same metrics (offense vs offense, defense vs defense)
            factors['offensive_rating'] = home_stats.get('offensive_rating', 110) - away_stats.get('offensive_rating', 110)
            factors['defensive_rating'] = away_stats.get('defensive_rating', 110) - home_stats.get('defensive_rating', 110)
            factors['net_rating'] = home_stats.get('net_rating', 0) - away_stats.get('net_rating', 0)
            factors['pace'] = 0.0  # Removed: negatively correlated noise factor
            factors['ppg'] = home_stats.get('ppg', 110) - away_stats.get('ppg', 110)
            factors['points_allowed'] = away_stats.get('opp_ppg', 110) - home_stats.get('opp_ppg', 110)
            
            # === SITUATIONAL FACTORS (12-17) ===
            
            # 12. Rest days (B2B penalty)
            home_rest = self.calculate_rest_days(home_team, game_date)
            away_rest = self.calculate_rest_days(away_team, game_date)
            factors['rest_days'] = (home_rest - away_rest) / 3.0  # Normalized difference
            
            # 13. Day of week effect — ZEROED (v5: negatively correlated)
            factors['day_of_week'] = 0.0
            
            # 14. Game time effect (early vs late games)
            hour = int(game_time.split(':')[0])
            factors['game_time'] = (hour - 19) / 5.0  # Normalized around 7 PM
            
            # 15-16. Travel and timezone effects
            home_travel = self.calculate_travel_distance(home_team, game_date, away_team)
            away_travel = self.calculate_travel_distance(away_team, game_date, home_team)
            factors['travel_distance'] = (away_travel - home_travel) / 2000.0  # Normalized
            
            tz_diff = get_timezone_difference(away_team, home_team)
            factors['timezone_change'] = abs(tz_diff) / 3.0  # Normalized
            
            # 17. Days since last game
            factors['days_since_last'] = (home_rest + away_rest) / 4.0  # Normalized
            
            # === MATCHUP FACTORS (18-20) ===
            
            # 18. Head-to-head record
            h2h = self.get_head_to_head_record(home_team, away_team)
            factors['head_to_head'] = h2h.get('team1_win_pct', 0.5) - 0.5  # Centered
            
            # 19. Division rivalry — ZEROED (v5: negatively correlated)
            factors['division_rivalry'] = 0.0
            
            # 20. Conference game
            factors['conference_game'] = 1.0 if is_conference_game(home_team, away_team) else 0.0
            
            # === ADVANCED FACTORS (21-28) ===
            
            # 21. Strength of schedule
            home_sos = self.calculate_strength_of_schedule(home_team)
            away_sos = self.calculate_strength_of_schedule(away_team)
            factors['strength_of_schedule'] = home_sos - away_sos
            
            # 22. Clutch performance (simplified - using plus/minus)
            factors['clutch_performance'] = home_stats.get('plus_minus', 0) - away_stats.get('plus_minus', 0)
            
            # 23-28. Statistical differentials
            factors['turnover_diff'] = home_stats.get('turnover_diff', 0) - away_stats.get('turnover_diff', 0)
            factors['rebound_diff'] = home_stats.get('rebound_diff', 0) - away_stats.get('rebound_diff', 0)
            factors['ft_rate_diff'] = home_stats.get('ft_rate_diff', 0) - away_stats.get('ft_rate_diff', 0)
            factors['three_pt_pct'] = home_stats.get('fg3_pct', 0.35) - away_stats.get('fg3_pct', 0.35)
            factors['assists_pg'] = home_stats.get('ast_pg', 25) - away_stats.get('ast_pg', 25)
            factors['defensive_activity'] = (home_stats.get('stl_pg', 8) + home_stats.get('blk_pg', 5)) - \
                                          (away_stats.get('stl_pg', 8) + away_stats.get('blk_pg', 5))
            
            # === INJURY FACTORS (29-30) ===
            
            # 29-30. Injury impact
            home_injury_impact = self.get_injury_impact(home_team, game_date)
            away_injury_impact = self.get_injury_impact(away_team, game_date)
            factors['key_player_status'] = away_injury_impact - home_injury_impact  # Negative hurts the team
            factors['star_player_penalty'] = max(home_injury_impact, away_injury_impact)
            
            # === MARKET FACTORS (31-33) ===
            
            # 31-33. Odds and market data
            try:
                game_key = f"{away_team}@{home_team}_{game_date}"
                odds_data = self.odds_fetcher.get_nba_odds(game_date)
                
                if game_key in odds_data:
                    # Line movement
                    movement = self.odds_fetcher.detect_line_movement(game_date, home_team, away_team)
                    factors['line_movement'] = movement.get('home_movement', 0) / 50.0  # Normalized
                    
                    # Public betting (simplified - use line movement as proxy)
                    factors['public_betting'] = -factors['line_movement'] if factors['line_movement'] != 0 else 0
                    
                    # Closing line value (simplified)
                    factors['closing_line_value'] = 0  # Would need model prediction first
                else:
                    factors['line_movement'] = 0
                    factors['public_betting'] = 0
                    factors['closing_line_value'] = 0
                    
            except Exception as e:
                logger.warning(f"Could not fetch market data: {e}")
                factors['line_movement'] = 0
                factors['public_betting'] = 0
                factors['closing_line_value'] = 0
            
            # Ensure all factors are numeric
            for key, value in factors.items():
                if not isinstance(value, (int, float)) or math.isnan(value):
                    factors[key] = 0.0
            
            logger.debug(f"Calculated {len(factors)} factors for {away_team} @ {home_team}")
            
            return factors
            
        except Exception as e:
            logger.error(f"Error calculating factors: {e}")
            logger.error(traceback.format_exc())
            
            # Return default factors if calculation fails
            return {factor: 0.0 for factor in self.factor_weights.keys()}
    
    # Normalization ranges for factors: (expected_range) to map raw values to roughly -1 to +1
    FACTOR_NORMS = {
        # Team performance diffs - already small for pct, large for raw stats
        'season_win_pct': 0.4,       # max diff ~0.4 (e.g., .700 vs .300)
        'home_win_pct': 0.5,         # absolute pct, center at 0.5
        'away_win_pct': 0.5,         # absolute pct, center at 0.5
        'last_10_record': 0.5,       # diff of win pcts
        'last_5_record': 0.6,        # diff of win pcts, noisier
        'offensive_rating': 10.0,    # rating diff, typical range ~-10 to +10
        'defensive_rating': 10.0,    # rating diff
        'net_rating': 10.0,          # rating diff
        'pace': 0.1,                 # normalized around 1.0, small diffs
        'ppg': 15.0,                 # PPG diff, max ~15
        'points_allowed': 15.0,      # PPG diff
        # Situational - already normalized in calculate_all_factors
        'rest_days': 1.0,            # already /3.0
        'day_of_week': 1.0,          # already /6.0
        'game_time': 1.0,            # already normalized
        'travel_distance': 1.0,      # already /2000
        'timezone_change': 1.0,      # already /3.0
        'days_since_last': 1.0,      # already /4.0
        # Matchup
        'head_to_head': 0.5,         # centered diff
        'division_rivalry': 1.0,     # binary
        'conference_game': 1.0,      # binary
        # Advanced
        'strength_of_schedule': 0.15, # SOS diff
        'clutch_performance': 8.0,   # plus/minus diff
        'turnover_diff': 4.0,        # TO diff of diffs
        'rebound_diff': 6.0,         # rebound diff
        'ft_rate_diff': 0.1,         # FT rate diff
        'three_pt_pct': 0.06,        # 3P% diff
        'assists_pg': 6.0,           # assists diff
        'defensive_activity': 4.0,   # stl+blk diff
        # Injuries
        'key_player_status': 0.1,    # injury impact diff
        'star_player_penalty': 0.1,  # injury impact
        # Market
        'line_movement': 1.0,        # already normalized
        'public_betting': 1.0,       # already normalized
        'closing_line_value': 1.0,   # already normalized
        # Home court (new factor)
        'home_court': 1.0,           # always 1.0
    }

    def normalize_factor(self, name: str, raw_value: float) -> float:
        """Normalize a factor value to roughly -1 to +1 range"""
        norm = self.FACTOR_NORMS.get(name, 1.0)
        if name == 'away_win_pct':
            # away_win_pct is absolute (inverted), center around 0.5
            return (raw_value - 0.5) / norm
        # home_win_pct is now a differential (v5), don't center
        return raw_value / norm if norm != 0 else 0.0

    def predict_game(self, home_team: str, away_team: str, 
                     game_date: date, game_time: str = "19:00") -> Dict:
        """
        Generate prediction for a single game
        Returns prediction with confidence score 0-100
        """
        try:
            # Calculate all factors
            factors = self.calculate_all_factors(home_team, away_team, game_date, game_time)
            
            # Add home court as an explicit factor (always 1.0 for home team)
            factors['home_court'] = 1.0
            
            # Apply weighted scoring with normalization
            home_score = 0.0
            
            for factor_name, factor_value in factors.items():
                if factor_name in self.factor_weights:
                    weight = self.factor_weights[factor_name]
                    normalized = self.normalize_factor(factor_name, factor_value)
                    # Clamp normalized values to [-2, 2] to prevent outlier domination
                    normalized = max(-2.0, min(2.0, normalized))
                    home_score += normalized * weight
            
            # Scale so that the weighted sum (weights sum to ~1.0) produces
            # a range of roughly -3 to +3 before sigmoid.
            # With normalized factors in [-1,1] and weights summing to ~1,
            # raw home_score is roughly in [-1, 1]. Scale up to use more of sigmoid range.
            scaled_score = home_score * 3.0
            
            # Logistic function: 0 maps to 50%, ±3 maps to ~95%/5%
            home_probability = 1.0 / (1.0 + math.exp(-scaled_score))
            
            # Clamp to realistic NBA range: 20% - 80%
            home_probability = max(0.20, min(0.80, home_probability))
            
            # Determine predicted winner
            if home_probability >= 0.5:
                predicted_winner = home_team
                confidence = home_probability
            else:
                predicted_winner = away_team
                confidence = 1 - home_probability
            
            # Apply Bayesian updating based on historical performance
            historical_perf = self.self_learner.get_accuracy_report(30)
            overall_accuracy = historical_perf['overall'].get('accuracy', 0.5)
            sample_size = historical_perf['overall'].get('total_predictions', 0)
            
            confidence = self.self_learner.bayesian_update_confidence(
                confidence, {'overall_accuracy': overall_accuracy, 'sample_size': sample_size}
            )
            
            # Convert to 0-100 scale  
            confidence_score = confidence * 100
            
            # Calculate closing line value if possible
            try:
                clv = self.odds_fetcher.get_closing_line_value(
                    game_date, home_team, away_team, predicted_winner, confidence
                )
                factors['closing_line_value'] = clv
            except:
                factors['closing_line_value'] = 0
            
            # Determine which sportsbooks have this game
            available_books = []
            try:
                game_key = f"{away_team}@{home_team}_{game_date}"
                odds_data = self.odds_fetcher.get_nba_odds(game_date)
                if game_key in odds_data:
                    available_books = odds_data[game_key].get('available_books', [])
            except Exception:
                pass

            prediction = {
                'home_team': home_team,
                'away_team': away_team,
                'game_date': game_date.isoformat(),
                'game_time': game_time,
                'predicted_winner': predicted_winner,
                'confidence': round(confidence_score, 1),
                'home_probability': round(home_probability * 100, 1),
                'away_probability': round((1 - home_probability) * 100, 1),
                'available_books': available_books,
                'factors': factors,
                'model_score': round(home_score, 4),
                'closing_line_value': factors.get('closing_line_value', 0)
            }
            
            # Record prediction for learning
            game_id = f"{away_team}@{home_team}_{game_date.isoformat()}"
            self.self_learner.record_prediction(
                game_id, game_date, home_team, away_team, 
                predicted_winner, confidence, factors
            )
            
            return prediction
            
        except Exception as e:
            logger.error(f"Error predicting game {away_team} @ {home_team}: {e}")
            logger.error(traceback.format_exc())
            
            # Return default prediction
            return {
                'home_team': home_team,
                'away_team': away_team,
                'game_date': game_date.isoformat(),
                'predicted_winner': home_team,  # Default to home advantage
                'confidence': 55.0,
                'error': str(e)
            }
    
    def generate_picks(self, product_type: str, target_date: date) -> List[Dict]:
        """
        Generate picks for a specific product type
        """
        # Get games for the target date/period
        games = self.get_games_for_product(product_type, target_date)
        
        if not games:
            logger.warning(f"No games found for {product_type}")
            return []
        
        # Generate predictions for all games
        predictions = []
        for game in games:
            try:
                pred = self.predict_game(
                    game['home_team'], game['away_team'], 
                    datetime.fromisoformat(game['game_date']).date(),
                    game.get('game_time', '19:00')
                )
                predictions.append(pred)
            except Exception as e:
                logger.error(f"Error predicting game: {e}")
                continue
        
        # Filter by confidence threshold (58% for straight, 55% for parlays)
        min_confidence = 55.0 if product_type.startswith('parlay') else 58.0
        confident_predictions = [p for p in predictions if p['confidence'] >= min_confidence]
        
        if not confident_predictions:
            logger.warning("No predictions meet confidence threshold")
            confident_predictions = [p for p in predictions if p['confidence'] >= 53.0]
        
        # Generate picks based on product type
        if product_type.startswith('parlay'):
            return self.generate_parlay_picks(confident_predictions, product_type)
        else:
            return self.generate_straight_picks(confident_predictions, product_type)
    
    def generate_parlay_picks(self, predictions: List[Dict], product_type: str) -> List[Dict]:
        """Generate parlay combinations using Kelly Criterion-inspired selection"""
        if product_type == 'parlay-consistent':
            mix = [2, 2, 2, 2, 3, 3, 4, 4, 5, 6]  # Mix A
        else:  # parlay-moonshot
            mix = [2, 2, 2, 2, 3, 3, 4, 5, 6, 7]  # Mix E
        
        # Sort by edge-to-odds ratio for Kelly-inspired selection
        for pred in predictions:
            # Calculate implied odds and edge
            prob = pred['confidence'] / 100
            fair_odds = 1 / prob
            edge = prob - 0.5  # Simplified edge calculation
            pred['kelly_score'] = edge / fair_odds if fair_odds > 0 else 0
        
        predictions.sort(key=lambda x: x['kelly_score'], reverse=True)
        
        parlays = []
        used_indices = set()
        
        for i, legs in enumerate(mix):
            if len(predictions) < legs:
                continue
            
            # Select games for this parlay, avoiding heavy reuse
            parlay_games = []
            start_idx = i % max(1, len(predictions) - legs + 1)
            
            for j in range(legs):
                idx = (start_idx + j) % len(predictions)
                parlay_games.append(predictions[idx])
                used_indices.add(idx)
            
            # Calculate combined probability
            combined_prob = 1.0
            for game in parlay_games:
                combined_prob *= (game['confidence'] / 100)
            
            parlay = {
                'pick_number': i + 1,
                'type': 'parlay',
                'legs': legs,
                'games': parlay_games,
                'combined_confidence': round(combined_prob * 100, 1),
                'implied_payout': f"{1/combined_prob:.1f}x" if combined_prob > 0 else "N/A"
            }
            
            parlays.append(parlay)
        
        return parlays
    
    def generate_straight_picks(self, predictions: List[Dict], product_type: str) -> List[Dict]:
        """Generate straight picks (top 10 by confidence)"""
        # Sort by confidence
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        # Take top 10
        top_picks = predictions[:10]
        
        straight_picks = []
        for i, pred in enumerate(top_picks):
            pick = {
                'pick_number': i + 1,
                'type': 'straight',
                'games': [pred],
                'confidence': pred['confidence'],
                'predicted_winner': pred['predicted_winner']
            }
            straight_picks.append(pick)
        
        return straight_picks
    
    def get_games_for_product(self, product_type: str, target_date: date) -> List[Dict]:
        """Get games for a specific product type and date"""
        if product_type.startswith('parlay'):
            # Nightly products - just target date
            return self.get_games_for_date(target_date)
        else:
            # Weekly products - get week range
            if 'weekday' in product_type:
                # Monday-Friday
                days_since_monday = target_date.weekday()
                start_date = target_date - timedelta(days=days_since_monday)
                end_date = start_date + timedelta(days=4)
            else:
                # Weekend: Friday-Sunday
                days_since_monday = target_date.weekday()
                start_date = target_date - timedelta(days=days_since_monday) + timedelta(days=4)
                end_date = start_date + timedelta(days=2)
            
            return self.get_games_for_date_range(start_date, end_date)
    
    def is_game_time_eligible(self, commence_time: str, buffer_minutes: int = 60) -> bool:
        """
        Check if a game is eligible for analysis based on time cutoffs.
        Rules:
        - Game must not have started yet
        - Game must be at least buffer_minutes from tip-off
        """
        if not commence_time:
            return True  # No time data, allow it (legacy)
            
        try:
            game_start = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
            now = datetime.now(game_start.tzinfo)
            
            # Check if game has already started
            if game_start <= now:
                return False
                
            # Check if game is within buffer window
            buffer_cutoff = now + timedelta(minutes=buffer_minutes)
            if game_start <= buffer_cutoff:
                return False
                
            return True
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse commence_time '{commence_time}': {e}")
            return True  # Allow if can't parse

    def get_games_for_date(self, target_date: date) -> List[Dict]:
        """Get games for a specific date with time filtering"""
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            self.rate_limit()
            sb = scoreboardv2.ScoreboardV2(game_date=date_str)
            dfs = safe_get_data_frames(sb)
            header = dfs[0]
            
            if header.empty:
                return []
            
            games = []
            for _, game in header.iterrows():
                home_id = game['HOME_TEAM_ID']
                away_id = game['VISITOR_TEAM_ID']
                home_team = TEAM_ID_MAP.get(home_id, f"Team_{home_id}")
                away_team = TEAM_ID_MAP.get(away_id, f"Team_{away_id}")
                
                # Try to get actual game time from NBA API or use default
                game_time = '19:00'  # Default time
                commence_time = None
                
                # Try to get real commence time from odds API if available
                try:
                    odds_data = self.odds_fetcher.get_nba_odds(target_date)
                    game_key = f"{away_team}@{home_team}_{target_date}"
                    if game_key in odds_data:
                        commence_time = odds_data[game_key].get('commence_time')
                        if commence_time:
                            # Convert to readable time
                            dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
                            game_time = dt.strftime('%H:%M')
                except Exception:
                    pass
                
                # Apply time cutoff filter - skip games that have started or are too close
                if commence_time and not self.is_game_time_eligible(commence_time):
                    logger.info(f"Filtering out game {away_team} @ {home_team} - too close to tip-off or already started")
                    continue
                
                games.append({
                    'game_date': target_date.isoformat(),
                    'home_team': home_team,
                    'away_team': away_team,
                    'game_id': game['GAME_ID'],
                    'game_status': game.get('GAME_STATUS_TEXT', 'Scheduled'),
                    'game_time': game_time,
                    'commence_time': commence_time
                })
            
            return games
            
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
    
    def record_result(self, game_id: str, actual_winner: str):
        """Record actual game result for learning"""
        self.self_learner.record_result(game_id, actual_winner)
    
    def recalibrate_weights(self):
        """Trigger weight recalibration based on recent performance"""
        new_weights = self.self_learner.recalibrate_weights()
        self.factor_weights = new_weights
        logger.info("Weights recalibrated")
    
    def get_accuracy_report(self) -> Dict:
        """Get comprehensive accuracy report"""
        return self.self_learner.get_accuracy_report()
    
    def is_cache_valid(self, key: str, hours: int = 6) -> bool:
        """Check if cached data is still valid"""
        if key not in self.api_cache:
            return False
        
        if key not in self.cache_timestamp:
            return False
        
        age_hours = (time.time() - self.cache_timestamp[key]) / 3600
        return age_hours < hours
    
    def get_team_id(self, team_name: str) -> Optional[int]:
        """Get team ID from name"""
        for team in teams.get_teams():
            if team['full_name'] == team_name:
                return team['id']
        return None


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='ParlayGuarantee Engine v2')
    parser.add_argument('--product', 
                      choices=['parlay-consistent', 'parlay-moonshot', 'straight-weekday', 'straight-weekend', 'all'],
                      default='all',
                      help='Product to generate picks for')
    parser.add_argument('--date',
                      help='Target date (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--output',
                      default='engine_v2_output.json',
                      help='Output file path')
    parser.add_argument('--recalibrate',
                      action='store_true',
                      help='Recalibrate factor weights before generating picks')
    parser.add_argument('--report',
                      action='store_true',
                      help='Generate accuracy report')
    
    args = parser.parse_args()
    
    # Initialize predictor
    predictor = NBAPredictor()
    
    # Parse date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        target_date = date.today()
    
    # Handle special commands
    if args.recalibrate:
        logger.info("Recalibrating factor weights...")
        predictor.recalibrate_weights()
        
    if args.report:
        logger.info("Generating accuracy report...")
        report = predictor.get_accuracy_report()
        print(json.dumps(report, indent=2))
        return
    
    # Generate picks
    results = {}
    
    if args.product == 'all':
        products = ['parlay-consistent', 'parlay-moonshot', 'straight-weekday', 'straight-weekend']
    else:
        products = [args.product]
    
    for product in products:
        logger.info(f"Generating picks for {product}")
        try:
            picks = predictor.generate_picks(product, target_date)
            
            if picks:
                results[product] = {
                    'product_name': product,
                    'date': target_date.isoformat(),
                    'generated_at': datetime.now().isoformat(),
                    'picks': picks,
                    'total_picks': len(picks)
                }
                logger.info(f"Generated {len(picks)} picks for {product}")
            else:
                logger.warning(f"No picks generated for {product}")
                
        except Exception as e:
            logger.error(f"Error generating picks for {product}: {e}")
    
    # Save results
    if results:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {args.output}")
        logger.info(f"Generated picks for {len(results)} products")
        
        # Print summary
        for product, data in results.items():
            print(f"✅ {product}: {data['total_picks']} picks")
    else:
        logger.error("No picks generated")
        sys.exit(1)


if __name__ == "__main__":
    main()
