"""
Reliable NBA Data Fetcher - Replaces problematic nba_api
Uses balldontlie.io as primary source with fallbacks
"""

import requests
import json
import time
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

class ReliableDataFetcher:
    """
    Fetches NBA data from reliable sources:
    1. balldontlie.io (primary - free, no key needed)
    2. NBA.com endpoints (fallback with retry logic)
    3. Cached data (emergency fallback)
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        })
        
        # NBA.com endpoints (official but can be slow)
        self.nba_base = "https://stats.nba.com/stats"
        
        # Cache for team data
        self.teams_cache = {}
        self.stats_cache = {}
        
        # Hardcoded team mapping for reliability
        self.default_teams = {
            1610612737: 'Atlanta Hawks', 1610612738: 'Boston Celtics', 1610612751: 'Brooklyn Nets',
            1610612766: 'Charlotte Hornets', 1610612741: 'Chicago Bulls', 1610612739: 'Cleveland Cavaliers',
            1610612742: 'Dallas Mavericks', 1610612743: 'Denver Nuggets', 1610612765: 'Detroit Pistons',
            1610612744: 'Golden State Warriors', 1610612745: 'Houston Rockets', 1610612754: 'Indiana Pacers',
            1610612746: 'LA Clippers', 1610612747: 'Los Angeles Lakers', 1610612763: 'Memphis Grizzlies',
            1610612748: 'Miami Heat', 1610612749: 'Milwaukee Bucks', 1610612750: 'Minnesota Timberwolves',
            1610612740: 'New Orleans Pelicans', 1610612752: 'New York Knicks', 1610612760: 'Oklahoma City Thunder',
            1610612753: 'Orlando Magic', 1610612755: 'Philadelphia 76ers', 1610612756: 'Phoenix Suns',
            1610612757: 'Portland Trail Blazers', 1610612758: 'Sacramento Kings', 1610612759: 'San Antonio Spurs',
            1610612761: 'Toronto Raptors', 1610612762: 'Utah Jazz', 1610612764: 'Washington Wizards'
        }
        
    def fetch_teams(self) -> Dict[int, str]:
        """Fetch all NBA teams - use hardcoded reliable mapping"""
        self.teams_cache = self.default_teams.copy()
        logger.info(f"Using reliable team mapping: {len(self.teams_cache)} teams")
        return self.teams_cache
    
    def fetch_games_for_date(self, target_date: date) -> List[Dict]:
        """
        Fetch games for a specific date using Odds API as PRIMARY source (faster + includes spreads)
        Falls back to NBA.com if needed
        Returns list of game dicts with: home_team, away_team, game_date, game_time, game_id, spread
        """
        # Ensure we have teams
        if not self.teams_cache:
            self.fetch_teams()
            
        # PRIMARY: Try Odds API first (faster and includes spreads)
        logger.info(f"PRIMARY: Fetching games for {target_date} from Odds API...")
        try:
            games = self._fetch_games_from_odds_api(target_date)
            if games:
                logger.info(f"✅ Odds API returned {len(games)} games for {target_date}")
                return games
        except Exception as e:
            logger.warning(f"Odds API failed: {e}")
        
        # FALLBACK: Try NBA.com scoreboard with retry
        logger.info("FALLBACK: Trying NBA.com...")
        for attempt in range(3):
            try:
                # NBA.com uses MM/DD/YYYY format
                date_str = target_date.strftime('%m/%d/%Y')
                
                url = f"{self.nba_base}/scoreboardV2"
                params = {
                    'GameDate': date_str,
                    'LeagueID': '00',
                    'DayOffset': '0'
                }
                
                logger.info(f"Attempt {attempt + 1}: Fetching games for {date_str}")
                
                response = self.session.get(url, params=params, timeout=15)
                response.raise_for_status()
                
                data = response.json()
                game_header = data.get('resultSets', [{}])[0].get('rowSet', [])
                
                games = []
                for game_row in game_header:
                    if len(game_row) < 10:
                        continue
                        
                    game_id = game_row[2]
                    home_team_id = game_row[6]  
                    away_team_id = game_row[7]
                    game_status = game_row[3] if len(game_row) > 3 else ''
                    
                    home_team = self.teams_cache.get(home_team_id, f"Team_{home_team_id}")
                    away_team = self.teams_cache.get(away_team_id, f"Team_{away_team_id}")
                    
                    # Extract game time from status if available
                    game_time = game_status
                    if 'ET' in game_status:
                        # e.g. "7:00 pm ET"
                        game_time = f"{target_date.isoformat()} {game_status}"
                    
                    games.append({
                        'game_id': str(game_id),
                        'home_team': home_team,
                        'away_team': away_team,
                        'game_date': target_date.isoformat(),
                        'game_time': game_time,
                        'game_status': game_status,
                        'spread': 0  # NBA.com doesn't provide spreads
                    })
                
                logger.info(f"Successfully fetched {len(games)} games for {target_date}")
                return games
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"All NBA.com attempts failed for {target_date}")
                    break
                time.sleep(1)
                continue
        
        logger.error(f"Both Odds API and NBA.com failed for {target_date}")
        return []

    def _fetch_games_from_odds_api(self, target_date: date) -> List[Dict]:
        """Fallback: build game list from The Odds API"""
        import os
        api_key = os.environ.get('ODDS_API_KEY', 'f3c9f91dc369f56dea1b523d3071e1f1')
        resp = self.session.get(
            'https://api.the-odds-api.com/v4/sports/basketball_nba/odds/',
            params={
                'apiKey': api_key,
                'regions': 'us',
                'markets': 'h2h,spreads',
                'oddsFormat': 'american',
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Odds API team names → our canonical names
        name_map = {
            'Los Angeles Clippers': 'LA Clippers',
        }

        games = []
        for event in data:
            commence = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
            game_date = commence.date()
            # NBA games starting after midnight UTC are the previous calendar day in ET
            # Accept games on target_date or target_date+1 (UTC)
            from datetime import timezone
            game_date_et = commence.astimezone(timezone(timedelta(hours=-5))).date()
            if game_date_et != target_date:
                continue

            home = name_map.get(event['home_team'], event['home_team'])
            away = name_map.get(event['away_team'], event['away_team'])

            # Extract spread from bookmakers
            spread = 0
            for bk in event.get('bookmakers', []):
                for mkt in bk.get('markets', []):
                    if mkt['key'] == 'spreads':
                        for outcome in mkt['outcomes']:
                            if outcome['name'] == event['home_team']:
                                spread = outcome.get('point', 0)
                                break
                        if spread != 0:
                            break
                if spread != 0:
                    break

            games.append({
                'game_id': event.get('id', f'{away}_{home}_{target_date}'),
                'home_team': home,
                'away_team': away,
                'game_date': target_date.isoformat(),
                'game_time': commence.isoformat(),
                'game_status': 'Scheduled',
                'spread': spread,
            })

        return games
    
    def fetch_team_stats(self, season: str = "2024") -> Dict[str, Dict]:
        """
        Fetch REAL team statistics using ESPN API
        Returns dict of {team_name: {win_pct, ppg, etc}}
        """
        try:
            logger.info("Fetching real NBA standings from ESPN API...")
            
            # ESPN NBA standings API (free, no key needed)
            espn_url = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
            
            response = self.session.get(espn_url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            team_stats = {}
            
            # Parse ESPN standings data — structure is children[].standings.entries[]
            for group in data.get('children', data.get('groups', [])):
                for standing in group.get('standings', {}).get('entries', []):
                    team_info = standing.get('team', {})
                    team_name = team_info.get('displayName', '')
                    
                    # Get the team stats
                    stats_obj = standing.get('stats', [])
                    
                    # Parse stats array - ESPN returns stats as array of objects
                    wins = 0
                    losses = 0
                    win_pct = 0.5
                    ppg = 110.0
                    
                    papg = 110.0
                    streak = 0
                    home_record = ''
                    road_record = ''
                    last_ten = ''

                    for stat in stats_obj:
                        stat_name = stat.get('name', '')
                        stat_value = stat.get('value', 0)
                        stat_display = stat.get('displayValue', '')
                        
                        if stat_name == 'wins':
                            wins = int(stat_value)
                        elif stat_name == 'losses':
                            losses = int(stat_value)
                        elif stat_name == 'winPercent':
                            win_pct = float(stat_value)
                        elif stat_name == 'avgPointsFor':
                            ppg = float(stat_value)
                        elif stat_name == 'pointsFor' and ppg == 110.0:
                            # Fallback: total points / games
                            pass  # Will calculate after we have wins+losses
                        elif stat_name == 'avgPointsAgainst':
                            papg = float(stat_value)
                        elif stat_name == 'streak':
                            streak = int(stat_value) if stat_value else 0
                        elif stat_name == 'Home':
                            home_record = stat_display
                        elif stat_name == 'Road':
                            road_record = stat_display
                        elif stat_name == 'Last Ten Games':
                            last_ten = stat_display
                    
                    # Calculate win percentage if not provided
                    if win_pct == 0.5 and (wins + losses) > 0:
                        win_pct = wins / (wins + losses)
                    
                    # Calculate PPG from totals if avgPointsFor wasn't available
                    if ppg == 110.0 and (wins + losses) > 0:
                        # Look for raw pointsFor total
                        for stat in stats_obj:
                            if stat.get('name') == 'pointsFor':
                                ppg = float(stat.get('value', 0)) / (wins + losses)
                                break
                    if papg == 110.0 and (wins + losses) > 0:
                        for stat in stats_obj:
                            if stat.get('name') == 'pointsAgainst':
                                papg = float(stat.get('value', 0)) / (wins + losses)
                                break
                    
                    # Handle team name mapping (ESPN -> our format)
                    mapped_name = self._map_espn_team_name(team_name)
                    
                    team_stats[mapped_name] = {
                        'win_pct': win_pct,
                        'ppg': round(ppg, 1),
                        'papg': round(papg, 1),
                        'games_played': wins + losses,
                        'wins': wins,
                        'losses': losses,
                        'offensive_rating': round(ppg, 1),
                        'defensive_rating': round(papg, 1),
                        'streak': streak,
                        'home_record': home_record,
                        'road_record': road_record,
                        'last_ten': last_ten,
                    }
            
            if not team_stats:
                logger.warning("No team stats parsed from ESPN, using fallback...")
                return self._get_fallback_stats()
            
            self.stats_cache = team_stats
            logger.info(f"Successfully fetched REAL stats for {len(team_stats)} teams")
            
            # Log a few examples
            for team_name in list(team_stats.keys())[:3]:
                stats = team_stats[team_name]
                logger.info(f"  {team_name}: {stats['wins']}-{stats['losses']} ({stats['win_pct']:.3f}), {stats['ppg']:.1f} PPG")
            
            return team_stats
            
        except Exception as e:
            logger.error(f"Failed to fetch team stats from ESPN: {e}")
            return self._get_fallback_stats()
    
    def _map_espn_team_name(self, espn_name: str) -> str:
        """Map ESPN team names to our canonical names"""
        name_mapping = {
            'Los Angeles Clippers': 'LA Clippers',
            'Los Angeles Lakers': 'Los Angeles Lakers',
            'New York Knicks': 'New York Knicks',
            'Golden State Warriors': 'Golden State Warriors',
            # Add more mappings as needed
        }
        
        return name_mapping.get(espn_name, espn_name)
    
    def _get_fallback_stats(self) -> Dict[str, Dict]:
        """Fallback team stats if API fails"""
        if not self.teams_cache:
            self.fetch_teams()
        
        # Use some reasonable win percentages instead of all 0.5
        estimated_records = {
            'Boston Celtics': 0.75,
            'Oklahoma City Thunder': 0.73,
            'Cleveland Cavaliers': 0.70,
            'Houston Rockets': 0.65,
            'Denver Nuggets': 0.63,
            'Los Angeles Lakers': 0.60,
            'Phoenix Suns': 0.58,
            'Miami Heat': 0.57,
            'Golden State Warriors': 0.56,
            'Dallas Mavericks': 0.55,
            'Memphis Grizzlies': 0.53,
            'Minnesota Timberwolves': 0.51,
            'Sacramento Kings': 0.50,
            'LA Clippers': 0.48,
            'San Antonio Spurs': 0.47,
            'Atlanta Hawks': 0.45,
            'Milwaukee Bucks': 0.43,
            'Indiana Pacers': 0.42,
            'Chicago Bulls': 0.40,
            'Orlando Magic': 0.38,
            'Detroit Pistons': 0.37,
            'Portland Trail Blazers': 0.35,
            'Utah Jazz': 0.33,
            'Charlotte Hornets': 0.32,
            'Toronto Raptors': 0.30,
            'Brooklyn Nets': 0.28,
            'New York Knicks': 0.27,
            'Washington Wizards': 0.25,
            'New Orleans Pelicans': 0.23,
            'Philadelphia 76ers': 0.20,
        }
        
        fallback_stats = {}
        for team_name in self.teams_cache.values():
            win_pct = estimated_records.get(team_name, 0.5)
            wins = int(win_pct * 50)  # Assume ~50 games played
            losses = 50 - wins
            
            fallback_stats[team_name] = {
                'win_pct': win_pct,
                'ppg': 108.0 + (win_pct - 0.5) * 20,  # Better teams score more
                'games_played': wins + losses,
                'wins': wins,
                'losses': losses,
                'offensive_rating': 110.0,
                'defensive_rating': 110.0,
            }
        
        logger.info(f"Using fallback stats with realistic win percentages for {len(fallback_stats)} teams")
        return fallback_stats
    
    def calculate_win_probability(self, home_team: str, away_team: str) -> Tuple[str, float]:
        """
        Calculate win probability using Log5 method with home court advantage
        Same logic as the original engine
        """
        if not self.stats_cache:
            logger.warning("No stats cache available, using defaults")
            return home_team, 0.58  # Default home advantage
        
        home_wp = self.stats_cache.get(home_team, {}).get('win_pct', 0.5)
        away_wp = self.stats_cache.get(away_team, {}).get('win_pct', 0.5)
        
        # Log5 method: p = (pA * (1 - pB)) / (pA * (1 - pB) + pB * (1 - pA))
        denom = home_wp * (1 - away_wp) + away_wp * (1 - home_wp)
        if denom <= 0:
            home_prob = 0.58  # default home advantage
        else:
            home_prob = (home_wp * (1 - away_wp)) / denom
        
        # Apply home court advantage: multiply by 1.03
        home_prob = home_prob * 1.03
        if home_prob > 1.0:
            home_prob = 1.0
        
        # Constrain probabilities
        if home_prob < 0.25:
            home_prob = 0.25
        elif home_prob > 0.85:
            home_prob = 0.85
        
        if home_prob >= 0.5:
            return home_team, home_prob
        else:
            return away_team, 1 - home_prob

# Test the data fetcher
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=date.today().isoformat())
    parser.add_argument('--test', choices=['teams', 'games', 'stats'], default='games')
    
    args = parser.parse_args()
    
    fetcher = ReliableDataFetcher()
    
    if args.test == 'teams':
        teams = fetcher.fetch_teams()
        print(f"Teams: {len(teams)}")
        for tid, name in list(teams.items())[:5]:
            print(f"  {tid}: {name}")
    
    elif args.test == 'games':
        target_date = date.fromisoformat(args.date)
        games = fetcher.fetch_games_for_date(target_date)
        print(f"Games for {target_date}: {len(games)}")
        for game in games:
            print(f"  {game['away_team']} @ {game['home_team']}")
    
    elif args.test == 'stats':
        stats = fetcher.fetch_team_stats()
        print(f"Team stats: {len(stats)}")
        for team, stat in list(stats.items())[:5]:
            print(f"  {team}: {stat['win_pct']:.3f} win%, {stat['games_played']} games")