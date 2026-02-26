#!/usr/bin/env python3
"""
NBA Advanced Stats Module — Data scrapers for Alpha V3 engine
==============================================================
Consolidates all 15 new data sources into one module with caching.
Each function returns data dicts; the V3 engine normalizes to 0-1 edge scores.

Graceful degradation: if any scraper fails, returns empty/default data.
"""

import json, logging, math, os, re, time, hashlib
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
CACHE_DIR = ENGINE_DIR / "data" / "alpha_v3_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

EST = timezone(timedelta(hours=-5))
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# ─── Cache Helpers ──────────────────────────────────────────────────
def _cache_path(key: str) -> Path:
    safe = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{safe}.json"

def _cache_get(key: str, max_age_hours: float = 6) -> Optional[dict]:
    p = _cache_path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        ts = data.get('_ts', 0)
        if time.time() - ts > max_age_hours * 3600:
            return None
        return data.get('payload')
    except Exception:
        return None

def _cache_set(key: str, payload):
    try:
        _cache_path(key).write_text(
            json.dumps({'_ts': time.time(), 'payload': payload}, default=str),
            encoding='utf-8'
        )
    except Exception as e:
        logger.debug(f"Cache write failed: {e}")

def _get(url: str, params=None, timeout=15) -> Optional[requests.Response]:
    if not HAS_REQUESTS:
        return None
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        logger.warning(f"HTTP GET failed {url}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
# 1. NET RATING / OFFENSIVE + DEFENSIVE EFFICIENCY
# ═══════════════════════════════════════════════════════════════════════
def fetch_team_ratings() -> Dict[str, Dict]:
    """
    Fetch ORtg, DRtg, NetRtg from NBA.com stats API or ESPN.
    Returns {team_name: {ortg, drtg, net_rtg, pace}}
    """
    cached = _cache_get('team_ratings', max_age_hours=24)
    if cached:
        return cached

    result = {}

    # Try NBA.com stats API (public JSON endpoint)
    try:
        url = "https://stats.nba.com/stats/leaguedashteamstats"
        params = {
            'Conference': '', 'DateFrom': '', 'DateTo': '',
            'Division': '', 'GameScope': '', 'GameSegment': '',
            'Height': '', 'ISTRound': '', 'LastNGames': '0',
            'LeagueID': '00', 'Location': '', 'MeasureType': 'Advanced',
            'Month': '0', 'OpponentTeamID': '0', 'Outcome': '',
            'PORound': '0', 'PaceAdjust': 'N', 'PerMode': 'PerGame',
            'Period': '0', 'PlayerExperience': '', 'PlayerPosition': '',
            'PlusMinus': 'N', 'Rank': 'N', 'Season': _current_season(),
            'SeasonSegment': '', 'SeasonType': 'Regular Season',
            'ShotClockRange': '', 'StarterBench': '', 'TeamID': '0',
            'TwoWay': '0', 'VsConference': '', 'VsDivision': '',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            headers_list = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx = {h: i for i, h in enumerate(headers_list)}
            for row in rows:
                name = row[idx.get('TEAM_NAME', 1)]
                result[name] = {
                    'ortg': row[idx.get('OFF_RATING', 0)] if 'OFF_RATING' in idx else 0,
                    'drtg': row[idx.get('DEF_RATING', 0)] if 'DEF_RATING' in idx else 0,
                    'net_rtg': row[idx.get('NET_RATING', 0)] if 'NET_RATING' in idx else 0,
                    'pace': row[idx.get('PACE', 0)] if 'PACE' in idx else 100,
                }
            if result:
                _cache_set('team_ratings', result)
                logger.info(f"Fetched team ratings for {len(result)} teams from NBA.com")
                return result
    except Exception as e:
        logger.warning(f"NBA.com stats API failed: {e}")

    # Fallback: ESPN team stats page
    try:
        url = "https://www.espn.com/nba/stats/team/_/table/offensive/sort/avgPoints/dir/desc"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            # ESPN doesn't expose net rating easily in HTML, try API
            pass
    except Exception as e:
        logger.warning(f"ESPN fallback failed: {e}")

    # Fallback: basketball-reference
    try:
        url = f"https://www.basketball-reference.com/leagues/NBA_{_current_year()}.html"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', id='advanced-team')
            if table:
                for row in table.find('tbody').find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 16:
                        name_cell = row.find('td', {'data-stat': 'team_name'})
                        if name_cell:
                            team = name_cell.text.strip().replace('*', '')
                            ortg_cell = row.find('td', {'data-stat': 'off_rtg'})
                            drtg_cell = row.find('td', {'data-stat': 'def_rtg'})
                            net_cell = row.find('td', {'data-stat': 'net_rtg'})
                            pace_cell = row.find('td', {'data-stat': 'pace'})
                            result[team] = {
                                'ortg': float(ortg_cell.text) if ortg_cell and ortg_cell.text else 110,
                                'drtg': float(drtg_cell.text) if drtg_cell and drtg_cell.text else 110,
                                'net_rtg': float(net_cell.text) if net_cell and net_cell.text else 0,
                                'pace': float(pace_cell.text) if pace_cell and pace_cell.text else 100,
                            }
                if result:
                    _cache_set('team_ratings', result)
                    logger.info(f"Fetched team ratings for {len(result)} teams from BBRef")
    except Exception as e:
        logger.warning(f"BBRef ratings failed: {e}")

    if result:
        _cache_set('team_ratings', result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 2. REST DAYS / BACK-TO-BACK DETECTION
# ═══════════════════════════════════════════════════════════════════════
def fetch_schedule_rest(target_date: date) -> Dict[str, Dict]:
    """
    Check NBA schedule for rest days / B2B.
    Returns {team_name: {rest_days: int, is_b2b: bool, played_yesterday: bool, games_in_5: int}}
    """
    cache_key = f"rest_{target_date.isoformat()}"
    cached = _cache_get(cache_key, max_age_hours=24)
    if cached:
        return cached

    result = {}
    # Check last 5 days of schedule via ESPN scoreboard
    for days_back in range(1, 6):
        check_date = target_date - timedelta(days=days_back)
        dt_str = check_date.strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt_str}"
        r = _get(url)
        if not r:
            continue
        try:
            events = r.json().get('events', [])
            for ev in events:
                comps = ev.get('competitions', [{}])[0]
                for c in comps.get('competitors', []):
                    team = c['team'].get('displayName', '')
                    if not team:
                        continue
                    if team not in result:
                        result[team] = {'last_game_days_ago': None, 'games_in_5': 0}
                    result[team]['games_in_5'] += 1
                    if result[team]['last_game_days_ago'] is None:
                        result[team]['last_game_days_ago'] = days_back
        except Exception as e:
            logger.warning(f"Schedule parse error for {check_date}: {e}")

    # Compute rest metrics
    for team, data in result.items():
        days_ago = data.get('last_game_days_ago')
        if days_ago is not None:
            data['rest_days'] = days_ago - 1  # 1 day ago = 0 rest days (B2B)
            data['is_b2b'] = (days_ago == 1)
            data['played_yesterday'] = (days_ago == 1)
        else:
            data['rest_days'] = 3  # unknown = assume rested
            data['is_b2b'] = False
            data['played_yesterday'] = False

    _cache_set(cache_key, result)
    logger.info(f"Rest data for {len(result)} teams on {target_date}")
    return result


# ═══════════════════════════════════════════════════════════════════════
# 3. ATS TRENDS
# ═══════════════════════════════════════════════════════════════════════
def fetch_ats_trends() -> Dict[str, Dict]:
    """
    Fetch ATS records from teamrankings.com or covers.com.
    Returns {team_name: {ats_pct, ats_home_pct, ats_away_pct, ats_l10_pct}}
    """
    cached = _cache_get('ats_trends', max_age_hours=24)
    if cached:
        return cached

    result = {}

    # Try teamrankings.com
    try:
        url = "https://www.teamrankings.com/nba/trends/ats_trends/"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', class_='tr-table')
            if table:
                rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        team = cells[0].text.strip()
                        # Parse W-L record
                        record = cells[1].text.strip()
                        w, l = _parse_record(record)
                        total = w + l
                        result[team] = {
                            'ats_pct': w / total if total > 0 else 0.5,
                            'ats_wins': w, 'ats_losses': l,
                        }
    except Exception as e:
        logger.warning(f"TeamRankings ATS failed: {e}")

    # Try covers.com as fallback
    if not result:
        try:
            url = "https://www.covers.com/sport/basketball/nba/standings"
            r = _get(url)
            if r:
                soup = BeautifulSoup(r.text, 'html.parser')
                # Parse ATS records from standings page
                tables = soup.find_all('table')
                for table in tables:
                    for row in table.find_all('tr')[1:]:
                        cells = row.find_all('td')
                        if len(cells) >= 5:
                            team = cells[0].text.strip()
                            ats_text = cells[-1].text.strip() if cells[-1].text.strip() else ''
                            w, l = _parse_record(ats_text)
                            total = w + l
                            if total > 0:
                                result[team] = {'ats_pct': w / total, 'ats_wins': w, 'ats_losses': l}
        except Exception as e:
            logger.warning(f"Covers ATS failed: {e}")

    # Also try home/away ATS
    for venue, url_suffix in [('home', 'home_ats_trends'), ('away', 'away_ats_trends')]:
        try:
            url = f"https://www.teamrankings.com/nba/trends/{url_suffix}/"
            r = _get(url)
            if r:
                soup = BeautifulSoup(r.text, 'html.parser')
                table = soup.find('table', class_='tr-table')
                if table:
                    rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            team = cells[0].text.strip()
                            record = cells[1].text.strip()
                            w, l = _parse_record(record)
                            total = w + l
                            if team in result and total > 0:
                                result[team][f'ats_{venue}_pct'] = w / total
        except Exception as e:
            logger.warning(f"TeamRankings {venue} ATS failed: {e}")

    if result:
        _cache_set('ats_trends', result)
        logger.info(f"ATS trends for {len(result)} teams")
    return result


def _parse_record(text: str) -> Tuple[int, int]:
    """Parse 'W-L' or 'W-L-P' record string. Returns (wins, losses)."""
    m = re.match(r'(\d+)\s*-\s*(\d+)', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


# ═══════════════════════════════════════════════════════════════════════
# 4. PLAYER-LEVEL ADVANCED STATS
# ═══════════════════════════════════════════════════════════════════════
def fetch_player_advanced_stats() -> Dict[str, List[Dict]]:
    """
    Fetch top player advanced stats per team.
    Returns {team_name: [{player, per, usg, plus_minus, mpg}]}
    """
    cached = _cache_get('player_advanced', max_age_hours=24)
    if cached:
        return cached

    result = {}

    # Try NBA.com player stats
    try:
        url = "https://stats.nba.com/stats/leaguedashplayerstats"
        params = {
            'College': '', 'Conference': '', 'Country': '',
            'DateFrom': '', 'DateTo': '', 'Division': '',
            'DraftPick': '', 'DraftYear': '', 'GameScope': '',
            'GameSegment': '', 'Height': '', 'ISTRound': '',
            'LastNGames': '0', 'LeagueID': '00', 'Location': '',
            'MeasureType': 'Advanced', 'Month': '0',
            'OpponentTeamID': '0', 'Outcome': '', 'PORound': '0',
            'PaceAdjust': 'N', 'PerMode': 'PerGame', 'Period': '0',
            'PlayerExperience': '', 'PlayerPosition': '',
            'PlusMinus': 'N', 'Rank': 'N', 'Season': _current_season(),
            'SeasonSegment': '', 'SeasonType': 'Regular Season',
            'ShotClockRange': '', 'StarterBench': '', 'TeamID': '0',
            'TwoWay': '0', 'VsConference': '', 'VsDivision': '',
            'Weight': '',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            hdrs = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx = {h: i for i, h in enumerate(hdrs)}
            for row in rows:
                team = row[idx.get('TEAM_ABBREVIATION', 3)]
                player = row[idx.get('PLAYER_NAME', 1)]
                if team not in result:
                    result[team] = []
                result[team].append({
                    'player': player,
                    'per': row[idx.get('PIE', 0)] * 100 if 'PIE' in idx else 15,  # PIE ≈ PER proxy
                    'usg': row[idx.get('USG_PCT', 0)] if 'USG_PCT' in idx else 0.2,
                    'plus_minus': row[idx.get('NET_RATING', 0)] if 'NET_RATING' in idx else 0,
                    'mpg': row[idx.get('MIN', 0)] if 'MIN' in idx else 0,
                })
            # Sort each team's players by minutes
            for team in result:
                result[team].sort(key=lambda x: x.get('mpg', 0), reverse=True)
            if result:
                _cache_set('player_advanced', result)
                logger.info(f"Player advanced stats: {sum(len(v) for v in result.values())} players")
                return result
    except Exception as e:
        logger.warning(f"NBA.com player stats failed: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════
# 5. LINEUP IMPACT (uses injury data + player stats)
# ═══════════════════════════════════════════════════════════════════════
def estimate_lineup_impact(team: str, injuries: List[Dict], player_stats: Dict) -> float:
    """
    Estimate point differential impact when key players are OUT.
    Returns estimated points lost per game (negative = team weaker).
    """
    if not injuries or not player_stats:
        return 0.0

    total_impact = 0.0
    # Find team's player stats (try abbreviation and full name matching)
    team_players = None
    for key, players in player_stats.items():
        if key in team or team in key:
            team_players = players
            break

    if not team_players:
        # Rough estimate: each OUT player = -2 pts, star = -5 pts
        for inj in injuries:
            if inj.get('status', '').lower() in ('out', 'doubtful'):
                impact = -5.0 if inj.get('star') else -2.0
                total_impact += impact
        return total_impact

    # Match injured players to stats
    for inj in injuries:
        if inj.get('status', '').lower() not in ('out', 'doubtful'):
            continue
        player_name = inj.get('player', '')
        for ps in team_players:
            if _name_match(player_name, ps.get('player', '')):
                # Impact ≈ minutes * plus_minus / 48
                mpg = ps.get('mpg', 0)
                pm = ps.get('plus_minus', 0)
                # Rough: player's on-court impact weighted by minutes share
                impact = -(mpg / 48.0) * max(abs(pm), 3) * (1 if pm > 0 else 0.5)
                total_impact += impact
                break
        else:
            # Player not found in stats — rough estimate
            total_impact += -5.0 if inj.get('star') else -1.5

    return total_impact


def _name_match(name1: str, name2: str) -> bool:
    """Fuzzy name match."""
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()
    if n1 == n2:
        return True
    # Last name match
    parts1 = n1.split()
    parts2 = n2.split()
    if parts1 and parts2 and parts1[-1] == parts2[-1]:
        # Also check first initial
        if parts1[0][0] == parts2[0][0]:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════
# 6. TRAVEL / FATIGUE MODEL
# ═══════════════════════════════════════════════════════════════════════
from team_locations import (
    NBA_TEAM_LOCATIONS, calculate_distance, get_timezone_difference,
    is_division_rival, is_conference_game
)

# Denver altitude (5280 ft) — visiting teams at altitude disadvantage
ALTITUDE_TEAMS = {'Denver Nuggets': 5280, 'Utah Jazz': 4226}

def compute_travel_fatigue(team: str, opponent: str, is_home: bool,
                           rest_data: Dict) -> Dict:
    """
    Compute travel/fatigue score.
    Returns {miles_traveled, tz_change, altitude_factor, fatigue_score (0-1, higher=more fatigued)}
    """
    result = {'miles': 0, 'tz_change': 0, 'altitude': 0, 'fatigue_score': 0.0}

    if is_home:
        # Home team — minimal travel fatigue
        result['fatigue_score'] = 0.1
        return result

    # Away team traveling
    miles = calculate_distance(team, opponent)
    tz = abs(get_timezone_difference(team, opponent))
    altitude = ALTITUDE_TEAMS.get(opponent, 0)

    result['miles'] = round(miles)
    result['tz_change'] = tz
    result['altitude'] = altitude

    # Fatigue formula
    fatigue = 0.0
    # Distance: 0-500mi = low, 500-1500 = medium, 1500+ = high
    if miles > 1500:
        fatigue += 0.3
    elif miles > 500:
        fatigue += 0.15

    # Timezone changes
    fatigue += tz * 0.08

    # Altitude (visiting Denver/Utah)
    if altitude > 4000:
        fatigue += 0.15

    # B2B amplifier
    team_rest = rest_data.get(team, {})
    if team_rest.get('is_b2b'):
        fatigue += 0.2
    elif team_rest.get('rest_days', 2) == 0:
        fatigue += 0.15

    # Games in 5 days
    g5 = team_rest.get('games_in_5', 0)
    if g5 >= 4:
        fatigue += 0.15
    elif g5 >= 3:
        fatigue += 0.05

    result['fatigue_score'] = min(1.0, fatigue)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 7. REFEREE TENDENCIES
# ═══════════════════════════════════════════════════════════════════════
def fetch_referee_data(target_date: date) -> Dict[str, Dict]:
    """
    Fetch ref assignments + tendencies.
    Returns {game_key: {refs: [], avg_total, avg_fouls, ou_tendency}}
    """
    cached = _cache_get(f'refs_{target_date.isoformat()}', max_age_hours=24)
    if cached:
        return cached

    result = {}

    # Try NBA.com official ref assignments
    try:
        dt_str = target_date.strftime('%m/%d/%Y')
        url = "https://official.nba.com/referee-assignments/"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Parse ref assignment tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                game_key = None
                refs = []
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        text = cells[0].text.strip()
                        if '@' in text or 'vs' in text.lower():
                            game_key = text
                        elif text and game_key:
                            refs.append(text)
                if game_key and refs:
                    result[game_key] = {
                        'refs': refs,
                        'avg_total': 215,  # default NBA avg
                        'ou_tendency': 0.0,  # 0 = neutral
                    }
    except Exception as e:
        logger.warning(f"Ref assignments fetch failed: {e}")

    if result:
        _cache_set(f'refs_{target_date.isoformat()}', result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 8. PACE MATCHUP MODELING
# ═══════════════════════════════════════════════════════════════════════
def compute_pace_matchup(home_pace: float, away_pace: float,
                         home_ortg: float, away_ortg: float,
                         home_drtg: float, away_drtg: float,
                         total_line: Optional[float]) -> Dict:
    """
    Model expected total based on pace + efficiency matchup.
    Returns {expected_total, pace_diff, ou_edge (vs line)}
    """
    # Expected possessions = average of both paces (simplified)
    avg_pace = (home_pace + away_pace) / 2.0
    league_avg_pace = 100.0

    # Expected points per 100 possessions for each team
    # Home scores at their ORtg against opponent's DRtg
    home_pts_per100 = (home_ortg + (league_avg_pace * 2 - away_drtg)) / 2.0
    away_pts_per100 = (away_ortg + (league_avg_pace * 2 - home_drtg)) / 2.0

    # Scale by actual pace
    home_pts = home_pts_per100 * (avg_pace / 100.0)
    away_pts = away_pts_per100 * (avg_pace / 100.0)

    expected_total = home_pts + away_pts

    ou_edge = 0.0
    if total_line and total_line > 0:
        ou_edge = (expected_total - total_line) / total_line  # positive = lean over

    pace_diff = abs(home_pace - away_pace)

    return {
        'expected_total': round(expected_total, 1),
        'pace_diff': round(pace_diff, 1),
        'avg_pace': round(avg_pace, 1),
        'ou_edge': round(ou_edge, 4),
    }


# ═══════════════════════════════════════════════════════════════════════
# 9. PUBLIC BETTING % / SHARP MONEY
# ═══════════════════════════════════════════════════════════════════════
def fetch_public_betting() -> Dict[str, Dict]:
    """
    Attempt to scrape public betting percentages.
    Returns {game_key: {public_spread_pct, public_ml_pct, public_ou_pct, sharp_side}}
    """
    cached = _cache_get('public_betting', max_age_hours=24)
    if cached:
        return cached

    result = {}

    # Try actionnetwork (often blocked for free)
    # Try scoresandodds.com or similar free sources
    try:
        url = "https://www.scoresandodds.com/nba"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Parse betting percentages if available
            games = soup.find_all('div', class_='event-card')
            for game in games:
                teams = game.find_all('span', class_='team-name')
                if len(teams) >= 2:
                    key = f"{teams[0].text.strip()} vs {teams[1].text.strip()}"
                    pct_els = game.find_all('span', class_='bet-pct')
                    if pct_els:
                        result[key] = {'public_spread_pct': 0.5}
    except Exception as e:
        logger.debug(f"Public betting scrape failed: {e}")

    if result:
        _cache_set('public_betting', result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 10. MOTIVATION FACTORS
# ═══════════════════════════════════════════════════════════════════════
def compute_motivation(team_stats: Dict, opp_stats: Dict,
                       team: str, opponent: str, target_date: date) -> Dict:
    """
    Assess motivation: playoff positioning, rivalry, elimination scenarios.
    Returns {motivation_score: 0-1, reasons: []}
    """
    score = 0.5  # neutral
    reasons = []

    # Playoff positioning
    if team_stats:
        wins = team_stats.get('wins', 0)
        losses = team_stats.get('losses', 0)
        total = wins + losses
        pct = wins / total if total > 0 else 0.5

        # Late season motivation (after All-Star break, ~Feb 15)
        games_played = total
        is_late_season = games_played > 55

        if is_late_season:
            # Bubble teams (7-10 seed range, ~.450-.550) are most motivated
            if 0.42 <= pct <= 0.58:
                score += 0.15
                reasons.append("Playoff bubble team — high motivation")
            # Top seeds might rest players
            elif pct > 0.70:
                score -= 0.05
                reasons.append("Top seed — possible rest/coast")
            # Tanking teams
            elif pct < 0.30:
                score -= 0.1
                reasons.append("Bottom team — tank risk")

    # Rivalry detection
    if is_division_rival(team, opponent):
        score += 0.1
        reasons.append("Division rival — extra intensity")
    elif is_conference_game(team, opponent):
        score += 0.03

    # Season series revenge (simplified — no data source, just note)
    score = max(0.0, min(1.0, score))
    return {'motivation_score': round(score, 3), 'reasons': reasons}


# ═══════════════════════════════════════════════════════════════════════
# 11. STRENGTH OF SCHEDULE
# ═══════════════════════════════════════════════════════════════════════
def fetch_strength_of_schedule() -> Dict[str, Dict]:
    """
    Fetch SOS rankings.
    Returns {team_name: {sos_rank, sos_rating, recent_sos}}
    """
    cached = _cache_get('sos', max_age_hours=24)
    if cached:
        return cached

    result = {}

    try:
        url = "https://www.teamrankings.com/nba/ranking/schedule-strength-by-other"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', class_='tr-table')
            if table:
                rows = table.find('tbody').find_all('tr') if table.find('tbody') else []
                for i, row in enumerate(rows):
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        team = cells[1].text.strip()
                        try:
                            rating = float(cells[2].text.strip())
                        except ValueError:
                            rating = 0.5
                        result[team] = {
                            'sos_rank': i + 1,
                            'sos_rating': rating,
                        }
    except Exception as e:
        logger.warning(f"SOS fetch failed: {e}")

    if result:
        _cache_set('sos', result)
        logger.info(f"SOS data for {len(result)} teams")
    return result


# ═══════════════════════════════════════════════════════════════════════
# 12. COACHING MATCHUP HISTORY
# ═══════════════════════════════════════════════════════════════════════
# This is very hard to scrape reliably. We'll use a simplified approach:
# store known coaches and approximate from team-vs-team records.

NBA_COACHES_2025_26 = {
    "Boston Celtics": "Joe Mazzulla", "Brooklyn Nets": "Jordi Fernandez",
    "New York Knicks": "Tom Thibodeau", "Philadelphia 76ers": "Nick Nurse",
    "Toronto Raptors": "Darko Rajakovic", "Chicago Bulls": "Billy Donovan",
    "Cleveland Cavaliers": "Kenny Atkinson", "Detroit Pistons": "J.B. Bickerstaff",
    "Indiana Pacers": "Rick Carlisle", "Milwaukee Bucks": "Doc Rivers",
    "Atlanta Hawks": "Quin Snyder", "Charlotte Hornets": "Charles Lee",
    "Miami Heat": "Erik Spoelstra", "Orlando Magic": "Jamahl Mosley",
    "Washington Wizards": "Brian Keefe", "Denver Nuggets": "Michael Malone",
    "Minnesota Timberwolves": "Chris Finch", "Oklahoma City Thunder": "Mark Daigneault",
    "Portland Trail Blazers": "Chauncey Billups", "Utah Jazz": "Will Hardy",
    "Golden State Warriors": "Steve Kerr", "LA Clippers": "Tyronn Lue",
    "Los Angeles Lakers": "JJ Redick", "Phoenix Suns": "Mike Budenholzer",
    "Sacramento Kings": "Mike Brown", "Dallas Mavericks": "Jason Kidd",
    "Houston Rockets": "Ime Udoka", "Memphis Grizzlies": "Taylor Jenkins",
    "New Orleans Pelicans": "Willie Green", "San Antonio Spurs": "Gregg Popovich",
}

def get_coaching_matchup(home: str, away: str) -> Dict:
    """Return coaching matchup info."""
    home_coach = NBA_COACHES_2025_26.get(home, 'Unknown')
    away_coach = NBA_COACHES_2025_26.get(away, 'Unknown')
    # Experience-based edge (very rough)
    veteran_coaches = {'Gregg Popovich', 'Erik Spoelstra', 'Steve Kerr', 'Doc Rivers',
                       'Rick Carlisle', 'Tom Thibodeau', 'Mike Budenholzer', 'Tyronn Lue',
                       'Nick Nurse', 'Jason Kidd', 'Michael Malone'}
    home_vet = home_coach in veteran_coaches
    away_vet = away_coach in veteran_coaches
    edge = 0.0
    if home_vet and not away_vet:
        edge = 0.05
    elif away_vet and not home_vet:
        edge = -0.05
    return {
        'home_coach': home_coach, 'away_coach': away_coach,
        'coaching_edge': edge,  # positive = home coach advantage
    }


# ═══════════════════════════════════════════════════════════════════════
# 13. QUARTER-BY-QUARTER PATTERNS
# ═══════════════════════════════════════════════════════════════════════
def fetch_quarter_patterns() -> Dict[str, Dict]:
    """
    Fetch Q1-Q4 scoring patterns.
    Returns {team_name: {q1_avg, q2_avg, q3_avg, q4_avg, q4_diff (relative), fast_start, strong_close}}
    """
    cached = _cache_get('quarter_patterns', max_age_hours=24)
    if cached:
        return cached

    result = {}

    try:
        # ESPN doesn't easily expose this; try basketball-reference
        url = f"https://www.basketball-reference.com/leagues/NBA_{_current_year()}.html"
        r = _get(url)
        if r:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Look for per-quarter stats table
            # BBRef has team per-game stats but not always broken by quarter on main page
            # We'll use a simplified approach
            pass
    except Exception as e:
        logger.warning(f"Quarter patterns fetch failed: {e}")

    # If no data, return empty — engine will use 0.5 neutral
    if result:
        _cache_set('quarter_patterns', result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# 14. CLUTCH PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════
def fetch_clutch_stats() -> Dict[str, Dict]:
    """
    Fetch clutch/close game records (games decided by ≤5 points).
    Returns {team_name: {clutch_wins, clutch_losses, clutch_pct}}
    """
    cached = _cache_get('clutch_stats', max_age_hours=24)
    if cached:
        return cached

    result = {}

    # Try NBA.com clutch stats
    try:
        url = "https://stats.nba.com/stats/leaguedashteamclutch"
        params = {
            'AheadBehind': 'Ahead or Behind',
            'ClutchTime': 'Last 5 Minutes',
            'Conference': '', 'DateFrom': '', 'DateTo': '',
            'Division': '', 'GameScope': '', 'GameSegment': '',
            'ISTRound': '', 'LastNGames': '0', 'LeagueID': '00',
            'Location': '', 'MeasureType': 'Base', 'Month': '0',
            'OpponentTeamID': '0', 'Outcome': '', 'PORound': '0',
            'PaceAdjust': 'N', 'PerMode': 'Totals', 'Period': '0',
            'PlayerExperience': '', 'PlayerPosition': '',
            'PointDiff': '5', 'PlusMinus': 'N', 'Rank': 'N',
            'Season': _current_season(), 'SeasonSegment': '',
            'SeasonType': 'Regular Season', 'ShotClockRange': '',
            'StarterBench': '', 'TeamID': '0', 'VsConference': '',
            'VsDivision': '',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            hdrs = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx = {h: i for i, h in enumerate(hdrs)}
            for row in rows:
                name = row[idx.get('TEAM_NAME', 1)]
                w = row[idx.get('W', 0)] if 'W' in idx else 0
                l = row[idx.get('L', 0)] if 'L' in idx else 0
                total = w + l
                result[name] = {
                    'clutch_wins': w, 'clutch_losses': l,
                    'clutch_pct': w / total if total > 0 else 0.5,
                }
            if result:
                _cache_set('clutch_stats', result)
                logger.info(f"Clutch stats for {len(result)} teams")
                return result
    except Exception as e:
        logger.warning(f"NBA.com clutch stats failed: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════
# 15. FREE THROW RATE DIFFERENTIAL
# ═══════════════════════════════════════════════════════════════════════
def fetch_ft_rate() -> Dict[str, Dict]:
    """
    Fetch FTA/FGA ratio (free throw rate).
    Returns {team_name: {ft_rate, opp_ft_rate, ft_diff}}
    """
    cached = _cache_get('ft_rate', max_age_hours=24)
    if cached:
        return cached

    result = {}

    try:
        url = "https://stats.nba.com/stats/leaguedashteamstats"
        params = {
            'Conference': '', 'DateFrom': '', 'DateTo': '',
            'Division': '', 'GameScope': '', 'GameSegment': '',
            'Height': '', 'ISTRound': '', 'LastNGames': '0',
            'LeagueID': '00', 'Location': '', 'MeasureType': 'Base',
            'Month': '0', 'OpponentTeamID': '0', 'Outcome': '',
            'PORound': '0', 'PaceAdjust': 'N', 'PerMode': 'PerGame',
            'Period': '0', 'PlayerExperience': '', 'PlayerPosition': '',
            'PlusMinus': 'N', 'Rank': 'N', 'Season': _current_season(),
            'SeasonSegment': '', 'SeasonType': 'Regular Season',
            'ShotClockRange': '', 'StarterBench': '', 'TeamID': '0',
            'TwoWay': '0', 'VsConference': '', 'VsDivision': '',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            hdrs = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx_map = {h: i for i, h in enumerate(hdrs)}
            for row in rows:
                name = row[idx_map.get('TEAM_NAME', 1)]
                fta = row[idx_map.get('FTA', 0)] if 'FTA' in idx_map else 20
                fga = row[idx_map.get('FGA', 0)] if 'FGA' in idx_map else 85
                ft_rate = fta / fga if fga > 0 else 0.25
                result[name] = {'ft_rate': round(ft_rate, 4), 'fta': fta, 'fga': fga}
            if result:
                _cache_set('ft_rate', result)
                logger.info(f"FT rate data for {len(result)} teams")
                return result
    except Exception as e:
        logger.warning(f"NBA.com FT rate failed: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════
def _current_season() -> str:
    """Return NBA season string like '2025-26'."""
    now = datetime.now()
    year = now.year
    if now.month >= 10:
        return f"{year}-{str(year+1)[-2:]}"
    return f"{year-1}-{str(year)[-2:]}"

def _current_year() -> int:
    """Return the ending year of the current NBA season (for BBRef URLs)."""
    now = datetime.now()
    if now.month >= 10:
        return now.year + 1
    return now.year


# ═══════════════════════════════════════════════════════════════════════
# TEAM NAME FUZZY MATCHING
# ═══════════════════════════════════════════════════════════════════════
# Common abbreviation/name variants
_TEAM_ALIASES = {
    'lal': 'Los Angeles Lakers', 'lakers': 'Los Angeles Lakers',
    'lac': 'LA Clippers', 'clippers': 'LA Clippers',
    'gsw': 'Golden State Warriors', 'warriors': 'Golden State Warriors',
    'bos': 'Boston Celtics', 'celtics': 'Boston Celtics',
    'nyk': 'New York Knicks', 'knicks': 'New York Knicks',
    'bkn': 'Brooklyn Nets', 'nets': 'Brooklyn Nets',
    'phi': 'Philadelphia 76ers', '76ers': 'Philadelphia 76ers', 'sixers': 'Philadelphia 76ers',
    'tor': 'Toronto Raptors', 'raptors': 'Toronto Raptors',
    'chi': 'Chicago Bulls', 'bulls': 'Chicago Bulls',
    'cle': 'Cleveland Cavaliers', 'cavaliers': 'Cleveland Cavaliers', 'cavs': 'Cleveland Cavaliers',
    'det': 'Detroit Pistons', 'pistons': 'Detroit Pistons',
    'ind': 'Indiana Pacers', 'pacers': 'Indiana Pacers',
    'mil': 'Milwaukee Bucks', 'bucks': 'Milwaukee Bucks',
    'atl': 'Atlanta Hawks', 'hawks': 'Atlanta Hawks',
    'cha': 'Charlotte Hornets', 'hornets': 'Charlotte Hornets',
    'mia': 'Miami Heat', 'heat': 'Miami Heat',
    'orl': 'Orlando Magic', 'magic': 'Orlando Magic',
    'was': 'Washington Wizards', 'wizards': 'Washington Wizards',
    'den': 'Denver Nuggets', 'nuggets': 'Denver Nuggets',
    'min': 'Minnesota Timberwolves', 'timberwolves': 'Minnesota Timberwolves', 'wolves': 'Minnesota Timberwolves',
    'okc': 'Oklahoma City Thunder', 'thunder': 'Oklahoma City Thunder',
    'por': 'Portland Trail Blazers', 'blazers': 'Portland Trail Blazers', 'trail blazers': 'Portland Trail Blazers',
    'uta': 'Utah Jazz', 'jazz': 'Utah Jazz',
    'phx': 'Phoenix Suns', 'suns': 'Phoenix Suns',
    'sac': 'Sacramento Kings', 'kings': 'Sacramento Kings',
    'dal': 'Dallas Mavericks', 'mavericks': 'Dallas Mavericks', 'mavs': 'Dallas Mavericks',
    'hou': 'Houston Rockets', 'rockets': 'Houston Rockets',
    'mem': 'Memphis Grizzlies', 'grizzlies': 'Memphis Grizzlies',
    'nop': 'New Orleans Pelicans', 'pelicans': 'New Orleans Pelicans',
    'sas': 'San Antonio Spurs', 'spurs': 'San Antonio Spurs',
}

def resolve_team(name: str) -> str:
    """Try to resolve a team name to its full canonical name."""
    if not name:
        return name
    # Direct match in locations
    if name in NBA_TEAM_LOCATIONS:
        return name
    # Alias match
    key = name.lower().strip()
    if key in _TEAM_ALIASES:
        return _TEAM_ALIASES[key]
    # Last word match
    last = key.split()[-1]
    if last in _TEAM_ALIASES:
        return _TEAM_ALIASES[last]
    # Substring match
    for full_name in NBA_TEAM_LOCATIONS:
        if key in full_name.lower() or full_name.lower() in key:
            return full_name
    return name


def find_in_data(team: str, data: Dict) -> Optional[Dict]:
    """Find team in a data dict, trying fuzzy matching."""
    if not data:
        return None
    if team in data:
        return data[team]
    resolved = resolve_team(team)
    if resolved in data:
        return data[resolved]
    # Try last word
    last = team.split()[-1].lower()
    for k, v in data.items():
        if last in k.lower():
            return v
    return None
