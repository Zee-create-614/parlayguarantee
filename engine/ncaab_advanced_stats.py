"""
NCAAB Advanced Stats Scraper — Rex V2 Data Layer
=================================================
Scrapes and caches advanced stats from multiple sources for the Rex V2 engine.
All scrapers fail gracefully → return neutral defaults (0.5 or empty).

Sources:
  - barttorvik.com (efficiency, tempo, SOS)
  - ESPN (player stats, schedules, rankings)
  - covers.com / teamrankings.com (ATS trends)
  - actionnetwork / scoresandodds (public betting %)

Cache: file-based JSON with TTL (default 6 hours for most, 24h for static data).
"""

import os
import json
import time
import math
import logging
import hashlib
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'ncaab_cache', 'rex_v2')
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# ─── Cache Helpers ──────────────────────────────────────────────

def _cache_key(prefix: str, *args) -> str:
    raw = f"{prefix}_{'_'.join(str(a) for a in args)}"
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cache(key: str, ttl_hours: float = 6.0) -> Optional[dict]:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > ttl_hours * 3600:
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def _set_cache(key: str, data: dict):
    path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")

def _safe_request(url: str, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
        if resp.status_code == 200:
            return resp
        logger.warning(f"HTTP {resp.status_code} from {url}")
    except Exception as e:
        logger.warning(f"Request failed {url}: {e}")
    return None


# ─── 1. Barttorvik Efficiency Data ─────────────────────────────

def fetch_barttorvik_stats() -> Dict[str, Dict]:
    """
    Fetch team efficiency data from barttorvik.com.
    Returns dict keyed by lowercase team name with:
      ortg, drtg, net_rtg, tempo, sos, barthag, etc.
    """
    key = _cache_key('barttorvik', date.today().isoformat())
    cached = _get_cache(key, ttl_hours=8.0)
    if cached:
        return cached

    teams = {}
    try:
        # Barttorvik JSON endpoint for current season
        url = "https://barttorvik.com/trank.php?year=2026&sort=&conlimit=All&top=0&quad=5&venue=All&type=pointed&mingames=0&begin=&end=&css=1"
        resp = _safe_request(url)
        if not resp:
            # Fallback: try the API-style endpoint
            url = "https://barttorvik.com/getadjstats.php?year=2026"
            resp = _safe_request(url)

        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]  # skip header
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 10:
                        try:
                            name = cols[1].get_text(strip=True).lower()
                            # Clean up name — remove seed numbers, etc.
                            name = name.split('\xa0')[0].strip()
                            teams[name] = {
                                'rank': _safe_float(cols[0].get_text(strip=True)),
                                'ortg': _safe_float(cols[4].get_text(strip=True), 100.0),
                                'drtg': _safe_float(cols[5].get_text(strip=True), 100.0),
                                'net_rtg': 0,
                                'tempo': _safe_float(cols[6].get_text(strip=True), 67.0),
                                'barthag': _safe_float(cols[3].get_text(strip=True), 0.5),
                                'sos': _safe_float(cols[9].get_text(strip=True), 0.5) if len(cols) > 9 else 0.5,
                            }
                            teams[name]['net_rtg'] = teams[name]['ortg'] - teams[name]['drtg']
                        except Exception:
                            continue
            logger.info(f"Barttorvik: scraped {len(teams)} teams")
    except Exception as e:
        logger.warning(f"Barttorvik scrape failed: {e}")

    if teams:
        _set_cache(key, teams)
    return teams


# ─── 2. ATS Trends ─────────────────────────────────────────────

def fetch_ats_trends(team_name: str) -> Dict:
    """
    Fetch ATS trends for a team. Try teamrankings.com or covers.com.
    Returns: {season_ats, home_ats, away_ats, l10_ats, conf_ats}
    """
    default = {'season_ats': 0.5, 'home_ats': 0.5, 'away_ats': 0.5,
               'l10_ats': 0.5, 'conf_ats': 0.5}

    key = _cache_key('ats', team_name, date.today().isoformat())
    cached = _get_cache(key, ttl_hours=8.0)
    if cached:
        return cached

    # TeamRankings scrape disabled — URL format requires mascot names we don't map.
    # ATS defaults to 0.5 (neutral). TODO: find a better ATS data source.

    _set_cache(key, default)
    return default


# ─── 3. Player Impact Stats ────────────────────────────────────

def fetch_top_players(team_name: str, espn_team_id: str = '') -> List[Dict]:
    """
    Fetch top players for a team from ESPN.
    Returns list of {name, ppg, usage_pct, status} sorted by ppg desc.
    """
    key = _cache_key('players', team_name, date.today().isoformat())
    cached = _get_cache(key, ttl_hours=12.0)
    if cached:
        return cached

    players = []

    if not espn_team_id:
        espn_team_id = _resolve_espn_team_id(team_name)

    if espn_team_id:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{espn_team_id}/roster"
            resp = _safe_request(url)
            if resp:
                data = resp.json()
                for athlete in data.get('athletes', []):
                    stats = {}
                    for cat in athlete.get('statistics', []):
                        if cat.get('type') == 'total':
                            for s in cat.get('stats', []):
                                stats[s.get('name', '')] = s.get('value', 0)
                    players.append({
                        'name': athlete.get('displayName', ''),
                        'ppg': stats.get('avgPoints', 0),
                        'usage_pct': 0.0,  # ESPN doesn't always have this
                        'status': 'active',
                    })
        except Exception as e:
            logger.debug(f"Player fetch failed for {team_name}: {e}")

    # Try stats endpoint
    if not players and espn_team_id:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{espn_team_id}/statistics"
            resp = _safe_request(url)
            if resp:
                data = resp.json()
                leaders = data.get('leaders', [])
                for cat in leaders:
                    if cat.get('name') == 'pointsPerGame':
                        for leader in cat.get('leaders', [])[:5]:
                            ath = leader.get('athlete', {})
                            players.append({
                                'name': ath.get('displayName', ''),
                                'ppg': _safe_float(leader.get('value', '0'), 0),
                                'usage_pct': 0.0,
                                'status': 'active',
                            })
        except Exception:
            pass

    players.sort(key=lambda p: p.get('ppg', 0), reverse=True)
    if players:
        _set_cache(key, players)
    return players[:5]


# ─── 4. Team Schedule / Rest Days ──────────────────────────────

def fetch_recent_schedule(team_name: str, espn_team_id: str = '') -> List[Dict]:
    """
    Fetch recent games from ESPN schedule to compute rest days and schedule density.
    Returns list of {date, opponent, home_away, result} for last ~10 games.
    """
    key = _cache_key('schedule', team_name, date.today().isoformat())
    cached = _get_cache(key, ttl_hours=12.0)
    if cached:
        return cached

    games = []
    if not espn_team_id:
        espn_team_id = _resolve_espn_team_id(team_name)

    if espn_team_id:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{espn_team_id}/schedule"
            resp = _safe_request(url)
            if resp:
                data = resp.json()
                for event in data.get('events', []):
                    game_date_str = event.get('date', '')
                    try:
                        game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00')).date()
                    except Exception:
                        continue

                    competitions = event.get('competitions', [{}])
                    comp = competitions[0] if competitions else {}
                    competitors = comp.get('competitors', [])

                    opp = ''
                    home_away = 'neutral'
                    result = ''
                    for c in competitors:
                        team = c.get('team', {})
                        tid = str(team.get('id', ''))
                        if tid == str(espn_team_id):
                            home_away = c.get('homeAway', 'neutral')
                            winner = c.get('winner', None)
                            score = c.get('score', '')
                            result = 'W' if winner else ('L' if winner is False else '')
                        else:
                            opp = team.get('displayName', team.get('shortDisplayName', ''))

                    games.append({
                        'date': game_date.isoformat(),
                        'opponent': opp,
                        'home_away': home_away,
                        'result': result,
                    })
        except Exception as e:
            logger.debug(f"Schedule fetch failed for {team_name}: {e}")

    if games:
        _set_cache(key, games)
    return games


def compute_rest_and_density(schedule: List[Dict], target_date: date) -> Dict:
    """
    From a schedule, compute:
      - rest_days: days since last game
      - games_in_7: number of games in last 7 days
      - games_in_14: number of games in last 14 days
      - b2b: True if back-to-back
    """
    result = {'rest_days': 3, 'games_in_7': 1, 'games_in_14': 2, 'b2b': False}

    past_games = []
    for g in schedule:
        try:
            gd = date.fromisoformat(g['date'])
            if gd < target_date:
                past_games.append(gd)
        except Exception:
            continue

    if not past_games:
        return result

    past_games.sort(reverse=True)
    last_game = past_games[0]
    result['rest_days'] = (target_date - last_game).days
    result['b2b'] = result['rest_days'] <= 1
    result['games_in_7'] = sum(1 for d in past_games if (target_date - d).days <= 7)
    result['games_in_14'] = sum(1 for d in past_games if (target_date - d).days <= 14)

    return result


# ─── 5. NCAAB Team Locations (for travel) ──────────────────────

# Top ~120 D1 programs with lat/lng
NCAAB_TEAM_LOCATIONS = {
    # ACC
    "duke": (36.0014, -78.9382), "north carolina": (35.9049, -79.0469),
    "nc state": (35.7872, -78.6782), "wake forest": (36.1340, -80.2774),
    "virginia": (38.0470, -78.5090), "virginia tech": (37.2296, -80.4139),
    "clemson": (34.6834, -82.8374), "florida state": (30.4383, -84.3063),
    "georgia tech": (33.7573, -84.3963), "louisville": (38.2190, -85.7586),
    "miami": (25.7178, -80.2013), "notre dame": (41.7053, -86.2353),
    "pittsburgh": (40.4435, -79.9625), "syracuse": (43.0481, -76.1474),
    "boston college": (42.3355, -71.1685), "cal": (37.8708, -122.2466),
    "smu": (32.8412, -96.7832), "stanford": (37.4346, -122.1609),
    # Big 12
    "kansas": (38.9543, -95.2528), "kansas state": (39.1974, -96.5847),
    "iowa state": (42.0140, -93.6358), "baylor": (31.5584, -97.1163),
    "texas tech": (33.5907, -101.8478), "tcu": (32.7100, -97.3685),
    "oklahoma state": (36.1262, -97.0660), "west virginia": (39.6500, -79.9559),
    "cincinnati": (39.1310, -84.5167), "ucf": (28.6024, -81.2001),
    "houston": (29.7210, -95.3413), "byu": (40.2518, -111.6493),
    "colorado": (40.0076, -105.2659), "arizona": (32.2319, -110.9501),
    "arizona state": (33.4527, -111.9328), "utah": (40.7649, -111.8421),
    # Big Ten
    "michigan": (42.2655, -83.7485), "michigan state": (42.7284, -84.4920),
    "ohio state": (40.0066, -83.0236), "indiana": (39.1696, -86.5186),
    "purdue": (40.4445, -86.9247), "illinois": (40.0966, -88.2353),
    "iowa": (41.6554, -91.5490), "minnesota": (44.9748, -93.2314),
    "wisconsin": (43.0698, -89.4130), "nebraska": (40.8202, -96.7005),
    "northwestern": (42.0596, -87.6737), "maryland": (38.9946, -76.9425),
    "penn state": (40.8122, -77.8566), "rutgers": (40.5135, -74.4653),
    "usc": (34.0224, -118.2851), "ucla": (34.0689, -118.4452),
    "oregon": (44.0463, -123.0726), "washington": (47.6528, -122.3045),
    # SEC
    "kentucky": (38.0464, -84.5030), "tennessee": (35.9544, -83.9295),
    "auburn": (32.6060, -85.4808), "alabama": (33.2098, -87.5692),
    "arkansas": (36.0689, -94.1748), "florida": (29.6499, -82.3486),
    "georgia": (33.9519, -83.3738), "lsu": (30.4124, -91.1837),
    "mississippi state": (33.4552, -88.7893), "ole miss": (34.3643, -89.5383),
    "missouri": (38.9517, -92.3341), "south carolina": (34.0007, -81.0228),
    "vanderbilt": (36.1447, -86.8027), "texas a&m": (30.6046, -96.3399),
    "texas": (30.2849, -97.7341), "oklahoma": (35.2057, -97.4452),
    # Big East
    "uconn": (41.8075, -72.2540), "villanova": (40.0349, -75.3430),
    "creighton": (41.2647, -95.9455), "marquette": (43.0389, -87.9302),
    "xavier": (39.1496, -84.4738), "seton hall": (40.7419, -74.2457),
    "st. john's": (40.7230, -73.7959), "georgetown": (38.9076, -77.0723),
    "providence": (41.8414, -71.4356), "butler": (39.8381, -86.1694),
    "depaul": (41.8758, -87.6559),
    # Top mid-majors
    "gonzaga": (47.6672, -117.4020), "memphis": (35.1182, -89.9413),
    "saint mary's": (37.8397, -122.1091), "dayton": (39.7422, -84.1754),
    "drake": (41.6010, -93.6508), "vcu": (37.5504, -77.4503),
    "san diego state": (32.7752, -117.0712), "boise state": (43.6027, -116.1976),
    "new mexico": (35.0795, -106.6262), "nevada": (39.5439, -119.8151),
    "loyola chicago": (41.9998, -87.6582), "murray state": (36.7623, -88.3218),
    "wichita state": (37.7217, -97.2951), "uab": (33.5007, -86.8093),
    "middle tennessee": (35.8480, -86.3628),
}


def get_travel_distance(team1: str, team2: str) -> float:
    """
    Compute approximate travel distance in miles between two teams.
    Uses haversine formula. Returns 0 if either team not found.
    """
    t1 = team1.lower()
    t2 = team2.lower()

    loc1 = _find_location(t1)
    loc2 = _find_location(t2)

    if not loc1 or not loc2:
        return 0.0

    return _haversine(loc1[0], loc1[1], loc2[0], loc2[1])


def _find_location(team_lower: str) -> Optional[Tuple[float, float]]:
    """Fuzzy match team name to locations dict."""
    if team_lower in NCAAB_TEAM_LOCATIONS:
        return NCAAB_TEAM_LOCATIONS[team_lower]
    # Try partial match
    for key, loc in NCAAB_TEAM_LOCATIONS.items():
        if key in team_lower or team_lower in key:
            return loc
    return None


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ─── 6. Public Betting % ───────────────────────────────────────

def fetch_public_betting(home_team: str, away_team: str) -> Dict:
    """
    Try to get public betting percentages.
    Returns {home_pct, away_pct} or defaults {0.5, 0.5}.
    """
    default = {'home_pct': 0.5, 'away_pct': 0.5}

    key = _cache_key('public_bet', home_team, away_team, date.today().isoformat())
    cached = _get_cache(key, ttl_hours=4.0)
    if cached:
        return cached

    # Try scoresandodds or actionnetwork (often blocked, best effort)
    try:
        url = "https://www.scoresandodds.com/ncaab"
        resp = _safe_request(url)
        if resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Look for the matchup and betting %
            text = soup.get_text().lower()
            h_lower = home_team.lower()
            a_lower = away_team.lower()
            if h_lower in text or a_lower in text:
                # Very rough — real scraping would need more structure
                import re
                pcts = re.findall(r'(\d{1,2})%', text)
                # Just use defaults — this source is unreliable without JS
                pass
    except Exception:
        pass

    _set_cache(key, default)
    return default


# ─── 7. Home Court Advantage Data ──────────────────────────────

# Historically difficult home courts (edge multiplier, 1.0 = average)
ELITE_HOME_COURTS = {
    "duke": 1.35, "kansas": 1.40, "kentucky": 1.30,
    "gonzaga": 1.25, "michigan state": 1.20, "north carolina": 1.15,
    "indiana": 1.20, "syracuse": 1.15, "purdue": 1.20,
    "wisconsin": 1.15, "virginia": 1.15, "tennessee": 1.20,
    "auburn": 1.25, "baylor": 1.15, "west virginia": 1.20,
    "iowa state": 1.25, "creighton": 1.15, "marquette": 1.15,
    "cincinnati": 1.15, "texas tech": 1.20, "arkansas": 1.15,
    "illinois": 1.15, "memphis": 1.15, "uconn": 1.15,
    "villanova": 1.10, "florida": 1.15, "alabama": 1.15,
    "san diego state": 1.20, "new mexico": 1.30, "byu": 1.20,
    "xavier": 1.10, "vcu": 1.15,
}


def get_home_court_multiplier(team_name: str) -> float:
    """Return home court advantage multiplier (1.0 = average, >1.0 = tougher)."""
    t = team_name.lower()
    if t in ELITE_HOME_COURTS:
        return ELITE_HOME_COURTS[t]
    for key, val in ELITE_HOME_COURTS.items():
        if key in t or t in key:
            return val
    return 1.0


# ─── 8. Coaching Data ──────────────────────────────────────────

# Top coaches: {name_lower: {years_hc, tourney_apps, final_fours, titles}}
COACHING_DATA = {
    "duke": {"coach": "Jon Scheyer", "years": 4, "tourney": 2, "f4": 0, "titles": 0},
    "kansas": {"coach": "Bill Self", "years": 23, "tourney": 19, "f4": 4, "titles": 2},
    "kentucky": {"coach": "Mark Pope", "years": 2, "tourney": 1, "f4": 0, "titles": 0},
    "north carolina": {"coach": "Hubert Davis", "years": 5, "tourney": 3, "f4": 1, "titles": 1},
    "gonzaga": {"coach": "Mark Few", "years": 26, "tourney": 24, "f4": 2, "titles": 0},
    "uconn": {"coach": "Dan Hurley", "years": 8, "tourney": 5, "f4": 2, "titles": 2},
    "houston": {"coach": "Kelvin Sampson", "years": 10, "tourney": 5, "f4": 2, "titles": 0},
    "purdue": {"coach": "Matt Painter", "years": 20, "tourney": 12, "f4": 1, "titles": 0},
    "tennessee": {"coach": "Rick Barnes", "years": 10, "tourney": 5, "f4": 0, "titles": 0},
    "alabama": {"coach": "Nate Oats", "years": 6, "tourney": 3, "f4": 1, "titles": 0},
    "auburn": {"coach": "Bruce Pearl", "years": 10, "tourney": 5, "f4": 1, "titles": 0},
    "michigan state": {"coach": "Tom Izzo", "years": 30, "tourney": 24, "f4": 8, "titles": 2},
    "iowa state": {"coach": "T.J. Otzelberger", "years": 5, "tourney": 3, "f4": 0, "titles": 0},
    "baylor": {"coach": "Scott Drew", "years": 22, "tourney": 10, "f4": 1, "titles": 1},
    "arkansas": {"coach": "John Calipari", "years": 2, "tourney": 0, "f4": 0, "titles": 0},
    "texas": {"coach": "Rodney Terry", "years": 3, "tourney": 1, "f4": 0, "titles": 0},
    "creighton": {"coach": "Greg McDermott", "years": 15, "tourney": 7, "f4": 0, "titles": 0},
    "marquette": {"coach": "Shaka Smart", "years": 5, "tourney": 3, "f4": 0, "titles": 0},
    "villanova": {"coach": "Kyle Neptune", "years": 4, "tourney": 1, "f4": 0, "titles": 0},
    "florida": {"coach": "Todd Golden", "years": 4, "tourney": 2, "f4": 0, "titles": 0},
    "ucla": {"coach": "Mick Cronin", "years": 6, "tourney": 4, "f4": 1, "titles": 0},
    "arizona": {"coach": "Tommy Lloyd", "years": 5, "tourney": 3, "f4": 0, "titles": 0},
    "wisconsin": {"coach": "Greg Gard", "years": 10, "tourney": 5, "f4": 0, "titles": 0},
}


def get_coaching_score(team_name: str) -> float:
    """Return 0-1 coaching experience score."""
    t = team_name.lower()
    data = None
    if t in COACHING_DATA:
        data = COACHING_DATA[t]
    else:
        for key, val in COACHING_DATA.items():
            if key in t or t in key:
                data = val
                break

    if not data:
        return 0.4  # unknown coach = slightly below average

    # Weighted score: years, tourney experience, deep runs
    score = (
        min(data['years'] / 25, 1.0) * 0.3 +
        min(data['tourney'] / 20, 1.0) * 0.3 +
        min(data['f4'] / 5, 1.0) * 0.25 +
        min(data['titles'] / 2, 1.0) * 0.15
    )
    return min(1.0, score)


# ─── 9. Rivalry Detection ──────────────────────────────────────

RIVALRIES = [
    {"duke", "north carolina"}, {"duke", "nc state"},
    {"kentucky", "louisville"}, {"indiana", "purdue"},
    {"kansas", "kansas state"}, {"michigan", "michigan state"},
    {"michigan", "ohio state"}, {"ohio state", "michigan state"},
    {"iowa", "iowa state"}, {"florida", "florida state"},
    {"north carolina", "nc state"}, {"virginia", "virginia tech"},
    {"arizona", "arizona state"}, {"usc", "ucla"},
    {"oklahoma", "oklahoma state"}, {"texas", "texas a&m"},
    {"auburn", "alabama"}, {"georgia", "georgia tech"},
    {"clemson", "south carolina"}, {"oregon", "oregon state"},
    {"cincinnati", "xavier"}, {"georgetown", "syracuse"},
    {"marquette", "wisconsin"}, {"utah", "byu"},
    {"louisville", "cincinnati"}, {"memphis", "cincinnati"},
    {"pittsburgh", "west virginia"}, {"stanford", "cal"},
    {"baylor", "tcu"}, {"texas tech", "texas"},
]


def is_rivalry(team1: str, team2: str) -> bool:
    t1 = team1.lower()
    t2 = team2.lower()
    for pair in RIVALRIES:
        p = [x.lower() for x in pair]
        if (t1 in p[0] or p[0] in t1) and (t2 in p[1] or p[1] in t2):
            return True
        if (t1 in p[1] or p[1] in t1) and (t2 in p[0] or p[0] in t2):
            return True
    return False


# ─── 10. Motivation Factors ────────────────────────────────────

def compute_motivation_score(team_name: str, rank: int, conference: str,
                             wins: int, losses: int, target_date: date) -> float:
    """
    Estimate motivation level 0-1 based on:
      - Bubble team fighting for tournament (ranks 30-70, near .500 or better)
      - Conference tournament seeding implications (late Feb/early March)
      - Late season = higher stakes
    """
    score = 0.5  # baseline

    # Bubble team boost (ranks ~25-70 with decent record)
    total = wins + losses
    wp = wins / max(total, 1)
    if 25 <= rank <= 75 and wp >= 0.55:
        score += 0.15  # fighting for at-large bid
    elif rank <= 25:
        score += 0.05  # seeding matters

    # Conference tournament time (late Feb / March)
    month = target_date.month
    day = target_date.day
    if month == 3 or (month == 2 and day >= 20):
        score += 0.10  # every game matters
    if month == 2 and day >= 25:
        score += 0.05  # regular season finale push

    # Poor record teams may have less to play for
    if wp < 0.40 and rank > 100:
        score -= 0.10

    return max(0.0, min(1.0, score))


# ─── 11. Conference vs Non-Conference Performance ──────────────

def compute_conf_vs_nonconf(schedule: List[Dict], conference: str) -> Dict:
    """
    Analyze schedule to separate conference vs non-conference performance.
    Returns {conf_wp, nonconf_wp, split_score} where split_score indicates
    if team pads stats in non-con (negative) or performs consistently (positive).
    """
    # Without detailed opponent conference data, we approximate:
    # Games after Dec 31 are mostly conference, before are mostly non-conference
    conf_w, conf_l, nonconf_w, nonconf_l = 0, 0, 0, 0

    for g in schedule:
        try:
            gd = date.fromisoformat(g['date'])
            is_conf = gd.month >= 1 and gd.day >= 1 and gd.month <= 3  # rough
            if gd.month >= 11:
                is_conf = False  # November/December = non-conference
            r = g.get('result', '')
            if is_conf:
                if r == 'W': conf_w += 1
                elif r == 'L': conf_l += 1
            else:
                if r == 'W': nonconf_w += 1
                elif r == 'L': nonconf_l += 1
        except Exception:
            continue

    conf_total = conf_w + conf_l
    nonconf_total = nonconf_w + nonconf_l
    conf_wp = conf_w / max(conf_total, 1)
    nonconf_wp = nonconf_w / max(nonconf_total, 1)

    # split_score: positive = conference performance matches or exceeds non-conf
    # negative = team padded stats in non-conference
    split_score = conf_wp - nonconf_wp * 0.8  # discount non-conf slightly

    return {'conf_wp': conf_wp, 'nonconf_wp': nonconf_wp, 'split_score': split_score}


# ─── Helpers ────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(',', '').strip())
    except (ValueError, TypeError):
        return default


def _resolve_espn_team_id(team_name: str) -> str:
    """Try to resolve ESPN team ID from name using search API."""
    key = _cache_key('espn_id', team_name)
    cached = _get_cache(key, ttl_hours=168.0)  # 1 week
    if cached:
        return cached.get('id', '')

    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams"
        resp = _safe_request(url, params={'limit': 400})
        if resp:
            data = resp.json()
            teams = data.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
            name_lower = team_name.lower()
            for t in teams:
                team = t.get('team', {})
                names = [
                    team.get('displayName', '').lower(),
                    team.get('shortDisplayName', '').lower(),
                    team.get('name', '').lower(),
                    team.get('abbreviation', '').lower(),
                ]
                if name_lower in names or any(name_lower in n for n in names):
                    tid = str(team.get('id', ''))
                    _set_cache(key, {'id': tid})
                    return tid
    except Exception:
        pass

    return ''


# ─── Composite Normalizers ──────────────────────────────────────

def normalize_to_edge(home_val: float, away_val: float,
                      scale: float = 1.0, higher_better: bool = True) -> float:
    """
    Convert a home vs away stat comparison to a -1 to +1 edge score.
    Positive = home advantage. Then map to 0-1 range (0.5 = neutral).
    """
    if higher_better:
        diff = home_val - away_val
    else:
        diff = away_val - home_val  # lower is better (e.g., defensive rating)

    # Normalize by scale
    edge = diff / max(abs(scale), 0.01)
    edge = max(-1.0, min(1.0, edge))

    # Map to 0-1 (0.5 = neutral)
    return 0.5 + edge * 0.5
