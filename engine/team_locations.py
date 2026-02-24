"""
NBA Team Locations - Latitude/Longitude and Timezone data for travel calculations
Used by Engine v2 for travel distance and timezone change factors
"""

from datetime import datetime
from typing import Dict, Tuple
import math

# NBA Team coordinates (lat, lng) and timezone
NBA_TEAM_LOCATIONS = {
    # Eastern Conference - Atlantic
    "Boston Celtics": {"lat": 42.3662, "lng": -71.0621, "tz": "America/New_York"},
    "Brooklyn Nets": {"lat": 40.6826, "lng": -73.9754, "tz": "America/New_York"},
    "New York Knicks": {"lat": 40.7505, "lng": -73.9934, "tz": "America/New_York"},
    "Philadelphia 76ers": {"lat": 39.9012, "lng": -75.1720, "tz": "America/New_York"},
    "Toronto Raptors": {"lat": 43.6434, "lng": -79.3790, "tz": "America/Toronto"},
    
    # Eastern Conference - Central
    "Chicago Bulls": {"lat": 41.8807, "lng": -87.6742, "tz": "America/Chicago"},
    "Cleveland Cavaliers": {"lat": 41.4965, "lng": -81.6882, "tz": "America/New_York"},
    "Detroit Pistons": {"lat": 42.3412, "lng": -83.0555, "tz": "America/New_York"},
    "Indiana Pacers": {"lat": 39.7640, "lng": -86.1555, "tz": "America/New_York"},
    "Milwaukee Bucks": {"lat": 43.0435, "lng": -87.9170, "tz": "America/Chicago"},
    
    # Eastern Conference - Southeast  
    "Atlanta Hawks": {"lat": 33.7573, "lng": -84.3963, "tz": "America/New_York"},
    "Charlotte Hornets": {"lat": 35.2251, "lng": -80.8392, "tz": "America/New_York"},
    "Miami Heat": {"lat": 25.7814, "lng": -80.1870, "tz": "America/New_York"},
    "Orlando Magic": {"lat": 28.5392, "lng": -81.3839, "tz": "America/New_York"},
    "Washington Wizards": {"lat": 38.8981, "lng": -77.0209, "tz": "America/New_York"},
    
    # Western Conference - Northwest
    "Denver Nuggets": {"lat": 39.7487, "lng": -105.0077, "tz": "America/Denver"},
    "Minnesota Timberwolves": {"lat": 44.9795, "lng": -93.2760, "tz": "America/Chicago"},
    "Oklahoma City Thunder": {"lat": 35.4634, "lng": -97.5151, "tz": "America/Chicago"},
    "Portland Trail Blazers": {"lat": 45.5316, "lng": -122.6668, "tz": "America/Los_Angeles"},
    "Utah Jazz": {"lat": 40.7683, "lng": -111.9011, "tz": "America/Denver"},
    
    # Western Conference - Pacific
    "Golden State Warriors": {"lat": 37.7680, "lng": -122.3877, "tz": "America/Los_Angeles"},
    "LA Clippers": {"lat": 34.0430, "lng": -118.2673, "tz": "America/Los_Angeles"},
    "Los Angeles Lakers": {"lat": 34.0430, "lng": -118.2673, "tz": "America/Los_Angeles"},
    "Phoenix Suns": {"lat": 33.4457, "lng": -112.0712, "tz": "America/Phoenix"},
    "Sacramento Kings": {"lat": 38.6491, "lng": -121.5177, "tz": "America/Los_Angeles"},
    
    # Western Conference - Southwest
    "Dallas Mavericks": {"lat": 32.7905, "lng": -96.8103, "tz": "America/Chicago"},
    "Houston Rockets": {"lat": 29.6820, "lng": -95.4110, "tz": "America/Chicago"},
    "Memphis Grizzlies": {"lat": 35.1381, "lng": -90.0505, "tz": "America/Chicago"},
    "New Orleans Pelicans": {"lat": 29.9490, "lng": -90.0821, "tz": "America/Chicago"},
    "San Antonio Spurs": {"lat": 29.4270, "lng": -98.4375, "tz": "America/Chicago"},
}

# Division mappings for rivalry detection
NBA_DIVISIONS = {
    "Atlantic": ["Boston Celtics", "Brooklyn Nets", "New York Knicks", "Philadelphia 76ers", "Toronto Raptors"],
    "Central": ["Chicago Bulls", "Cleveland Cavaliers", "Detroit Pistons", "Indiana Pacers", "Milwaukee Bucks"],
    "Southeast": ["Atlanta Hawks", "Charlotte Hornets", "Miami Heat", "Orlando Magic", "Washington Wizards"],
    "Northwest": ["Denver Nuggets", "Minnesota Timberwolves", "Oklahoma City Thunder", "Portland Trail Blazers", "Utah Jazz"],
    "Pacific": ["Golden State Warriors", "LA Clippers", "Los Angeles Lakers", "Phoenix Suns", "Sacramento Kings"],
    "Southwest": ["Dallas Mavericks", "Houston Rockets", "Memphis Grizzlies", "New Orleans Pelicans", "San Antonio Spurs"]
}

# Conference mappings
NBA_CONFERENCES = {
    "Eastern": ["Boston Celtics", "Brooklyn Nets", "New York Knicks", "Philadelphia 76ers", "Toronto Raptors",
                "Chicago Bulls", "Cleveland Cavaliers", "Detroit Pistons", "Indiana Pacers", "Milwaukee Bucks",
                "Atlanta Hawks", "Charlotte Hornets", "Miami Heat", "Orlando Magic", "Washington Wizards"],
    "Western": ["Denver Nuggets", "Minnesota Timberwolves", "Oklahoma City Thunder", "Portland Trail Blazers", "Utah Jazz",
                "Golden State Warriors", "LA Clippers", "Los Angeles Lakers", "Phoenix Suns", "Sacramento Kings",
                "Dallas Mavericks", "Houston Rockets", "Memphis Grizzlies", "New Orleans Pelicans", "San Antonio Spurs"]
}


def calculate_distance(team1: str, team2: str) -> float:
    """
    Calculate distance between two NBA team cities using Haversine formula
    Returns distance in miles
    """
    if team1 not in NBA_TEAM_LOCATIONS or team2 not in NBA_TEAM_LOCATIONS:
        return 0.0
    
    loc1 = NBA_TEAM_LOCATIONS[team1]
    loc2 = NBA_TEAM_LOCATIONS[team2]
    
    # Haversine formula
    lat1, lng1 = math.radians(loc1["lat"]), math.radians(loc1["lng"])
    lat2, lng2 = math.radians(loc2["lat"]), math.radians(loc2["lng"])
    
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth radius in miles
    r = 3956
    
    return c * r


def get_timezone_difference(team1: str, team2: str) -> int:
    """
    Get timezone difference between two teams (in hours)
    Positive = team2 is ahead of team1
    """
    if team1 not in NBA_TEAM_LOCATIONS or team2 not in NBA_TEAM_LOCATIONS:
        return 0
    
    tz1 = NBA_TEAM_LOCATIONS[team1]["tz"]
    tz2 = NBA_TEAM_LOCATIONS[team2]["tz"]
    
    # Simplified timezone mapping (not handling DST changes)
    tz_hours = {
        "America/Los_Angeles": -8,  # PST
        "America/Phoenix": -7,      # MST (no DST)  
        "America/Denver": -7,       # MST
        "America/Chicago": -6,      # CST
        "America/New_York": -5,     # EST
        "America/Toronto": -5       # EST
    }
    
    hour1 = tz_hours.get(tz1, -5)
    hour2 = tz_hours.get(tz2, -5)
    
    return hour2 - hour1


def is_division_rival(team1: str, team2: str) -> bool:
    """Check if two teams are in the same division"""
    for division, teams in NBA_DIVISIONS.items():
        if team1 in teams and team2 in teams:
            return True
    return False


def is_conference_game(team1: str, team2: str) -> bool:
    """Check if two teams are in the same conference"""
    for conference, teams in NBA_CONFERENCES.items():
        if team1 in teams and team2 in teams:
            return True
    return False


def get_team_division(team: str) -> str:
    """Get division for a team"""
    for division, teams in NBA_DIVISIONS.items():
        if team in teams:
            return division
    return "Unknown"


def get_team_conference(team: str) -> str:
    """Get conference for a team"""
    for conference, teams in NBA_CONFERENCES.items():
        if team in teams:
            return conference
    return "Unknown"


if __name__ == "__main__":
    # Test the functions
    print("Testing team location functions:")
    print(f"Distance LAL to BOS: {calculate_distance('Los Angeles Lakers', 'Boston Celtics'):.1f} miles")
    print(f"Timezone diff LAL to BOS: {get_timezone_difference('Los Angeles Lakers', 'Boston Celtics')} hours")
    print(f"LAL vs BOS division rivals: {is_division_rival('Los Angeles Lakers', 'Boston Celtics')}")
    print(f"LAL vs BOS conference game: {is_conference_game('Los Angeles Lakers', 'Boston Celtics')}")
    print(f"LAL vs LAC division rivals: {is_division_rival('Los Angeles Lakers', 'LA Clippers')}")
    print(f"LAL division: {get_team_division('Los Angeles Lakers')}")
    print(f"BOS conference: {get_team_conference('Boston Celtics')}")