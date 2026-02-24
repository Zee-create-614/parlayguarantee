"""
MLB Data Fetcher — Baseball Stats for ParlayGuarantee
Sources: ESPN API, The Odds API, cached in SQLite
"""

import requests
import json
import time
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'mlb_data.db')
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'mlb_cache')
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ESPN_MLB_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
ESPN_MLB_STANDINGS = "https://site.api.espn.com/apis/v2/sports/baseball/mlb/standings"
ESPN_MLB_TEAMS = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# Park factors (runs multiplier relative to neutral; >1.0 = hitter-friendly)
PARK_FACTORS = {
    'Coors Field': 1.30, 'Great American Ball Park': 1.10, 'Fenway Park': 1.08,
    'Globe Life Field': 1.05, 'Citizens Bank Park': 1.06, 'Guaranteed Rate Field': 1.04,
    'Wrigley Field': 1.03, 'Yankee Stadium': 1.05, 'Minute Maid Park': 1.02,
    'Camden Yards': 1.02, 'Nationals Park': 1.01, 'Kauffman Stadium': 0.97,
    'Busch Stadium': 0.97, 'Dodger Stadium': 0.98, 'Angel Stadium': 0.98,
    'T-Mobile Park': 0.95, 'Oracle Park': 0.93, 'Tropicana Field': 0.96,
    'Petco Park': 0.94, 'Target Field': 1.00, 'Progressive Field': 0.99,
    'PNC Park': 0.98, 'Truist Park': 1.01, 'Chase Field': 1.04,
    'American Family Field': 1.02, 'Rogers Centre': 1.02, 'Comerica Park': 0.96,
    'Oakland Coliseum': 0.94, 'loanDepot park': 0.97, 'Citi Field': 0.97,
}

# Outdoor stadiums (weather matters)
OUTDOOR_STADIUMS = {
    'Coors Field', 'Fenway Park', 'Wrigley Field', 'Yankee Stadium',
    'Citizens Bank Park', 'Nationals Park', 'Kauffman Stadium', 'Busch Stadium',
    'Dodger Stadium', 'Angel Stadium', 'Oracle Park', 'Petco Park',
    'Target Field', 'Progressive Field', 'PNC Park', 'Truist Park',
    'Camden Yards', 'Great American Ball Park', 'Comerica Park',
    'Guaranteed Rate Field', 'Citi Field', 'Oakland Coliseum',
}

# Team city coordinates for travel distance (lat, lon)
TEAM_LOCATIONS = {
    'Arizona Diamondbacks': (33.45, -112.07), 'Atlanta Braves': (33.89, -84.47),
    'Baltimore Orioles': (39.28, -76.62), 'Boston Red Sox': (42.35, -71.10),
    'Chicago Cubs': (41.95, -87.66), 'Chicago White Sox': (41.83, -87.63),
    'Cincinnati Reds': (39.10, -84.51), 'Cleveland Guardians': (41.50, -81.69),
    'Colorado Rockies': (39.76, -104.99), 'Detroit Tigers': (42.34, -83.05),
    'Houston Astros': (29.76, -95.36), 'Kansas City Royals': (39.05, -94.48),
    'Los Angeles Angels': (33.80, -117.88), 'Los Angeles Dodgers': (34.07, -118.24),
    'Miami Marlins': (25.78, -80.22), 'Milwaukee Brewers': (43.03, -87.97),
    'Minnesota Twins': (44.98, -93.28), 'New York Mets': (40.76, -73.85),
    'New York Yankees': (40.83, -73.93), 'Oakland Athletics': (37.75, -122.20),
    'Philadelphia Phillies': (39.91, -75.17), 'Pittsburgh Pirates': (40.45, -80.01),
    'San Diego Padres': (32.71, -117.16), 'San Francisco Giants': (37.78, -122.39),
    'Seattle Mariners': (47.59, -122.33), 'St. Louis Cardinals': (38.62, -90.19),
    'Tampa Bay Rays': (27.77, -82.65), 'Texas Rangers': (32.75, -97.08),
    'Toronto Blue Jays': (43.64, -79.39), 'Washington Nationals': (38.87, -77.01),
}

# Division mappings
DIVISIONS = {
    'AL East': ['New York Yankees', 'Baltimore Orioles', 'Tampa Bay Rays', 'Boston Red Sox', 'Toronto Blue Jays'],
    'AL Central': ['Cleveland Guardians', 'Minnesota Twins', 'Detroit Tigers', 'Chicago White Sox', 'Kansas City Royals'],
    'AL West': ['Houston Astros', 'Texas Rangers', 'Seattle Mariners', 'Los Angeles Angels', 'Oakland Athletics'],
    'NL East': ['Atlanta Braves', 'Philadelphia Phillies', 'New York Mets', 'Miami Marlins', 'Washington Nationals'],
    'NL Central': ['Milwaukee Brewers', 'St. Louis Cardinals', 'Chicago Cubs', 'Cincinnati Reds', 'Pittsburgh Pirates'],
    'NL West': ['Los Angeles Dodgers', 'San Diego Padres', 'Arizona Diamondbacks', 'San Francisco Giants', 'Colorado Rockies'],
}


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class MLBDataFetcher:
    """Fetches MLB data from ESPN + Odds API, caches in SQLite."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.db_path = DB_PATH
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._init_db()
        self.team_stats_cache: Dict[str, Dict] = {}

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_name TEXT, season TEXT,
                wins INT, losses INT, win_pct REAL,
                runs_scored REAL, runs_allowed REAL,
                batting_avg REAL, obp REAL, slg REAL, ops REAL,
                era REAL, whip REAL, team_so REAL,
                home_wins INT, home_losses INT, away_wins INT, away_losses INT,
                l10_wins INT, l10_losses INT, streak INT,
                conference TEXT, division TEXT,
                last_updated TEXT,
                PRIMARY KEY (team_name, season)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pitcher_stats (
                player_name TEXT, team TEXT, season TEXT,
                era REAL, whip REAL, k_per_9 REAL, bb_per_9 REAL,
                innings_pitched REAL, wins INT, losses INT,
                avg_against REAL, home_era REAL, away_era REAL,
                throws TEXT,
                last_updated TEXT,
                PRIMARY KEY (player_name, team, season)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS odds_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date TEXT, home_team TEXT, away_team TEXT,
                bookmaker TEXT, home_odds REAL, away_odds REAL,
                spread REAL, total REAL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_date, home_team, away_team, bookmaker, timestamp)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_results (
                game_id TEXT PRIMARY KEY, game_date TEXT,
                home_team TEXT, away_team TEXT,
                home_score INT, away_score INT,
                home_pitcher TEXT, away_pitcher TEXT
            )
        """)
        conn.commit()
        conn.close()

    # ─── Odds API ───────────────────────────────────────────────

    def fetch_games_from_odds(self, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch MLB games + odds from The Odds API."""
        url = f"{ODDS_API_BASE}/sports/baseball_mlb/odds"
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'american',
        }
        try:
            resp = self.session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            events = resp.json()
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"Odds API: {len(events)} MLB events (remaining: {remaining})")
        except Exception as e:
            logger.error(f"Odds API fetch failed: {e}")
            return []

        games = []
        target_str = (target_date or date.today()).isoformat()

        for ev in events:
            commence = ev.get('commence_time', '')
            # Filter to target date (EST)
            if commence:
                try:
                    utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    est_dt = utc_dt - timedelta(hours=5)
                    game_date_str = est_dt.date().isoformat()
                except Exception:
                    game_date_str = commence[:10]
            else:
                game_date_str = ''

            if target_date and game_date_str != target_str:
                continue

            home = ev.get('home_team', '')
            away = ev.get('away_team', '')

            h2h_home, h2h_away = None, None
            spread_home, spread_val = None, None
            total_val = None

            for bm in ev.get('bookmakers', []):
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'h2h':
                        for oc in mkt['outcomes']:
                            if oc['name'] == home:
                                h2h_home = oc.get('price')
                            elif oc['name'] == away:
                                h2h_away = oc.get('price')
                    elif mkt['key'] == 'spreads':
                        for oc in mkt['outcomes']:
                            if oc['name'] == home:
                                spread_home = oc.get('price')
                                spread_val = oc.get('point')
                    elif mkt['key'] == 'totals':
                        for oc in mkt['outcomes']:
                            if oc['name'] == 'Over':
                                total_val = oc.get('point')
                if h2h_home is not None:
                    break

            home_prob = self._american_to_prob(h2h_home)
            away_prob = self._american_to_prob(h2h_away)

            games.append({
                'game_id': ev.get('id', ''),
                'game_date': game_date_str,
                'game_time': commence,
                'home_team': home,
                'away_team': away,
                'home_odds': h2h_home,
                'away_odds': h2h_away,
                'home_implied_prob': home_prob,
                'away_implied_prob': away_prob,
                'spread': spread_val,
                'total': total_val,
            })

            self._store_odds(game_date_str, home, away, 'consensus',
                             h2h_home, h2h_away, spread_val, total_val)

        logger.info(f"Returning {len(games)} MLB games for {target_str}")
        return games

    def fetch_futures_odds(self) -> List[Dict]:
        """Fetch World Series futures from Odds API."""
        url = f"{ODDS_API_BASE}/sports/baseball_mlb_world_series_winner/odds"
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'oddsFormat': 'american',
        }
        try:
            resp = self.session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Futures odds fetch failed: {e}")
            return []

    # ─── ESPN API ───────────────────────────────────────────────

    def fetch_espn_scoreboard(self, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch games from ESPN MLB scoreboard."""
        target = target_date or date.today()
        params = {'dates': target.strftime('%Y%m%d')}
        try:
            resp = self.session.get(ESPN_MLB_SCOREBOARD, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"ESPN scoreboard fetch failed: {e}")
            return []

        games = []
        for ev in data.get('events', []):
            comp = ev.get('competitions', [{}])[0]
            teams_data = comp.get('competitors', [])
            if len(teams_data) < 2:
                continue

            home_data = next((t for t in teams_data if t.get('homeAway') == 'home'), teams_data[0])
            away_data = next((t for t in teams_data if t.get('homeAway') == 'away'), teams_data[1])

            home_team = home_data.get('team', {}).get('displayName', '')
            away_team = away_data.get('team', {}).get('displayName', '')
            venue = comp.get('venue', {}).get('fullName', '')

            # Extract probable pitchers
            home_pitcher = ''
            away_pitcher = ''
            for note in comp.get('notes', []):
                text = note.get('headline', '')
                if 'vs' in text.lower() or 'at' in text.lower():
                    # Sometimes pitcher info is in notes
                    pass

            # Try to get pitchers from broadcasts/status
            status = comp.get('status', {}).get('type', {}).get('name', '')

            games.append({
                'game_id': ev.get('id', ''),
                'game_date': target.isoformat(),
                'home_team': home_team,
                'away_team': away_team,
                'venue': venue,
                'status': status,
                'home_score': _safe_float(home_data.get('score', 0)),
                'away_score': _safe_float(away_data.get('score', 0)),
                'home_record': home_data.get('records', [{}])[0].get('summary', '') if home_data.get('records') else '',
                'away_record': away_data.get('records', [{}])[0].get('summary', '') if away_data.get('records') else '',
            })

        return games

    def fetch_team_stats(self) -> Dict[str, Dict]:
        """Fetch team standings/stats from ESPN."""
        try:
            resp = self.session.get(ESPN_MLB_STANDINGS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"ESPN standings fetch failed: {e}")
            return {}

        stats = {}
        for group in data.get('children', []):
            conf_name = group.get('name', '')
            for div_group in group.get('children', []):
                div_name = div_group.get('name', '')
                for entry in div_group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    s = {'team': name, 'conference': conf_name, 'division': div_name}

                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        sd = stat.get('displayValue', '')
                        if sn == 'wins': s['wins'] = int(_safe_float(sv))
                        elif sn == 'losses': s['losses'] = int(_safe_float(sv))
                        elif sn == 'winPercent': s['win_pct'] = _safe_float(sv)
                        elif sn == 'avgPointsFor': s['runs_scored'] = _safe_float(sv)
                        elif sn == 'avgPointsAgainst': s['runs_allowed'] = _safe_float(sv)
                        elif sn == 'streak': s['streak'] = int(_safe_float(sv))
                        elif sn == 'Home': s['home_record'] = sd
                        elif sn == 'Road': s['away_record'] = sd

                    gp = s.get('wins', 0) + s.get('losses', 0)
                    s['games_played'] = gp

                    # Parse home/away records
                    for key, w_key, l_key in [('home_record', 'home_wins', 'home_losses'),
                                               ('away_record', 'away_wins', 'away_losses')]:
                        rec = s.get(key, '0-0')
                        parts = rec.split('-')
                        if len(parts) == 2:
                            s[w_key] = int(_safe_float(parts[0]))
                            s[l_key] = int(_safe_float(parts[1]))

                    stats[name] = s

            # If no children (flat structure), try entries directly
            if not group.get('children'):
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    s = {'team': name, 'conference': conf_name}
                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        if sn == 'wins': s['wins'] = int(_safe_float(sv))
                        elif sn == 'losses': s['losses'] = int(_safe_float(sv))
                        elif sn == 'winPercent': s['win_pct'] = _safe_float(sv)
                        elif sn == 'avgPointsFor': s['runs_scored'] = _safe_float(sv)
                        elif sn == 'avgPointsAgainst': s['runs_allowed'] = _safe_float(sv)
                    s['games_played'] = s.get('wins', 0) + s.get('losses', 0)
                    stats[name] = s

        logger.info(f"Fetched stats for {len(stats)} MLB teams")
        self.team_stats_cache = stats
        return stats

    def fetch_espn_team_detail(self, team_name: str) -> Optional[Dict]:
        """Fetch detailed team stats from ESPN teams endpoint."""
        # Check cache
        if team_name in self.team_stats_cache:
            return self.team_stats_cache[team_name]

        # Check DB (< 6 hours old)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM team_stats WHERE team_name = ? AND last_updated > ?",
            (team_name, (datetime.now() - timedelta(hours=6)).isoformat())
        ).fetchone()
        conn.close()
        if row:
            return self._row_to_team_stats(row)

        return None

    def save_team_stats(self, stats: Dict):
        """Save team stats to DB."""
        season = str(date.today().year)
        conn = sqlite3.connect(self.db_path)
        for name, s in stats.items():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO team_stats 
                    (team_name, season, wins, losses, win_pct, runs_scored, runs_allowed,
                     batting_avg, obp, slg, ops, era, whip, team_so,
                     home_wins, home_losses, away_wins, away_losses,
                     l10_wins, l10_losses, streak, conference, division, last_updated)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    name, season,
                    s.get('wins', 0), s.get('losses', 0), s.get('win_pct', 0),
                    s.get('runs_scored', 0), s.get('runs_allowed', 0),
                    s.get('batting_avg', 0), s.get('obp', 0), s.get('slg', 0), s.get('ops', 0),
                    s.get('era', 0), s.get('whip', 0), s.get('team_so', 0),
                    s.get('home_wins', 0), s.get('home_losses', 0),
                    s.get('away_wins', 0), s.get('away_losses', 0),
                    s.get('l10_wins', 0), s.get('l10_losses', 0),
                    s.get('streak', 0), s.get('conference', ''), s.get('division', ''),
                    datetime.now().isoformat()
                ))
            except Exception as e:
                logger.warning(f"Failed to save stats for {name}: {e}")
        conn.commit()
        conn.close()

    def _row_to_team_stats(self, row) -> Dict:
        keys = ['team_name', 'season', 'wins', 'losses', 'win_pct',
                'runs_scored', 'runs_allowed', 'batting_avg', 'obp', 'slg', 'ops',
                'era', 'whip', 'team_so', 'home_wins', 'home_losses',
                'away_wins', 'away_losses', 'l10_wins', 'l10_losses',
                'streak', 'conference', 'division', 'last_updated']
        return dict(zip(keys, row))

    # ─── Utility ────────────────────────────────────────────────

    def _american_to_prob(self, odds) -> float:
        if odds is None:
            return 0.5
        odds = float(odds)
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    def _store_odds(self, game_date, home, away, bookmaker, home_odds, away_odds, spread, total):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR IGNORE INTO odds_history
                (game_date, home_team, away_team, bookmaker, home_odds, away_odds, spread, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_date, home, away, bookmaker, home_odds, away_odds, spread, total))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store odds: {e}")

    @staticmethod
    def get_park_factor(venue: str) -> float:
        return PARK_FACTORS.get(venue, 1.0)

    @staticmethod
    def is_outdoor(venue: str) -> bool:
        return venue in OUTDOOR_STADIUMS

    @staticmethod
    def is_division_rival(team_a: str, team_b: str) -> bool:
        for div, teams in DIVISIONS.items():
            if team_a in teams and team_b in teams:
                return True
        return False

    @staticmethod
    def calculate_travel_distance(team_a: str, team_b: str) -> float:
        """Approximate distance in miles between two team cities."""
        import math
        loc_a = TEAM_LOCATIONS.get(team_a)
        loc_b = TEAM_LOCATIONS.get(team_b)
        if not loc_a or not loc_b:
            return 0.0
        lat1, lon1 = math.radians(loc_a[0]), math.radians(loc_a[1])
        lat2, lon2 = math.radians(loc_b[0]), math.radians(loc_b[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return c * 3959  # Earth radius in miles
