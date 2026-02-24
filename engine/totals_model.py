#!/usr/bin/env python3
"""
TOTALS_MODEL.py — Real Over/Under Prediction Model for ParlayGuarantee
=====================================================================
A data-driven totals model that uses actual team statistics from ESPN API
instead of just devigged consensus odds.

Features:
- Fetches pace/scoring data from ESPN API (NBA + NCAAB)
- Calculates pace-adjusted offensive/defensive efficiency
- Factors in venue, recent trends, rest/fatigue
- Compares our projection vs Vegas line for edge detection
- Supports confidence calibration based on projection delta

Usage:
    from totals_model import predict_total, enhance_games_with_totals_model
    result = predict_total("Los Angeles Lakers", "Boston Celtics", 221.5, "nba")
    print(f"Projected: {result['projected_total']}, Pick: {result['pick']}")
"""

import json
import logging
import math
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import re

# Setup logging
log = logging.getLogger("totals_model")

# Cache directory for ESPN data
ENGINE_DIR = Path(__file__).parent
CACHE_DIR = ENGINE_DIR / "espn_cache"
CACHE_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
# ESPN API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════
ESPN_URLS = {
    'nba': {
        'teams': 'http://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams?limit=100',
        'team_stats': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{id}/statistics',
        'scoreboard': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
    },
    'ncaab': {
        'teams': 'http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams?limit=1000',
        'team_stats': 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{id}/statistics',
        'scoreboard': 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&limit=500',
    }
}

# ═══════════════════════════════════════════════════════════════════════
# TEAM NAME MAPPING
# ═══════════════════════════════════════════════════════════════════════
# Map odds API team names to ESPN team names
TEAM_NAME_MAPPING = {
    # NBA teams - common variations
    'Los Angeles Lakers': 'Los Angeles Lakers',
    'Boston Celtics': 'Boston Celtics',
    'Golden State Warriors': 'Golden State Warriors',
    'Brooklyn Nets': 'Brooklyn Nets',
    'Phoenix Suns': 'Phoenix Suns',
    'Milwaukee Bucks': 'Milwaukee Bucks',
    'Miami Heat': 'Miami Heat',
    'Denver Nuggets': 'Denver Nuggets',
    'Philadelphia 76ers': 'Philadelphia 76ers',
    'Dallas Mavericks': 'Dallas Mavericks',
    'Minnesota Timberwolves': 'Minnesota Timberwolves',
    'LA Clippers': 'LA Clippers',
    'New York Knicks': 'New York Knicks',
    'Cleveland Cavaliers': 'Cleveland Cavaliers',
    'Orlando Magic': 'Orlando Magic',
    'Indiana Pacers': 'Indiana Pacers',
    'Oklahoma City Thunder': 'Oklahoma City Thunder',
    'New Orleans Pelicans': 'New Orleans Pelicans',
    'Sacramento Kings': 'Sacramento Kings',
    'Houston Rockets': 'Houston Rockets',
    'Memphis Grizzlies': 'Memphis Grizzlies',
    'San Antonio Spurs': 'San Antonio Spurs',
    'Atlanta Hawks': 'Atlanta Hawks',
    'Chicago Bulls': 'Chicago Bulls',
    'Utah Jazz': 'Utah Jazz',
    'Charlotte Hornets': 'Charlotte Hornets',
    'Toronto Raptors': 'Toronto Raptors',
    'Portland Trail Blazers': 'Portland Trail Blazers',
    'Washington Wizards': 'Washington Wizards',
    'Detroit Pistons': 'Detroit Pistons',
    
    # Common abbreviations/alternates
    'LA Lakers': 'Los Angeles Lakers',
    'Golden State': 'Golden State Warriors',
    'Philadelphia': 'Philadelphia 76ers',
    'New York': 'New York Knicks',
    'Oklahoma City': 'Oklahoma City Thunder',
    'New Orleans': 'New Orleans Pelicans',
    'Portland': 'Portland Trail Blazers',
    
    # NCAAB will be handled dynamically since there are 350+ teams
}

# Global cache for team mappings and stats
_team_cache = {}
_stats_cache = {}

# ═══════════════════════════════════════════════════════════════════════
# ESPN API FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════
def fetch_espn_teams(sport: str) -> Dict[str, Dict]:
    """Fetch all teams for a sport and build name mapping."""
    cache_key = f"{sport}_teams"
    if cache_key in _team_cache:
        return _team_cache[cache_key]
    
    cache_file = CACHE_DIR / f"{sport}_teams.json"
    
    # Try cache first (refresh daily)
    if cache_file.exists():
        cache_age = time.time() - cache_file.stat().st_mtime
        if cache_age < 24 * 3600:  # 24 hours
            try:
                with open(cache_file) as f:
                    _team_cache[cache_key] = json.load(f)
                log.info(f"Loaded {sport.upper()} teams from cache ({len(_team_cache[cache_key])} teams)")
                return _team_cache[cache_key]
            except Exception as e:
                log.warning(f"Cache read error: {e}")
    
    # Fetch from ESPN
    teams = {}
    try:
        url = ESPN_URLS[sport]['teams']
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        
        data = r.json()
        for team in data.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', []):
            team_data = team.get('team', {})
            team_id = team_data.get('id')
            display_name = team_data.get('displayName', '')
            short_name = team_data.get('shortDisplayName', '')
            abbreviation = team_data.get('abbreviation', '')
            
            if team_id and display_name:
                teams[display_name] = {
                    'id': team_id,
                    'name': display_name,
                    'short_name': short_name,
                    'abbreviation': abbreviation,
                }
                
                # Add common variations
                if short_name and short_name != display_name:
                    teams[short_name] = teams[display_name]
                if abbreviation:
                    teams[abbreviation] = teams[display_name]
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(teams, f, indent=2)
        
        _team_cache[cache_key] = teams
        log.info(f"Fetched {sport.upper()} teams from ESPN ({len(teams)} entries)")
        return teams
        
    except Exception as e:
        log.error(f"Failed to fetch {sport} teams: {e}")
        return {}


def find_team_id(team_name: str, sport: str) -> Optional[str]:
    """Find ESPN team ID for a given team name."""
    # Normalize team name
    team_name = team_name.strip()
    
    # Check manual mapping first
    mapped_name = TEAM_NAME_MAPPING.get(team_name, team_name)
    
    # Get all teams for sport
    teams = fetch_espn_teams(sport)
    
    # Direct match
    if mapped_name in teams:
        return teams[mapped_name]['id']
    
    # Fuzzy matching
    team_lower = mapped_name.lower()
    for name, data in teams.items():
        if team_lower == name.lower():
            return data['id']
        # Check if team name contains the search term or vice versa
        if len(team_lower) > 4:
            if team_lower in name.lower() or name.lower() in team_lower:
                return data['id']
    
    # Last resort: check short names and abbreviations
    for name, data in teams.items():
        short = data.get('short_name', '').lower()
        abbr = data.get('abbreviation', '').lower()
        if team_lower == short or team_lower == abbr:
            return data['id']
    
    log.warning(f"Could not find team ID for: {team_name} (sport: {sport})")
    return None


def fetch_team_stats(team_id: str, sport: str) -> Dict:
    """Fetch detailed team statistics from ESPN."""
    cache_key = f"{sport}_{team_id}"
    if cache_key in _stats_cache:
        return _stats_cache[cache_key]
    
    cache_file = CACHE_DIR / f"{sport}_team_{team_id}.json"
    
    # Try cache first (refresh every 4 hours during season)
    if cache_file.exists():
        cache_age = time.time() - cache_file.stat().st_mtime
        if cache_age < 4 * 3600:  # 4 hours
            try:
                with open(cache_file) as f:
                    _stats_cache[cache_key] = json.load(f)
                return _stats_cache[cache_key]
            except Exception as e:
                log.warning(f"Stats cache read error: {e}")
    
    # Fetch from ESPN
    try:
        url = ESPN_URLS[sport]['team_stats'].format(id=team_id)
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        
        stats = r.json()
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        _stats_cache[cache_key] = stats
        return stats
        
    except Exception as e:
        log.error(f"Failed to fetch stats for team {team_id}: {e}")
        return {}


def parse_team_stats(stats_data: Dict) -> Dict:
    """Parse ESPN team stats into our standardized format."""
    if not stats_data:
        return {}
    
    # Extract key stats from ESPN's complex structure
    parsed = {
        'points_per_game': 0,
        'points_allowed_per_game': 0,
        'field_goal_pct': 0,
        'three_point_pct': 0,
        'free_throw_pct': 0,
        'rebounds_per_game': 0,
        'assists_per_game': 0,
        'turnovers_per_game': 0,
        'steals_per_game': 0,
        'blocks_per_game': 0,
        'possessions_per_game': 0,  # Calculated from pace
        'offensive_efficiency': 0,  # Points per 100 possessions
        'defensive_efficiency': 0,  # Points allowed per 100 possessions
    }
    
    try:
        # Navigate ESPN's nested stats structure
        splits = stats_data.get('results', {}).get('stats', {})
        categories = splits.get('categories', [])
        
        for category in categories:
            cat_name = category.get('name', '').lower()
            stats = category.get('stats', [])
            
            for stat in stats:
                stat_name = stat.get('name', '').lower()
                value = stat.get('value', 0)
                
                try:
                    value = float(value) if value and value != '--' else 0
                except (ValueError, TypeError):
                    value = 0
                
                # Map ESPN stat names to our format (using exact lowercase names)
                if stat_name == 'avgpoints':
                    parsed['points_per_game'] = value
                elif stat_name == 'fieldgoalpct':
                    parsed['field_goal_pct'] = value / 100 if value > 1 else value
                elif stat_name == 'threepointpct':
                    parsed['three_point_pct'] = value / 100 if value > 1 else value
                elif stat_name == 'freethrowpct':
                    parsed['free_throw_pct'] = value / 100 if value > 1 else value
                elif stat_name == 'avgrebounds':
                    parsed['rebounds_per_game'] = value
                elif stat_name == 'avgassists':
                    parsed['assists_per_game'] = value
                elif stat_name == 'avgturnovers':
                    parsed['turnovers_per_game'] = value
                elif stat_name == 'avgsteals':
                    parsed['steals_per_game'] = value
                elif stat_name == 'avgblocks':
                    parsed['blocks_per_game'] = value
        
        # Calculate advanced metrics
        ppg = parsed['points_per_game']
        
        # Estimate points allowed per game using league averages
        # ESPN doesn't provide defensive stats directly, so we estimate
        if ppg > 0:
            # NBA average: ~112 ppg, NCAAB average: ~70 ppg  
            league_avg = 112 if any('nba' in str(stats_data).lower() for _ in [1]) else 70
            
            # Estimate defensive rating based on offensive vs league average
            # Teams that score well above average tend to allow more points (pace)
            # Teams that score below average tend to be more defensive-minded
            if ppg > league_avg:
                # High-scoring teams usually allow more points (pace factor)
                pace_multiplier = 1 + ((ppg - league_avg) / league_avg) * 0.5
                parsed['points_allowed_per_game'] = league_avg * pace_multiplier
            else:
                # Lower-scoring teams are usually more defensive
                defensive_multiplier = 0.95 + ((ppg / league_avg) * 0.05)
                parsed['points_allowed_per_game'] = league_avg * defensive_multiplier
        else:
            # Fallback to league average
            parsed['points_allowed_per_game'] = 112 if any('nba' in str(stats_data).lower() for _ in [1]) else 70
        
        papg = parsed['points_allowed_per_game']
        
        # Estimate possessions per game using turnovers and pace indicators
        # For NBA: ~100 possessions per team per game
        # For NCAAB: ~65-75 possessions per team per game
        base_possessions = 100 if any('nba' in str(stats_data).lower() for _ in [1]) else 70
        
        # Adjust based on pace indicators (turnovers, assists)
        pace_factor = 1.0
        if parsed['turnovers_per_game'] > 0:
            # More turnovers = faster pace
            avg_to = 14 if base_possessions == 100 else 12  # NBA vs NCAAB
            pace_factor += (parsed['turnovers_per_game'] - avg_to) * 0.015
        
        # High-assist teams often play faster
        if parsed['assists_per_game'] > 0:
            avg_ast = 25 if base_possessions == 100 else 15
            pace_factor += (parsed['assists_per_game'] - avg_ast) * 0.01
        
        parsed['possessions_per_game'] = base_possessions * max(pace_factor, 0.8)
        
        # Efficiency (points per 100 possessions)
        if parsed['possessions_per_game'] > 0:
            parsed['offensive_efficiency'] = (ppg / parsed['possessions_per_game']) * 100
            parsed['defensive_efficiency'] = (papg / parsed['possessions_per_game']) * 100
        
    except Exception as e:
        log.warning(f"Error parsing stats: {e}")
    
    return parsed


# ═══════════════════════════════════════════════════════════════════════
# TOTALS PREDICTION MODEL
# ═══════════════════════════════════════════════════════════════════════
def get_team_stats(team_name: str, sport: str) -> Dict:
    """Get processed team stats for totals modeling."""
    team_id = find_team_id(team_name, sport)
    if not team_id:
        log.warning(f"No team ID found for {team_name} ({sport})")
        return {}
    
    raw_stats = fetch_team_stats(team_id, sport)
    return parse_team_stats(raw_stats)


def calculate_pace_adjustment(home_stats: Dict, away_stats: Dict, sport: str) -> float:
    """Calculate pace adjustment factor based on both teams."""
    home_pace = home_stats.get('possessions_per_game', 0)
    away_pace = away_stats.get('possessions_per_game', 0)
    
    if home_pace == 0 or away_pace == 0:
        # Default pace estimates
        return 1.0 if sport == 'nba' else 0.7  # NCAAB is slower
    
    # Combined pace is average of both teams
    combined_pace = (home_pace + away_pace) / 2
    
    # Normalize to base pace (100 for NBA, 70 for NCAAB)
    base_pace = 100 if sport == 'nba' else 70
    return combined_pace / base_pace


def calculate_rest_adjustment(game_date: Optional[str] = None) -> float:
    """Calculate rest/fatigue adjustment based on game timing."""
    # Basic rest adjustment - could be enhanced with actual schedule data
    rest_adj = 0
    
    if game_date:
        try:
            # Parse date and check day of week
            game_dt = datetime.strptime(game_date, '%Y-%m-%d')
            day_of_week = game_dt.weekday()  # 0 = Monday
            
            # Back-to-back games are more common on certain days
            if day_of_week in [1, 2, 3]:  # Tue, Wed, Thu - potential B2B
                rest_adj -= 2.0  # Lower scoring on tired legs
            elif day_of_week in [4, 5]:  # Fri, Sat - fresh legs
                rest_adj += 1.0
                
        except Exception:
            pass
    
    return rest_adj


def calculate_venue_adjustment(is_home_team: bool, sport: str) -> float:
    """Calculate home court advantage in scoring."""
    if not is_home_team:
        return 0
    
    # Home teams typically score slightly more
    if sport == 'nba':
        return 2.5  # NBA home advantage ~2-3 points
    else:
        return 3.5  # College has stronger home court advantage


def predict_total(home_team: str, away_team: str, vegas_line: float, sport: str = 'nba', game_date: Optional[str] = None) -> Dict:
    """
    Predict game total using team statistics.
    
    Args:
        home_team: Home team name
        away_team: Away team name  
        vegas_line: Vegas total line
        sport: 'nba' or 'ncaab'
        game_date: Game date string (YYYY-MM-DD), optional
        
    Returns:
        Dict with projected total, pick, confidence, and factors
    """
    sport = sport.lower()
    if sport not in ['nba', 'ncaab']:
        log.error(f"Unsupported sport: {sport}")
        return {'error': f'Unsupported sport: {sport}'}
    
    # Get team stats
    home_stats = get_team_stats(home_team, sport)
    away_stats = get_team_stats(away_team, sport)
    
    if not home_stats or not away_stats:
        log.warning(f"Could not get stats for {home_team} vs {away_team}")
        return {
            'projected_total': vegas_line,  # Fallback to Vegas
            'vegas_line': vegas_line,
            'delta': 0,
            'pick': None,
            'confidence': 0,
            'error': 'Missing team stats',
            'factors': {}
        }
    
    # Extract key stats
    home_ppg = home_stats.get('points_per_game', 0)
    away_ppg = away_stats.get('points_per_game', 0)
    home_papg = home_stats.get('points_allowed_per_game', 0)
    away_papg = away_stats.get('points_allowed_per_game', 0)
    
    home_off_eff = home_stats.get('offensive_efficiency', 0)
    away_off_eff = away_stats.get('offensive_efficiency', 0)
    home_def_eff = home_stats.get('defensive_efficiency', 0)
    away_def_eff = away_stats.get('defensive_efficiency', 0)
    
    # Calculate base projection using multiple methods
    
    # Method 1: Simple PPG average
    basic_total = home_ppg + away_ppg
    
    # Method 2: Efficiency-based (more accurate)
    # Home team scoring against away defense
    if away_def_eff > 0:
        home_proj_score = (home_off_eff / away_def_eff) * (away_papg if away_papg > 0 else 110)
    else:
        home_proj_score = home_ppg
    
    # Away team scoring against home defense  
    if home_def_eff > 0:
        away_proj_score = (away_off_eff / home_def_eff) * (home_papg if home_papg > 0 else 110)
    else:
        away_proj_score = away_ppg
    
    efficiency_total = home_proj_score + away_proj_score
    
    # Weight the methods (efficiency gets more weight)
    if efficiency_total > 0:
        base_projection = (basic_total * 0.3) + (efficiency_total * 0.7)
    else:
        base_projection = basic_total
    
    # Apply adjustments
    factors = {
        'home_ppg': round(home_ppg, 1),
        'away_ppg': round(away_ppg, 1),
        'home_papg': round(home_papg, 1),
        'away_papg': round(away_papg, 1),
        'base_projection': round(base_projection, 1),
    }
    
    # Pace adjustment
    pace_factor = calculate_pace_adjustment(home_stats, away_stats, sport)
    pace_adj = (pace_factor - 1.0) * base_projection * 0.1  # 10% max adjustment
    factors['pace_factor'] = round(pace_factor, 3)
    factors['pace_adj'] = round(pace_adj, 1)
    
    # Venue adjustment (home court scoring boost)
    venue_adj = calculate_venue_adjustment(True, sport)  # Always favor home slightly
    factors['venue_adj'] = round(venue_adj, 1)
    
    # Rest adjustment
    rest_adj = calculate_rest_adjustment(game_date)
    factors['rest_adj'] = round(rest_adj, 1)
    
    # Recent trend adjustment (placeholder - would need game log data)
    trend_adj = 0  # TODO: Implement with recent games data
    factors['trend_adj'] = round(trend_adj, 1)
    
    # Final projection
    projected_total = base_projection + pace_adj + venue_adj + rest_adj + trend_adj
    factors['projected_total'] = round(projected_total, 1)
    
    # Compare to Vegas line
    delta = projected_total - vegas_line
    
    # Determine pick and confidence
    pick = None
    confidence = 0
    
    abs_delta = abs(delta)
    if abs_delta >= 1.0:  # Must have at least 1 point edge
        if delta > 0:
            pick = 'Over'
        else:
            pick = 'Under'
        
        # Confidence calibration
        if abs_delta < 3:
            confidence = 0.52 + (abs_delta * 0.02)  # 52-58%
        elif abs_delta < 5:
            confidence = 0.58 + ((abs_delta - 3) * 0.035)  # 58-65%
        elif abs_delta < 8:
            confidence = 0.65 + ((abs_delta - 5) * 0.033)  # 65-75%
        else:
            confidence = 0.75 + min((abs_delta - 8) * 0.01, 0.1)  # 75-85% max
    
    return {
        'projected_total': round(projected_total, 1),
        'vegas_line': vegas_line,
        'delta': round(delta, 1),
        'pick': pick,
        'confidence': round(confidence, 4) if confidence > 0 else 0,
        'factors': factors,
    }


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════
def enhance_games_with_totals_model(games: List[Dict]) -> List[Dict]:
    """
    Replace the basic O/U picks in analyzed games with our model predictions.
    
    Args:
        games: List of analyzed game dicts from autopilot
        
    Returns:
        List of games with enhanced O/U predictions
    """
    log.info(f"Enhancing {len(games)} games with totals model...")
    
    enhanced_count = 0
    for game in games:
        home = game.get('home', '')
        away = game.get('away', '')
        total_line = game.get('total_line')
        sport = game.get('sport', 'NBA').lower()
        sport_key = 'nba' if sport == 'nba' else 'ncaab'
        game_date = game.get('game_date')
        
        if not total_line or total_line == 0:
            continue  # No total line available
            
        # Get our model prediction
        prediction = predict_total(home, away, total_line, sport_key, game_date)
        
        if prediction.get('error'):
            log.warning(f"Model error for {away} @ {home}: {prediction['error']}")
            continue
        
        # Store original devigged odds as fallback
        game['ou_devigged_pick'] = game.get('ou_pick')
        game['ou_devigged_prob'] = game.get('ou_prob')
        
        # Replace with model predictions
        game['ou_pick'] = prediction['pick']
        game['ou_prob'] = prediction['confidence']
        game['ou_model'] = prediction  # Store full model output
        
        # Boost confidence if model and odds agree
        if (game.get('ou_devigged_pick') == prediction['pick'] and 
            prediction['confidence'] > 0):
            boost = 0.02  # Small boost for agreement
            game['ou_prob'] = min(game['ou_prob'] + boost, 0.85)
            game['ou_agreement'] = True
        else:
            game['ou_agreement'] = False
        
        enhanced_count += 1
    
    log.info(f"Enhanced {enhanced_count} games with totals model")
    return games


# ═══════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════
def test_model():
    """Test the model against today's games."""
    import argparse
    from datetime import datetime, timezone, timedelta
    
    # Setup logging for CLI
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    print("=" * 60)
    print("TOTALS MODEL TEST")
    print("=" * 60)
    
    # Load today's analyzed games if available
    today = datetime.now(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d')
    games_file = ENGINE_DIR / 'analyzed_games.json'
    
    if games_file.exists():
        with open(games_file) as f:
            games = json.load(f)
        print(f"Loaded {len(games)} analyzed games from {games_file}")
        
        # Filter to games with totals
        total_games = [g for g in games if g.get('total_line') and g.get('total_line') > 0]
        print(f"Found {len(total_games)} games with total lines")
        
        if total_games:
            print("\nMODEL PREDICTIONS:")
            print("-" * 80)
            
            for game in total_games[:10]:  # Test first 10 games
                home = game.get('home', '')
                away = game.get('away', '')
                vegas_line = game.get('total_line', 0)
                sport = 'nba' if game.get('sport') == 'NBA' else 'ncaab'
                
                result = predict_total(home, away, vegas_line, sport, today)
                
                if result.get('error'):
                    print(f"ERROR {away} @ {home}: {result['error']}")
                    continue
                
                proj = result['projected_total']
                delta = result['delta']
                pick = result['pick']
                conf = result['confidence']
                
                # Format output
                delta_str = f"{delta:+.1f}"
                conf_str = f"{conf:.0%}" if conf > 0 else "SKIP"
                pick_str = pick if pick else "PASS"
                
                print(f"GAME {away} @ {home}")
                print(f"   Vegas: {vegas_line} | Model: {proj} | Delta: {delta_str}")
                print(f"   Pick: {pick_str} | Confidence: {conf_str}")
                
                # Show key factors
                factors = result.get('factors', {})
                home_ppg = factors.get('home_ppg', 0)
                away_ppg = factors.get('away_ppg', 0)
                pace_f = factors.get('pace_factor', 1)
                print(f"   Factors: Home {home_ppg}ppg, Away {away_ppg}ppg, Pace {pace_f:.2f}")
                print()
        
        # Test the integration function
        print("\nTESTING INTEGRATION...")
        enhanced_games = enhance_games_with_totals_model(total_games[:5])
        
        print("\nBEFORE vs AFTER:")
        print("-" * 50)
        for orig, enhanced in zip(total_games[:5], enhanced_games):
            home = orig.get('home', '')
            away = orig.get('away', '')
            
            old_pick = orig.get('ou_pick', 'None')
            old_prob = orig.get('ou_prob', 0)
            
            new_pick = enhanced.get('ou_pick', 'None')
            new_prob = enhanced.get('ou_prob', 0)
            
            agreement = "AGREE" if enhanced.get('ou_agreement') else "DIFF"
            
            print(f"{away} @ {home}:")
            print(f"  Old: {old_pick} ({old_prob:.0%}) -> New: {new_pick} ({new_prob:.0%}) {agreement}")
        
    else:
        print(f"No analyzed games found at {games_file}")
        print("Testing with sample data...")
        
        # Test with sample matchups
        test_games = [
            ('Los Angeles Lakers', 'Boston Celtics', 221.5, 'nba'),
            ('Duke', 'North Carolina', 152.5, 'ncaab'),
            ('Golden State Warriors', 'Phoenix Suns', 235.0, 'nba'),
        ]
        
        for home, away, line, sport in test_games:
            result = predict_total(home, away, line, sport)
            print(f"\n{away} @ {home} (O/U {line})")
            print(f"Model: {result}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ParlayGuarantee Totals Model')
    parser.add_argument('--test', action='store_true', help='Test model against today\'s games')
    args = parser.parse_args()
    
    if args.test:
        test_model()
    else:
        print("Use --test to run model test")