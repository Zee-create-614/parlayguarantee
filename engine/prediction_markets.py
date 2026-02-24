"""
Prediction Markets API Integration
Fetches sports betting odds from Kalshi and Polymarket
Maps market-implied probabilities to our games for confidence boosting
"""
import requests
import logging
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import re
import json

logger = logging.getLogger(__name__)

class PredictionMarketsAPI:
    """Base class for prediction market APIs"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ParlayGuarantee/1.0 (Sports Prediction Engine)',
            'Accept': 'application/json'
        })
    
    def safe_api_call(self, url: str, method: str = 'GET', **kwargs) -> Optional[Dict]:
        """Make API call with proper timeout and error handling"""
        try:
            logger.debug(f"API call: {method} {url}")
            
            # Set 30-second timeout as required
            kwargs.setdefault('timeout', 30)
            
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            return response.json()
        
        except requests.exceptions.Timeout:
            logger.warning(f"API timeout for {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"API error for {url}: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error for {url}: {str(e)}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error for {url}: {str(e)}")
            return None


class KalshiAPI(PredictionMarketsAPI):
    """Kalshi API client for sports prediction markets"""
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://trading-api.kalshi.com/trade-api/v2"
        logger.info("Initialized Kalshi API client")
    
    def fetch_sports_markets(self, sport: str = 'NBA') -> Dict[str, List[Dict]]:
        """
        Fetch sports markets from Kalshi
        Returns: Dict mapping game_key -> [market_data]
        """
        markets_data = {}
        
        try:
            # Get active markets
            markets_url = f"{self.base_url}/events"
            params = {
                'limit': 200,
                'status': 'open',
                'category': 'Sports'
            }
            
            events_response = self.safe_api_call(markets_url, params=params)
            if not events_response or 'events' not in events_response:
                logger.warning("No Kalshi events data received")
                return markets_data
            
            # Filter for NBA games
            nba_events = []
            for event in events_response['events']:
                title = event.get('title', '').upper()
                if sport.upper() in title:
                    nba_events.append(event)
            
            logger.info(f"Found {len(nba_events)} Kalshi {sport} events")
            
            # For each NBA event, fetch its markets
            for event in nba_events:
                event_ticker = event.get('event_ticker')
                if not event_ticker:
                    continue
                
                # Extract team names and date from event title
                game_key = self._extract_game_key_from_kalshi_title(event.get('title', ''))
                if not game_key:
                    continue
                
                # Fetch markets for this event
                markets_url = f"{self.base_url}/events/{event_ticker}/markets"
                markets_response = self.safe_api_call(markets_url)
                
                if markets_response and 'markets' in markets_response:
                    # Process market data to extract probabilities
                    market_probs = self._extract_probabilities_from_kalshi_markets(
                        markets_response['markets'], event.get('title', '')
                    )
                    
                    if market_probs:
                        markets_data[game_key] = market_probs
            
            logger.info(f"Successfully processed {len(markets_data)} Kalshi games")
            
        except Exception as e:
            logger.error(f"Error fetching Kalshi sports markets: {str(e)}")
        
        return markets_data
    
    def _extract_game_key_from_kalshi_title(self, title: str) -> Optional[str]:
        """Extract standardized game key from Kalshi event title"""
        try:
            # Kalshi titles often like "Will the Lakers beat the Warriors on Feb 19?"
            # Or "Lakers vs Warriors Feb 19 2026"
            title_upper = title.upper()
            
            # Common NBA team name mappings
            team_mappings = {
                'LAKERS': 'Los Angeles Lakers',
                'WARRIORS': 'Golden State Warriors', 
                'CELTICS': 'Boston Celtics',
                'NETS': 'Brooklyn Nets',
                'KNICKS': 'New York Knicks',
                'HEAT': 'Miami Heat',
                'BULLS': 'Chicago Bulls',
                'CAVS': 'Cleveland Cavaliers',
                'CAVALIERS': 'Cleveland Cavaliers',
                'PISTONS': 'Detroit Pistons',
                'PACERS': 'Indiana Pacers',
                'BUCKS': 'Milwaukee Bucks',
                'HAWKS': 'Atlanta Hawks',
                'HORNETS': 'Charlotte Hornets',
                'MAGIC': 'Orlando Magic',
                'SIXERS': 'Philadelphia 76ers',
                '76ERS': 'Philadelphia 76ers',
                'RAPTORS': 'Toronto Raptors',
                'WIZARDS': 'Washington Wizards',
                'NUGGETS': 'Denver Nuggets',
                'TIMBERWOLVES': 'Minnesota Timberwolves',
                'THUNDER': 'Oklahoma City Thunder',
                'BLAZERS': 'Portland Trail Blazers',
                'JAZZ': 'Utah Jazz',
                'CLIPPERS': 'LA Clippers',
                'KINGS': 'Sacramento Kings',
                'SUNS': 'Phoenix Suns',
                'MAVERICKS': 'Dallas Mavericks',
                'ROCKETS': 'Houston Rockets',
                'GRIZZLIES': 'Memphis Grizzlies',
                'PELICANS': 'New Orleans Pelicans',
                'SPURS': 'San Antonio Spurs'
            }
            
            # Try to find team names in the title
            found_teams = []
            for short_name, full_name in team_mappings.items():
                if short_name in title_upper:
                    found_teams.append(full_name)
            
            if len(found_teams) >= 2:
                # Sort teams alphabetically for consistent key format
                found_teams.sort()
                return f"{found_teams[0]}_{found_teams[1]}"
            
        except Exception as e:
            logger.debug(f"Error parsing Kalshi title '{title}': {str(e)}")
        
        return None
    
    def _extract_probabilities_from_kalshi_markets(self, markets: List[Dict], event_title: str) -> List[Dict]:
        """Extract team win probabilities from Kalshi market data"""
        try:
            market_data = []
            
            for market in markets:
                ticker = market.get('ticker', '')
                subtitle = market.get('subtitle', '')
                
                # Look for yes/no contracts (binary outcomes)
                if market.get('market_type') == 'binary':
                    yes_price = market.get('yes_bid')  # or yes_ask
                    no_price = market.get('no_bid')
                    
                    if yes_price is not None:
                        # Kalshi prices are in cents, so 0-100 range
                        yes_prob = float(yes_price) / 100.0
                        
                        # Try to determine which team this probability refers to
                        team = self._extract_team_from_kalshi_market_title(subtitle or ticker)
                        
                        if team and 0 <= yes_prob <= 1:
                            market_data.append({
                                'team': team,
                                'probability': yes_prob,
                                'market_type': 'win',
                                'source': 'kalshi',
                                'raw_price': yes_price
                            })
            
            return market_data
            
        except Exception as e:
            logger.debug(f"Error extracting Kalshi probabilities: {str(e)}")
            return []
    
    def _extract_team_from_kalshi_market_title(self, title: str) -> Optional[str]:
        """Extract team name from individual market title"""
        # This would need to be customized based on how Kalshi structures their market titles
        # For now, return None and rely on overall event parsing
        return None


class PolymarketAPI(PredictionMarketsAPI):
    """Polymarket API client for sports prediction markets"""
    
    def __init__(self):
        super().__init__()
        # Polymarket has a GraphQL API, but also has REST endpoints
        self.base_url = "https://gamma-api.polymarket.com"
        logger.info("Initialized Polymarket API client")
    
    def fetch_sports_markets(self, sport: str = 'NBA') -> Dict[str, List[Dict]]:
        """
        Fetch sports markets from Polymarket
        Returns: Dict mapping game_key -> [market_data]
        """
        markets_data = {}
        
        try:
            # Get events/markets - Polymarket structure may vary
            markets_url = f"{self.base_url}/events"
            params = {
                'limit': 200,
                'active': True,
                'category': 'sports'  # or similar
            }
            
            events_response = self.safe_api_call(markets_url, params=params)
            if not events_response:
                logger.warning("No Polymarket events data received")
                return markets_data
            
            # Process Polymarket response format
            # Note: This is a placeholder implementation since Polymarket API structure may vary
            events = events_response if isinstance(events_response, list) else events_response.get('events', [])
            
            nba_events = []
            for event in events:
                description = event.get('description', '').upper()
                question = event.get('question', '').upper()
                title = (description + ' ' + question).upper()
                
                if sport.upper() in title:
                    nba_events.append(event)
            
            logger.info(f"Found {len(nba_events)} Polymarket {sport} events")
            
            # Process each event
            for event in nba_events:
                game_key = self._extract_game_key_from_polymarket_event(event)
                if not game_key:
                    continue
                
                # Extract probabilities from token prices
                market_probs = self._extract_probabilities_from_polymarket_event(event)
                if market_probs:
                    markets_data[game_key] = market_probs
            
            logger.info(f"Successfully processed {len(markets_data)} Polymarket games")
            
        except Exception as e:
            logger.error(f"Error fetching Polymarket sports markets: {str(e)}")
        
        return markets_data
    
    def _extract_game_key_from_polymarket_event(self, event: Dict) -> Optional[str]:
        """Extract standardized game key from Polymarket event"""
        try:
            # Similar logic to Kalshi but adapted for Polymarket format
            description = event.get('description', '')
            question = event.get('question', '')
            title = description + ' ' + question
            
            # Use the same team mapping logic as Kalshi
            return self._extract_teams_from_title(title.upper())
            
        except Exception as e:
            logger.debug(f"Error parsing Polymarket event: {str(e)}")
            return None
    
    def _extract_teams_from_title(self, title: str) -> Optional[str]:
        """Shared team extraction logic"""
        team_mappings = {
            'LAKERS': 'Los Angeles Lakers',
            'WARRIORS': 'Golden State Warriors', 
            'CELTICS': 'Boston Celtics',
            'NETS': 'Brooklyn Nets',
            'KNICKS': 'New York Knicks',
            'HEAT': 'Miami Heat',
            'BULLS': 'Chicago Bulls',
            'CAVS': 'Cleveland Cavaliers',
            'CAVALIERS': 'Cleveland Cavaliers',
            'PISTONS': 'Detroit Pistons',
            'PACERS': 'Indiana Pacers',
            'BUCKS': 'Milwaukee Bucks',
            'HAWKS': 'Atlanta Hawks',
            'HORNETS': 'Charlotte Hornets',
            'MAGIC': 'Orlando Magic',
            'SIXERS': 'Philadelphia 76ers',
            '76ERS': 'Philadelphia 76ers',
            'RAPTORS': 'Toronto Raptors',
            'WIZARDS': 'Washington Wizards',
            'NUGGETS': 'Denver Nuggets',
            'TIMBERWOLVES': 'Minnesota Timberwolves',
            'THUNDER': 'Oklahoma City Thunder',
            'BLAZERS': 'Portland Trail Blazers',
            'JAZZ': 'Utah Jazz',
            'CLIPPERS': 'LA Clippers',
            'KINGS': 'Sacramento Kings',
            'SUNS': 'Phoenix Suns',
            'MAVERICKS': 'Dallas Mavericks',
            'ROCKETS': 'Houston Rockets',
            'GRIZZLIES': 'Memphis Grizzlies',
            'PELICANS': 'New Orleans Pelicans',
            'SPURS': 'San Antonio Spurs'
        }
        
        found_teams = []
        for short_name, full_name in team_mappings.items():
            if short_name in title:
                found_teams.append(full_name)
        
        if len(found_teams) >= 2:
            found_teams.sort()
            return f"{found_teams[0]}_{found_teams[1]}"
        
        return None
    
    def _extract_probabilities_from_polymarket_event(self, event: Dict) -> List[Dict]:
        """Extract team win probabilities from Polymarket event data"""
        try:
            market_data = []
            
            # Polymarket typically uses token prices to represent probabilities
            # Tokens are priced 0-1 where price = implied probability
            
            outcomes = event.get('outcomes', [])
            tokens = event.get('tokens', [])  # Alternative structure
            
            # Process outcomes if available
            for outcome in outcomes:
                outcome_text = outcome.get('text', '')
                price = outcome.get('price')  # Should be 0-1 range
                
                if price is not None and 0 <= float(price) <= 1:
                    team = self._extract_team_from_outcome_text(outcome_text)
                    if team:
                        market_data.append({
                            'team': team,
                            'probability': float(price),
                            'market_type': 'win',
                            'source': 'polymarket',
                            'raw_price': price
                        })
            
            # Alternative: process tokens structure
            for token in tokens:
                token_name = token.get('name', '')
                price = token.get('price')
                
                if price is not None and 0 <= float(price) <= 1:
                    team = self._extract_team_from_outcome_text(token_name)
                    if team:
                        market_data.append({
                            'team': team,
                            'probability': float(price),
                            'market_type': 'win',
                            'source': 'polymarket',
                            'raw_price': price
                        })
            
            return market_data
            
        except Exception as e:
            logger.debug(f"Error extracting Polymarket probabilities: {str(e)}")
            return []
    
    def _extract_team_from_outcome_text(self, text: str) -> Optional[str]:
        """Extract team name from outcome text"""
        # This would need customization based on Polymarket's outcome naming
        return None


class PredictionMarketsAggregator:
    """Aggregates data from multiple prediction market sources"""
    
    def __init__(self):
        self.kalshi_api = KalshiAPI()
        self.polymarket_api = PolymarketAPI()
        logger.info("Initialized PredictionMarketsAggregator")
    
    def fetch_all_sports_markets(self, sport: str = 'NBA') -> Dict[str, Dict]:
        """
        Fetch markets from all sources and aggregate
        Returns: Dict mapping game_key -> consolidated market data
        """
        logger.info(f"Fetching {sport} prediction markets from all sources...")
        
        all_markets = {}
        
        # Fetch from Kalshi
        logger.info("Fetching Kalshi markets...")
        kalshi_markets = self.kalshi_api.fetch_sports_markets(sport)
        
        # Fetch from Polymarket  
        logger.info("Fetching Polymarket markets...")
        polymarket_markets = self.polymarket_api.fetch_sports_markets(sport)
        
        # Merge and consolidate data
        all_game_keys = set(kalshi_markets.keys()) | set(polymarket_markets.keys())
        
        for game_key in all_game_keys:
            consolidated_data = {
                'game_key': game_key,
                'kalshi_data': kalshi_markets.get(game_key, []),
                'polymarket_data': polymarket_markets.get(game_key, []),
                'consolidated_probabilities': {}
            }
            
            # Extract team probabilities from each source
            kalshi_probs = self._extract_team_probabilities(kalshi_markets.get(game_key, []))
            polymarket_probs = self._extract_team_probabilities(polymarket_markets.get(game_key, []))
            
            # Merge probabilities by team
            all_teams = set(kalshi_probs.keys()) | set(polymarket_probs.keys())
            
            for team in all_teams:
                team_data = {
                    'kalshi_prob': kalshi_probs.get(team),
                    'polymarket_prob': polymarket_probs.get(team)
                }
                
                # Calculate consensus probability (average if both available)
                probs = [p for p in [team_data['kalshi_prob'], team_data['polymarket_prob']] if p is not None]
                if probs:
                    team_data['consensus_prob'] = sum(probs) / len(probs)
                
                consolidated_data['consolidated_probabilities'][team] = team_data
            
            all_markets[game_key] = consolidated_data
        
        logger.info(f"Consolidated {len(all_markets)} games from prediction markets")
        return all_markets
    
    def _extract_team_probabilities(self, market_data: List[Dict]) -> Dict[str, float]:
        """Extract team -> probability mapping from market data"""
        team_probs = {}
        
        for market in market_data:
            team = market.get('team')
            prob = market.get('probability')
            
            if team and prob is not None:
                team_probs[team] = float(prob)
        
        return team_probs
    
    def get_market_data_for_game(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Get market data for a specific game (helper method)"""
        # Generate game key (same format as used in fetching)
        teams = sorted([home_team, away_team])
        game_key = f"{teams[0]}_{teams[1]}"
        
        all_markets = self.fetch_all_sports_markets()
        return all_markets.get(game_key)


# Convenience function for easy import
def get_prediction_markets_data(sport: str = 'NBA') -> Dict[str, Dict]:
    """
    Convenience function to get all prediction markets data
    Returns: Dict mapping game_key -> market data
    """
    aggregator = PredictionMarketsAggregator()
    return aggregator.fetch_all_sports_markets(sport)


if __name__ == "__main__":
    # Test the APIs
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Prediction Markets APIs...")
    
    markets_data = get_prediction_markets_data('NBA')
    
    print(f"\nFound data for {len(markets_data)} games:")
    for game_key, data in markets_data.items():
        print(f"\n{game_key}:")
        for team, probs in data['consolidated_probabilities'].items():
            print(f"  {team}: Kalshi={probs.get('kalshi_prob')}, Polymarket={probs.get('polymarket_prob')}, Consensus={probs.get('consensus_prob')}")