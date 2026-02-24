"""
Configuration file for ParlayGuarantee Engine
"""
import os
from datetime import timezone, timedelta

# API Keys (from environment variables)
THE_ODDS_API_KEY = os.environ.get('THE_ODDS_API_KEY')

# API URLs
THE_ODDS_BASE_URL = "https://api.the-odds-api.com/v4"
BALLDONTLIE_BASE_URL = "https://api.balldontlie.io/v1"

# Sports mappings
SPORTS = {
    'NBA': 'basketball_nba',
    'NFL': 'americanfootball_nfl', 
    'MLB': 'baseball_mlb',
    'NHL': 'icehockey_nhl',
    'MMA': 'mma_mixed_martial_arts',
    'EPL': 'soccer_epl'
}

# NBA Team city coordinates for travel distance calculations
NBA_TEAM_COORDS = {
    'Atlanta Hawks': (33.7490, -84.3880),
    'Boston Celtics': (42.3601, -71.0589),
    'Brooklyn Nets': (40.6782, -73.9442),
    'Charlotte Hornets': (35.2271, -80.8431),
    'Chicago Bulls': (41.8781, -87.6298),
    'Cleveland Cavaliers': (41.4993, -81.6944),
    'Dallas Mavericks': (32.7767, -96.7970),
    'Denver Nuggets': (39.7392, -104.9903),
    'Detroit Pistons': (42.3314, -83.0458),
    'Golden State Warriors': (37.7749, -122.4194),
    'Houston Rockets': (29.7604, -95.3698),
    'Indiana Pacers': (39.7684, -86.1581),
    'LA Clippers': (34.0522, -118.2437),
    'Los Angeles Lakers': (34.0522, -118.2437),
    'Memphis Grizzlies': (35.1495, -90.0490),
    'Miami Heat': (25.7617, -80.1918),
    'Milwaukee Bucks': (43.0389, -87.9065),
    'Minnesota Timberwolves': (44.9778, -93.2650),
    'New Orleans Pelicans': (29.9511, -90.0715),
    'New York Knicks': (40.7128, -74.0060),
    'Oklahoma City Thunder': (35.4676, -97.5164),
    'Orlando Magic': (28.5383, -81.3792),
    'Philadelphia 76ers': (39.9526, -75.1652),
    'Phoenix Suns': (33.4484, -112.0740),
    'Portland Trail Blazers': (45.5152, -122.6784),
    'Sacramento Kings': (38.5816, -121.4944),
    'San Antonio Spurs': (29.4241, -98.4936),
    'Toronto Raptors': (43.6532, -79.3832),
    'Utah Jazz': (40.7608, -111.8910),
    'Washington Wizards': (38.9072, -77.0369)
}

# Timezone mappings
TEAM_TIMEZONES = {
    'Eastern': ['Atlanta Hawks', 'Boston Celtics', 'Brooklyn Nets', 'Charlotte Hornets',
                'Cleveland Cavaliers', 'Detroit Pistons', 'Indiana Pacers', 'Miami Heat',
                'Milwaukee Bucks', 'New York Knicks', 'Orlando Magic', 'Philadelphia 76ers',
                'Toronto Raptors', 'Washington Wizards'],
    'Central': ['Chicago Bulls', 'Dallas Mavericks', 'Houston Rockets', 'Memphis Grizzlies',
                'Minnesota Timberwolves', 'New Orleans Pelicans', 'Oklahoma City Thunder',
                'San Antonio Spurs'],
    'Mountain': ['Denver Nuggets', 'Utah Jazz'],
    'Pacific': ['Golden State Warriors', 'LA Clippers', 'Los Angeles Lakers', 'Phoenix Suns',
                'Portland Trail Blazers', 'Sacramento Kings']
}

# Analysis weights for scoring
ANALYSIS_WEIGHTS = {
    'record': 0.15,
    'home_away': 0.12,
    'last_10': 0.10,
    'rest_days': 0.08,
    'head_to_head': 0.12,
    'offensive_rating': 0.10,
    'defensive_rating': 0.10,
    'injuries': 0.15,
    'travel_fatigue': 0.05,
    'back_to_back': 0.03
}

# Parlay configuration
PARLAY_CONFIG = {
    'min_legs': 2,
    'max_legs': 7,
    'total_parlays': 10,
    'min_confidence': 55,
    'max_confidence': 85
}

# Rate limiting (seconds between API calls)
API_DELAYS = {
    'nba_api': 1.5,  # Conservative rate limiting
    'odds_api': 0.5,
    'balldontlie': 0.5
}

# High-altitude venues (affects total points)
HIGH_ALTITUDE_VENUES = ['Denver Nuggets']

# Default odds format
DEFAULT_ODDS = "-110"

# Logging format
LOG_FORMAT = "[%(asctime)s] %(levelname)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"