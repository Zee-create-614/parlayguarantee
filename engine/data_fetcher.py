"""
Data fetcher module for ParlayGuarantee Engine
Handles all API interactions: NBA data, odds, and injury reports
"""
import requests
import time
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import json
from abc import ABC, abstractmethod

# NBA API imports
from nba_api.stats.endpoints import scoreboardv2 as scoreboard, leaguedashteamstats, teamgamelog
from nba_api.stats.endpoints import playergamelog, leaguegamefinder
from nba_api.stats.static import teams

from config import *

# Configure logging
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)


class BaseSportFetcher(ABC):
    """Abstract base class for sport-specific data fetchers"""
    
    @abstractmethod
    def get_todays_games(self) -> List[Dict]:
        pass
    
    @abstractmethod
    def get_team_stats(self) -> Dict:
        pass
    
    @abstractmethod
    def get_recent_games(self, team_id: str, games: int = 10) -> List[Dict]:
        pass


class NBADataFetcher(BaseSportFetcher):
    """NBA-specific data fetcher using nba_api"""
    
    def __init__(self):
        self.teams_data = teams.get_teams()
        logger.info("NBA Data Fetcher initialized")
    
    def get_todays_games(self) -> List[Dict]:
        """Get today's NBA games"""
        try:
            today = date.today().strftime("%Y-%m-%d")
            logger.info(f"Fetching NBA games for {today}")
            
            # Get scoreboard for today
            scoreboard_data = scoreboard.ScoreboardV2(game_date=today)
            games_data = scoreboard_data.get_normalized_dict()
            
            games = []
            if 'GameHeader' in games_data:
                for game in games_data['GameHeader']:
                    game_info = {
                        'game_id': game['GAME_ID'],
                        'home_team': game['HOME_TEAM_NAME'],
                        'away_team': game['VISITOR_TEAM_NAME'], 
                        'game_time': game['GAME_DATE_EST'],
                        'home_team_id': game['HOME_TEAM_ID'],
                        'away_team_id': game['VISITOR_TEAM_ID'],
                        'season': game['SEASON'],
                        'game_status': game['GAME_STATUS_TEXT']
                    }
                    games.append(game_info)
            
            logger.info(f"Found {len(games)} NBA games for today")
            time.sleep(API_DELAYS['nba_api'])
            return games
            
        except Exception as e:
            logger.error(f"Error fetching NBA games: {str(e)}")
            return []
    
    def get_team_stats(self, season: str = "2023-24") -> Dict:
        """Get current season team stats"""
        try:
            logger.info("Fetching NBA team stats")
            
            # Get team stats
            team_stats = leaguedashteamstats.LeagueDashTeamStats(season=season)
            stats_data = team_stats.get_normalized_dict()
            
            team_stats_dict = {}
            if 'LeagueDashTeamStats' in stats_data:
                for team in stats_data['LeagueDashTeamStats']:
                    team_name = team['TEAM_NAME']
                    team_stats_dict[team_name] = {
                        'team_id': team['TEAM_ID'],
                        'games_played': team['GP'],
                        'wins': team['W'],
                        'losses': team['L'],
                        'win_pct': team['W_PCT'],
                        'offensive_rating': team.get('OFF_RATING', 0),
                        'defensive_rating': team.get('DEF_RATING', 0),
                        'pace': team.get('PACE', 0),
                        'points_per_game': team['PTS'],
                        'opp_points_per_game': team.get('OPP_PTS', 0)
                    }
            
            logger.info(f"Fetched stats for {len(team_stats_dict)} NBA teams")
            time.sleep(API_DELAYS['nba_api'])
            return team_stats_dict
            
        except Exception as e:
            logger.error(f"Error fetching NBA team stats: {str(e)}")
            return {}
    
    def get_recent_games(self, team_id: int, games: int = 10) -> List[Dict]:
        """Get recent games for a team"""
        try:
            logger.info(f"Fetching last {games} games for team {team_id}")
            
            # Get team game log
            game_log = teamgamelog.TeamGameLog(team_id=team_id, season='2023-24')
            log_data = game_log.get_normalized_dict()
            
            recent_games = []
            if 'TeamGameLog' in log_data:
                for i, game in enumerate(log_data['TeamGameLog'][:games]):
                    game_info = {
                        'game_id': game['Game_ID'],
                        'game_date': game['GAME_DATE'],
                        'matchup': game['MATCHUP'],
                        'win_loss': game['WL'],
                        'points': game['PTS'],
                        'opp_points': game.get('OPP_PTS', 0),
                        'home_away': 'HOME' if 'vs.' in game['MATCHUP'] else 'AWAY'
                    }
                    recent_games.append(game_info)
            
            time.sleep(API_DELAYS['nba_api'])
            return recent_games
            
        except Exception as e:
            logger.error(f"Error fetching recent games for team {team_id}: {str(e)}")
            return []
    
    def get_head_to_head(self, team1_id: int, team2_id: int, seasons: int = 3) -> Dict:
        """Get head-to-head record between two teams"""
        try:
            logger.info(f"Fetching H2H record: {team1_id} vs {team2_id}")
            
            # This is a simplified version - in practice you'd query multiple seasons
            # For now, get current season H2H
            game_finder = leaguegamefinder.LeagueGameFinder(
                team_id_nullable=team1_id,
                vs_team_id_nullable=team2_id,
                season_nullable='2023-24'
            )
            
            games_data = game_finder.get_normalized_dict()
            
            h2h_record = {'wins': 0, 'losses': 0, 'games': []}
            if 'LeagueGameFinderResults' in games_data:
                for game in games_data['LeagueGameFinderResults']:
                    if game['WL'] == 'W':
                        h2h_record['wins'] += 1
                    else:
                        h2h_record['losses'] += 1
                    h2h_record['games'].append(game)
            
            time.sleep(API_DELAYS['nba_api'])
            return h2h_record
            
        except Exception as e:
            logger.error(f"Error fetching H2H record: {str(e)}")
            return {'wins': 0, 'losses': 0, 'games': []}


class OddsDataFetcher:
    """Fetcher for odds data from The Odds API"""
    
    def __init__(self):
        self.api_key = THE_ODDS_API_KEY
        self.base_url = THE_ODDS_BASE_URL
        logger.info("Odds Data Fetcher initialized")
    
    def get_odds(self, sport: str = 'basketball_nba') -> List[Dict]:
        """Get current odds for a sport"""
        if not self.api_key:
            logger.warning("THE_ODDS_API_KEY not set - skipping odds data")
            return []
        
        try:
            url = f"{self.base_url}/sports/{sport}/odds/"
            params = {
                'apiKey': self.api_key,
                'regions': 'us',
                'markets': 'h2h,spreads,totals',
                'oddsFormat': 'american',
                'dateFormat': 'iso'
            }
            
            logger.info(f"Fetching odds for {sport}")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            odds_data = response.json()
            logger.info(f"Fetched odds for {len(odds_data)} games")
            
            time.sleep(API_DELAYS['odds_api'])
            return odds_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching odds data: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching odds: {str(e)}")
            return []
    
    def get_usage_info(self) -> Dict:
        """Get API usage information"""
        if not self.api_key:
            return {'remaining': 0, 'used': 0}
        
        try:
            url = f"{self.base_url}/sports/"
            params = {'apiKey': self.api_key}
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Check headers for usage info
            remaining = response.headers.get('x-requests-remaining', 'Unknown')
            used = response.headers.get('x-requests-used', 'Unknown')
            
            return {
                'remaining': remaining,
                'used': used
            }
            
        except Exception as e:
            logger.error(f"Error fetching usage info: {str(e)}")
            return {'remaining': 'Unknown', 'used': 'Unknown'}


class InjuryDataFetcher:
    """Fetcher for injury data - simplified for demo"""
    
    def __init__(self):
        logger.info("Injury Data Fetcher initialized")
    
    def get_injury_report(self, team_names: List[str]) -> Dict:
        """Get injury reports for teams
        Note: This is a simplified version. In production, you'd integrate
        with a real injury API or scrape data from official sources.
        """
        try:
            # For demo purposes, return some sample injury data
            # In production, integrate with ESPN API, NBA.com, or other sources
            
            logger.info(f"Fetching injury reports for {len(team_names)} teams")
            
            # Simplified injury data structure
            injury_data = {}
            for team in team_names:
                injury_data[team] = {
                    'out': [],  # Players definitely out
                    'doubtful': [],  # Unlikely to play
                    'questionable': [],  # Game-time decisions
                    'probable': []  # Likely to play
                }
            
            # In real implementation, populate with actual data
            logger.info("Injury data fetched (demo mode)")
            return injury_data
            
        except Exception as e:
            logger.error(f"Error fetching injury data: {str(e)}")
            return {}


class DataFetcherOrchestrator:
    """Main orchestrator for all data fetching operations"""
    
    def __init__(self, sport: str = 'NBA'):
        self.sport = sport
        
        # Initialize sport-specific fetcher
        if sport == 'NBA':
            self.sport_fetcher = NBADataFetcher()
        else:
            raise NotImplementedError(f"Sport {sport} not yet implemented")
        
        self.odds_fetcher = OddsDataFetcher()
        self.injury_fetcher = InjuryDataFetcher()
        
        logger.info(f"Data Fetcher Orchestrator initialized for {sport}")
    
    def fetch_all_data(self) -> Dict:
        """Fetch all data needed for analysis"""
        logger.info("Starting comprehensive data fetch")
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'sport': self.sport,
            'games': [],
            'team_stats': {},
            'odds': [],
            'injuries': {},
            'api_usage': {}
        }
        
        try:
            # Get today's games
            games = self.sport_fetcher.get_todays_games()
            data['games'] = games
            
            # Get team stats
            team_stats = self.sport_fetcher.get_team_stats()
            data['team_stats'] = team_stats
            
            # Get odds data
            if self.sport == 'NBA':
                odds = self.odds_fetcher.get_odds('basketball_nba')
                data['odds'] = odds
            
            # Get injury reports
            team_names = [game['home_team'] for game in games] + [game['away_team'] for game in games]
            injuries = self.injury_fetcher.get_injury_report(team_names)
            data['injuries'] = injuries
            
            # Get API usage info
            usage_info = self.odds_fetcher.get_usage_info()
            data['api_usage'] = usage_info
            
            logger.info(f"Data fetch complete: {len(games)} games, {len(team_stats)} teams")
            return data
            
        except Exception as e:
            logger.error(f"Error in comprehensive data fetch: {str(e)}")
            return data


if __name__ == "__main__":
    # Test the data fetcher
    fetcher = DataFetcherOrchestrator()
    all_data = fetcher.fetch_all_data()
    
    print(f"\nFetched data for {len(all_data['games'])} games")
    print(f"Team stats for {len(all_data['team_stats'])} teams")
    print(f"Odds data for {len(all_data['odds'])} games")
    print(f"API usage: {all_data['api_usage']}")
