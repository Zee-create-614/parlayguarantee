"""
Odds API Integration for Engine v2
Fetches live odds, line movements, and public betting data
"""

import requests
import json
import logging
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import sqlite3

logger = logging.getLogger(__name__)

ALLOWED_BOOKMAKERS = {"draftkings", "fanduel", "betmgm"}

BOOKMAKER_DISPLAY_NAMES = {
    "draftkings": "DraftKings",
    "fanduel": "FanDuel",
    "betmgm": "BetMGM",
    "pointsbetus": "PointsBet",
    "betrivers": "BetRivers",
    "bovada": "Bovada",
    "mybookieag": "MyBookie",
    "williamhill_us": "Caesars",
    "barstool": "ESPN BET",
    "unibet_us": "Unibet",
    "wynnbet": "WynnBET",
    "superbook": "SuperBook",
    "twinspires": "TwinSpires",
    "betus": "BetUS",
    "lowvig": "LowVig",
    "betfair": "Betfair",
    "betonlineag": "BetOnline",
    "fanatics": "Fanatics",
}

def normalize_bookmaker_name(raw_key: str, raw_title: str = "") -> str:
    """Convert Odds API bookmaker key/title to display-friendly name."""
    key_lower = raw_key.lower()
    if key_lower in BOOKMAKER_DISPLAY_NAMES:
        return BOOKMAKER_DISPLAY_NAMES[key_lower]
    # Try matching the title (Odds API sometimes uses 'title' field directly)
    title_lower = raw_title.lower()
    if title_lower in BOOKMAKER_DISPLAY_NAMES:
        return BOOKMAKER_DISPLAY_NAMES[title_lower]
    # Fallback: return the title as-is (already display-friendly from API)
    return raw_title or raw_key


class OddsFetcher:
    """
    Integrates with The Odds API to fetch:
    - Current moneyline odds
    - Opening vs current odds (line movement)
    - Public betting percentages (when available)
    - Closing line values
    """
    
    def __init__(self, api_key: str = "f3c9f91dc369f56dea1b523d3071e1f1"):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        self.db_path = "odds_data.db"
        self.init_database()
        
        # Rate limiting - Odds API allows 500 requests per month on free tier
        self.last_request = 0
        self.min_request_interval = 1.0  # 1 second between requests
        
    def init_database(self):
        """Initialize SQLite database for odds storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Odds history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS odds_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date DATE,
                home_team TEXT,
                away_team TEXT,
                bookmaker TEXT,
                home_odds REAL,
                away_odds REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_date, home_team, away_team, bookmaker, timestamp)
            )
        ''')
        
        # Line movements table  
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS line_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date DATE,
                home_team TEXT,
                away_team TEXT,
                opening_home_odds REAL,
                opening_away_odds REAL,
                current_home_odds REAL,
                current_away_odds REAL,
                movement_home REAL,
                movement_away REAL,
                sharp_money_indicator TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_date, home_team, away_team)
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make rate-limited request to Odds API"""
        # Rate limiting
        now = time.time()
        if now - self.last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - (now - self.last_request))
        
        url = f"{self.base_url}/{endpoint}"
        if params is None:
            params = {}
        params['apiKey'] = self.api_key
        
        try:
            response = requests.get(url, params=params, timeout=30)
            self.last_request = time.time()
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Odds API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching odds: {e}")
            return None
    
    def get_nba_odds(self, target_date: date = None) -> Dict[str, Dict]:
        """
        Fetch current NBA moneyline odds
        Returns: {game_key: {home_team, away_team, odds_data}}
        """
        if target_date is None:
            target_date = date.today()
            
        # Convert date to ISO format for API
        date_str = target_date.isoformat()
        
        # US sports typically tip off 12pm-11pm EST = 17:00 UTC to 04:00 UTC next day
        # Extend window to catch all games on the US calendar date
        next_date_str = (target_date + timedelta(days=1)).isoformat()
        
        params = {
            'sport': 'basketball_nba',
            'regions': 'us',  
            'markets': 'h2h',  # head-to-head (moneyline)
            'oddsFormat': 'american',
            'dateFormat': 'iso',
            'bookmakers': ','.join(sorted(ALLOWED_BOOKMAKERS)),
            'commenceTimeFrom': f"{date_str}T10:00:00Z",
            'commenceTimeTo': f"{next_date_str}T06:00:00Z"
        }
        
        data = self.make_request("sports/basketball_nba/odds", params)
        if not data:
            return {}
        
        games_odds = {}
        
        for game in data:
            home_team = game['home_team']
            away_team = game['away_team'] 
            game_key = f"{away_team}@{home_team}_{target_date}"
            
            # Extract odds from different bookmakers
            bookmaker_odds = {}
            
            for bookmaker in game.get('bookmakers', []):
                bookie_key = bookmaker.get('key', '')
                if bookie_key.lower() not in ALLOWED_BOOKMAKERS:
                    continue
                bookie_title = bookmaker.get('title', bookie_key)
                bookie_name = normalize_bookmaker_name(bookie_key, bookie_title)
                
                for market in bookmaker.get('markets', []):
                    if market['key'] == 'h2h':
                        odds_data = {}
                        for outcome in market['outcomes']:
                            team = outcome['name']
                            price = outcome['price']
                            
                            if team == home_team:
                                odds_data['home_odds'] = price
                            elif team == away_team:
                                odds_data['away_odds'] = price
                        
                        if 'home_odds' in odds_data and 'away_odds' in odds_data:
                            bookmaker_odds[bookie_name] = odds_data
            
            if bookmaker_odds:
                games_odds[game_key] = {
                    'home_team': home_team,
                    'away_team': away_team,
                    'game_date': target_date.isoformat(),
                    'commence_time': game.get('commence_time'),
                    'bookmakers': bookmaker_odds
                }
        
        # Tag each game with available_books (normalized display names)
        for game_key, game_data in games_odds.items():
            available = []
            for bookie_name in game_data['bookmakers'].keys():
                # bookie_name here is the API 'title' field; try to normalize
                display = normalize_bookmaker_name(bookie_name, bookie_name)
                if display not in available:
                    available.append(display)
            game_data['available_books'] = sorted(available)
        
        # Store in database
        self.store_odds_data(games_odds)
        
        return games_odds
    
    def get_games_by_bookmaker(self, sport: str = 'basketball_nba', target_date: date = None) -> Dict[str, List[str]]:
        """
        Return a dict of {display_bookmaker_name: [game_key, ...]} for a given sport/date.
        Uses the same Odds API call as get_nba_odds but reorganizes by bookmaker.
        """
        if target_date is None:
            target_date = date.today()

        params = {
            'sport': sport,
            'regions': 'us',
            'markets': 'h2h',
            'oddsFormat': 'american',
            'dateFormat': 'iso',
            'bookmakers': ','.join(sorted(ALLOWED_BOOKMAKERS)),
            'commenceTimeFrom': f"{target_date.isoformat()}T00:00:00Z",
            'commenceTimeTo': f"{target_date.isoformat()}T23:59:59Z"
        }

        data = self.make_request(f"sports/{sport}/odds", params)
        if not data:
            return {}

        books: Dict[str, List[str]] = {}
        for game in data:
            home_team = game['home_team']
            away_team = game['away_team']
            game_key = f"{away_team}@{home_team}_{target_date}"

            for bookmaker in game.get('bookmakers', []):
                bookie_key = bookmaker.get('key', '')
                bookie_title = bookmaker.get('title', bookie_key)
                display = normalize_bookmaker_name(bookie_key, bookie_title)
                if display not in books:
                    books[display] = []
                if game_key not in books[display]:
                    books[display].append(game_key)

        return books

    def store_odds_data(self, odds_data: Dict):
        """Store odds data in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now()
        
        for game_key, game_data in odds_data.items():
            game_date = game_data['game_date']
            home_team = game_data['home_team']
            away_team = game_data['away_team']
            
            for bookmaker, odds in game_data['bookmakers'].items():
                cursor.execute('''
                    INSERT OR IGNORE INTO odds_history 
                    (game_date, home_team, away_team, bookmaker, home_odds, away_odds, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (game_date, home_team, away_team, bookmaker, 
                      odds['home_odds'], odds['away_odds'], timestamp))
        
        conn.commit()
        conn.close()
    
    def get_consensus_odds(self, game_key: str, odds_data: Dict) -> Tuple[float, float]:
        """
        Calculate consensus odds across bookmakers
        Returns: (home_odds, away_odds) as averages
        """
        if game_key not in odds_data:
            return 0, 0
        
        game = odds_data[game_key]
        bookmakers = game.get('bookmakers', {})
        
        if not bookmakers:
            return 0, 0
        
        home_odds_list = []
        away_odds_list = []
        
        for bookie, odds in bookmakers.items():
            home_odds_list.append(odds['home_odds'])
            away_odds_list.append(odds['away_odds'])
        
        avg_home = sum(home_odds_list) / len(home_odds_list)
        avg_away = sum(away_odds_list) / len(away_odds_list)
        
        return avg_home, avg_away
    
    def detect_line_movement(self, game_date: date, home_team: str, away_team: str) -> Dict:
        """
        Detect line movement by comparing historical odds
        Returns movement data and sharp money indicators
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get odds history for this game
        cursor.execute('''
            SELECT bookmaker, home_odds, away_odds, timestamp
            FROM odds_history 
            WHERE game_date = ? AND home_team = ? AND away_team = ?
            ORDER BY timestamp ASC
        ''', (game_date.isoformat(), home_team, away_team))
        
        history = cursor.fetchall()
        conn.close()
        
        if len(history) < 2:
            return {'movement_detected': False}
        
        # Get opening odds (first recorded)
        opening = history[0]
        opening_home, opening_away = opening[1], opening[2]
        
        # Get current odds (most recent)
        current = history[-1]  
        current_home, current_away = current[1], current[2]
        
        # Calculate movement
        home_movement = current_home - opening_home
        away_movement = current_away - opening_away
        
        # Detect sharp money indicators
        sharp_indicator = "neutral"
        
        # If favorite odds get longer (less negative), that's reverse line movement
        if opening_home < 0 and home_movement > 0:  # Home favorite got longer odds
            sharp_indicator = "sharp_on_away"
        elif opening_away < 0 and away_movement > 0:  # Away favorite got longer odds  
            sharp_indicator = "sharp_on_home"
        
        # Significant movement threshold (25+ points)
        significant_movement = abs(home_movement) > 25 or abs(away_movement) > 25
        
        movement_data = {
            'movement_detected': True,
            'opening_home_odds': opening_home,
            'opening_away_odds': opening_away,
            'current_home_odds': current_home,
            'current_away_odds': current_away,
            'home_movement': home_movement,
            'away_movement': away_movement,
            'sharp_money_indicator': sharp_indicator,
            'significant_movement': significant_movement
        }
        
        # Store line movement data
        self.store_line_movement(game_date, home_team, away_team, movement_data)
        
        return movement_data
    
    def store_line_movement(self, game_date: date, home_team: str, away_team: str, movement_data: Dict):
        """Store line movement analysis in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO line_movements
            (game_date, home_team, away_team, opening_home_odds, opening_away_odds,
             current_home_odds, current_away_odds, movement_home, movement_away, 
             sharp_money_indicator)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            game_date.isoformat(), home_team, away_team,
            movement_data['opening_home_odds'], movement_data['opening_away_odds'],
            movement_data['current_home_odds'], movement_data['current_away_odds'],
            movement_data['home_movement'], movement_data['away_movement'],
            movement_data['sharp_money_indicator']
        ))
        
        conn.commit()
        conn.close()
    
    def convert_american_to_probability(self, american_odds: float) -> float:
        """Convert American odds to implied probability"""
        if american_odds > 0:
            return 100 / (american_odds + 100)
        else:
            return abs(american_odds) / (abs(american_odds) + 100)
    
    def get_closing_line_value(self, game_date: date, home_team: str, away_team: str, 
                              predicted_winner: str, model_probability: float) -> float:
        """
        Calculate closing line value - how much better our model is vs market
        Positive CLV = we have an edge
        """
        # Get current market odds
        odds_data = self.get_nba_odds(game_date)
        game_key = f"{away_team}@{home_team}_{game_date}"
        
        if game_key not in odds_data:
            return 0.0
        
        # Get consensus odds
        home_odds, away_odds = self.get_consensus_odds(game_key, odds_data)
        
        if home_odds == 0 or away_odds == 0:
            return 0.0
        
        # Get market probability for our predicted winner
        if predicted_winner == home_team:
            market_prob = self.convert_american_to_probability(home_odds)
        else:
            market_prob = self.convert_american_to_probability(away_odds)
        
        # CLV = our probability - market probability 
        clv = model_probability - market_prob
        
        return clv
    
    def fetch_daily_odds(self, target_date: date = None) -> List[Dict]:
        """
        Fetch daily odds - wrapper around get_nba_odds for compatibility
        Returns list of odds dictionaries (not dict of dicts like get_nba_odds)
        """
        if target_date is None:
            target_date = date.today()
            
        logger.info(f"Fetching daily odds for {target_date}")
        
        # Get odds data in the dict format
        odds_data = self.get_nba_odds(target_date)
        
        # Convert to list format expected by tier_engine
        odds_list = []
        for game_key, game_data in odds_data.items():
            # Get consensus odds
            home_odds, away_odds = self.get_consensus_odds(game_key, {game_key: game_data})
            
            odds_list.append({
                'home_team': game_data['home_team'],
                'away_team': game_data['away_team'], 
                'game_date': game_data['game_date'],
                'commence_time': game_data.get('commence_time'),
                'home_odds': home_odds,
                'away_odds': away_odds,
                'bookmakers': game_data.get('bookmakers', {}),
                'available_books': game_data.get('available_books', []),
                'game_key': game_key
            })
        
        logger.info(f"Converted {len(odds_list)} games to odds list format")
        return odds_list
    
    def get_usage_stats(self) -> Dict:
        """Check API usage for monitoring"""
        # Note: The Odds API doesn't provide usage endpoints on free tier
        # This is a placeholder for tracking our own requests
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count requests today
        today = date.today()
        cursor.execute('''
            SELECT COUNT(DISTINCT game_date || home_team || away_team) 
            FROM odds_history 
            WHERE DATE(timestamp) = ?
        ''', (today.isoformat(),))
        
        requests_today = cursor.fetchone()[0]
        conn.close()
        
        return {
            'requests_today': requests_today,
            'estimated_monthly_usage': requests_today * 30,
            'free_tier_limit': 500
        }


if __name__ == "__main__":
    # Test the odds fetcher
    logging.basicConfig(level=logging.INFO)
    
    fetcher = OddsFetcher()
    
    # Test fetching odds for today
    odds = fetcher.get_nba_odds()
    print(f"Found odds for {len(odds)} games")
    
    for game_key, data in odds.items():
        print(f"{data['away_team']} @ {data['home_team']}")
        for bookie, odds_data in data['bookmakers'].items():
            print(f"  {bookie}: {odds_data['away_odds']}/{odds_data['home_odds']}")
        print()
    
    # Check usage
    usage = fetcher.get_usage_stats()
    print(f"API Usage: {usage}")