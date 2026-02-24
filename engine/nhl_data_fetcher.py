"""
NHL Data Fetcher — ParlayGuarantee
Sources: ESPN NHL API, The Odds API
Caches data in SQLite for performance.
"""

import sys
import requests
import json
import time
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'nhl_data.db')
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'nhl_cache')
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_SPORT_KEY = "icehockey_nhl"

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
ESPN_STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# NHL Division/Conference strength tiers (2025-26 estimates)
DIVISION_STRENGTH = {
    'Atlantic': 0.82, 'Metropolitan': 0.85, 'Central': 0.80, 'Pacific': 0.78,
}
CONFERENCE_STRENGTH = {
    'Eastern': 0.83, 'Western': 0.79,
}

# Team name normalization map (Odds API name -> ESPN canonical)
TEAM_NAME_MAP = {
    'New York Rangers': 'New York Rangers',
    'New York Islanders': 'New York Islanders',
    'Los Angeles Kings': 'Los Angeles Kings',
    'LA Kings': 'Los Angeles Kings',
    'Vegas Golden Knights': 'Vegas Golden Knights',
    'Seattle Kraken': 'Seattle Kraken',
    'St Louis Blues': 'St. Louis Blues',
    'St. Louis Blues': 'St. Louis Blues',
    'Montreal Canadiens': 'Montréal Canadiens',
    'Montréal Canadiens': 'Montréal Canadiens',
    'Utah Hockey Club': 'Utah Hockey Club',
}


def init_db():
    """Initialize SQLite database with NHL tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS team_stats (
        team_name TEXT PRIMARY KEY,
        wins INT, losses INT, otl INT,
        points INT, points_pct REAL,
        goals_for INT, goals_against INT,
        goals_per_game REAL, goals_against_per_game REAL,
        pp_pct REAL, pk_pct REAL,
        shots_per_game REAL, shots_against_per_game REAL,
        faceoff_pct REAL,
        home_wins INT, home_losses INT, home_otl INT,
        away_wins INT, away_losses INT, away_otl INT,
        last10_wins INT, last10_losses INT, last10_otl INT,
        streak TEXT, streak_count INT,
        division TEXT, conference TEXT,
        games_played INT,
        last_updated TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS game_results (
        game_id TEXT PRIMARY KEY,
        game_date TEXT,
        home_team TEXT, away_team TEXT,
        home_score INT, away_score INT,
        overtime INT DEFAULT 0,
        shootout INT DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS odds_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date TEXT, home_team TEXT, away_team TEXT,
        bookmaker TEXT,
        home_odds REAL, away_odds REAL,
        spread REAL, total REAL,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(game_date, home_team, away_team, bookmaker, timestamp)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS team_schedule (
        team_name TEXT, game_date TEXT, opponent TEXT,
        home_away TEXT, result TEXT, score TEXT,
        PRIMARY KEY(team_name, game_date)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS injuries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT, player_name TEXT,
        position TEXT, status TEXT, detail TEXT,
        last_updated TEXT
    )""")
    conn.commit()
    conn.close()


class NHLDataFetcher:
    """Fetches NHL data from ESPN + Odds API with SQLite caching."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.db_path = DB_PATH
        os.makedirs(CACHE_DIR, exist_ok=True)
        init_db()
        self._team_stats_cache: Dict[str, Dict] = {}
        self._schedule_cache: Dict[str, List] = {}
        self._injuries_cache: Dict[str, List] = {}

    def normalize_team_name(self, name: str) -> str:
        """Normalize team names across sources."""
        return TEAM_NAME_MAP.get(name, name)

    # ─── Odds API ───────────────────────────────────────────────

    def fetch_games_from_odds(self, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch NHL games + odds from The Odds API."""
        url = f"https://api.the-odds-api.com/v4/sports/{ODDS_SPORT_KEY}/odds"
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
            logger.info(f"Odds API: {len(events)} NHL events (remaining: {remaining})")
        except Exception as e:
            logger.error(f"Odds API fetch failed: {e}")
            return []

        target = target_date or date.today()
        target_str = target.isoformat()
        games = []

        for ev in events:
            commence = ev.get('commence_time', '')
            # Parse UTC time, convert to EST for date matching
            try:
                utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                est_dt = utc_dt + timedelta(hours=-5)
                game_date_str = est_dt.date().isoformat()
            except:
                game_date_str = commence[:10] if commence else ''

            if game_date_str != target_str:
                continue

            home = self.normalize_team_name(ev.get('home_team', ''))
            away = self.normalize_team_name(ev.get('away_team', ''))

            # Extract odds from bookmakers
            h2h_home, h2h_away = None, None
            spread_home, spread_val = None, None
            total_val = None
            h2h_prices = []
            spread_vals = []
            total_vals = []

            for bm in ev.get('bookmakers', []):
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'h2h':
                        for oc in mkt['outcomes']:
                            if oc['name'] == ev.get('home_team', ''):
                                h2h_prices.append(('home', oc.get('price')))
                            elif oc['name'] == ev.get('away_team', ''):
                                h2h_prices.append(('away', oc.get('price')))
                    elif mkt['key'] == 'spreads':
                        for oc in mkt['outcomes']:
                            if oc['name'] == ev.get('home_team', ''):
                                spread_vals.append((oc.get('point'), oc.get('price')))
                    elif mkt['key'] == 'totals':
                        for oc in mkt['outcomes']:
                            if oc['name'] == 'Over':
                                total_vals.append(oc.get('point'))

            # Use first available
            for side, price in h2h_prices:
                if side == 'home' and h2h_home is None:
                    h2h_home = price
                elif side == 'away' and h2h_away is None:
                    h2h_away = price

            if spread_vals:
                spread_val = spread_vals[0][0]
                spread_home = spread_vals[0][1]

            if total_vals:
                total_val = sum(total_vals) / len(total_vals)

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
                'spread_price': spread_home,
                'total': total_val,
                'game_status': 'Scheduled',
            })

            # Store odds
            self._store_odds(game_date_str, home, away, 'consensus',
                             h2h_home, h2h_away, spread_val, total_val)

        logger.info(f"Found {len(games)} NHL games for {target_str}")
        return games

    def _american_to_prob(self, odds) -> float:
        if odds is None:
            return 0.5
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    def _store_odds(self, game_date, home, away, bookmaker, home_odds, away_odds, spread, total):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""INSERT OR IGNORE INTO odds_history
                (game_date, home_team, away_team, bookmaker, home_odds, away_odds, spread, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (game_date, home, away, bookmaker, home_odds, away_odds, spread, total))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store odds: {e}")

    # ─── ESPN Data ──────────────────────────────────────────────

    def fetch_standings(self) -> Dict[str, Dict]:
        """Fetch NHL standings from ESPN — primary source for team stats."""
        cache_file = os.path.join(CACHE_DIR, f"standings_{date.today().isoformat()}.json")
        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if (time.time() - mtime) < 3600 * 4:  # 4 hour cache
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self._team_stats_cache = json.load(f)
                    return self._team_stats_cache

        stats = {}
        try:
            resp = self.session.get(ESPN_STANDINGS_URL, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for group in data.get('children', []):
                conf_name = group.get('name', '').replace(' Conference', '')
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    name = self.normalize_team_name(name)

                    s = {
                        'team_name': name,
                        'division': '',
                        'conference': conf_name,
                        'team_id': team_info.get('id', ''),
                        'abbreviation': team_info.get('abbreviation', ''),
                    }

                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        sd = stat.get('displayValue', '')
                        try:
                            if sn == 'wins': s['wins'] = int(float(sv))
                            elif sn == 'losses': s['losses'] = int(float(sv))
                            elif sn in ('OTLosses', 'otLosses', 'overtimeLosses'): s['otl'] = int(float(sv))
                            elif sn == 'points': s['points'] = int(float(sv))
                            elif sn == 'pointPct': s['points_pct'] = float(sv)
                            elif sn == 'gamesPlayed': s['games_played'] = int(float(sv))
                            elif sn == 'pointsFor':
                                # In NHL standings, pointsFor = goals for
                                s['goals_for'] = int(float(sv))
                            elif sn == 'pointsAgainst':
                                s['goals_against'] = int(float(sv))
                            elif sn == 'goalsFor': s['goals_for'] = int(float(sv))
                            elif sn == 'goalsAgainst': s['goals_against'] = int(float(sv))
                            elif sn == 'avgGoalsFor': s['goals_per_game'] = float(sv)
                            elif sn == 'avgGoalsAgainst': s['goals_against_per_game'] = float(sv)
                            elif sn == 'powerPlayPct': s['pp_pct'] = float(sv)
                            elif sn == 'penaltyKillPct': s['pk_pct'] = float(sv)
                            elif sn in ('shotsFor', 'avgShotsFor'): s['shots_per_game'] = float(sv)
                            elif sn in ('shotsAgainst', 'avgShotsAgainst'): s['shots_against_per_game'] = float(sv)
                            elif sn == 'faceoffWinPct': s['faceoff_pct'] = float(sv)
                            elif sn == 'differential':
                                s['goal_diff_per_game'] = float(sv)
                            elif sn in ('pointDifferential', 'pointsDiff'):
                                s['point_differential'] = int(float(sv))
                            elif sn == 'streak':
                                s['streak'] = sd
                                s['streak_count'] = int(float(sv)) if sv else 0
                            elif sn in ('Home', 'home'):
                                parts = sd.split('-') if sd else []
                                if len(parts) >= 2:
                                    s['home_wins'] = int(parts[0])
                                    s['home_losses'] = int(parts[1])
                                    s['home_otl'] = int(parts[2]) if len(parts) > 2 else 0
                            elif sn in ('Road', 'road', 'Away', 'away'):
                                parts = sd.split('-') if sd else []
                                if len(parts) >= 2:
                                    s['away_wins'] = int(parts[0])
                                    s['away_losses'] = int(parts[1])
                                    s['away_otl'] = int(parts[2]) if len(parts) > 2 else 0
                            elif sn in ('L10', 'Last Ten', 'last10', 'Last Ten Games'):
                                # Format: "8-1-1, 0 PTS"
                                record_part = sd.split(',')[0] if sd else sd
                                parts = record_part.split('-') if record_part else []
                                if len(parts) >= 2:
                                    s['last10_wins'] = int(parts[0])
                                    s['last10_losses'] = int(parts[1])
                                    s['last10_otl'] = int(parts[2]) if len(parts) > 2 else 0
                        except (ValueError, TypeError):
                            pass

                    # Compute derived stats
                    gp = s.get('games_played', s.get('wins', 0) + s.get('losses', 0) + s.get('otl', 0))
                    if gp == 0:
                        continue
                    s['games_played'] = gp

                    if 'goals_per_game' not in s and 'goals_for' in s:
                        s['goals_per_game'] = round(s['goals_for'] / gp, 2)
                    if 'goals_against_per_game' not in s and 'goals_against' in s:
                        s['goals_against_per_game'] = round(s['goals_against'] / gp, 2)

                    # Estimate save % from goals against and shots against
                    sapg = s.get('shots_against_per_game', 30.0)
                    gapg = s.get('goals_against_per_game', 3.0)
                    if sapg > 0:
                        s['save_pct'] = round(1 - (gapg / sapg), 4)
                    else:
                        s['save_pct'] = 0.900

                    # Estimate shooting %
                    spg = s.get('shots_per_game', 30.0)
                    gpg = s.get('goals_per_game', 3.0)
                    if spg > 0:
                        s['shooting_pct'] = round(gpg / spg, 4)
                    else:
                        s['shooting_pct'] = 0.100

                    # Win percentage
                    total_decisions = s.get('wins', 0) + s.get('losses', 0)
                    s['win_pct'] = s['wins'] / max(total_decisions, 1)

                    # Points percentage
                    if 'points_pct' not in s:
                        possible = gp * 2
                        s['points_pct'] = s.get('points', 0) / max(possible, 1)

                    stats[name] = s
                    self._save_team_stats(s)

            logger.info(f"Fetched standings for {len(stats)} NHL teams")
        except Exception as e:
            logger.error(f"ESPN standings error: {e}")
            # Try loading from DB
            stats = self._load_all_stats_from_db()

        if stats:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False)
        self._team_stats_cache = stats
        return stats

    def get_team_stats(self, team_name: str) -> Optional[Dict]:
        """Get stats for a single team."""
        if not self._team_stats_cache:
            self.fetch_standings()
        name = self.normalize_team_name(team_name)
        # Try exact match first
        if name in self._team_stats_cache:
            return self._team_stats_cache[name]
        # Fuzzy match
        name_lower = name.lower()
        for key, val in self._team_stats_cache.items():
            if name_lower in key.lower() or key.lower() in name_lower:
                return val
        return None

    def fetch_scoreboard(self, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch games from ESPN scoreboard."""
        td = target_date or date.today()
        dt_str = td.strftime('%Y%m%d')
        url = f"{ESPN_BASE}/scoreboard?dates={dt_str}"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            games = []
            for event in data.get('events', []):
                comp = event.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])
                if len(competitors) < 2:
                    continue
                home_data = away_data = None
                for c in competitors:
                    if c.get('homeAway') == 'home':
                        home_data = c
                    else:
                        away_data = c
                if not home_data or not away_data:
                    continue
                games.append({
                    'game_id': event.get('id', ''),
                    'home_team': self.normalize_team_name(home_data['team'].get('displayName', '')),
                    'away_team': self.normalize_team_name(away_data['team'].get('displayName', '')),
                    'home_score': int(home_data.get('score', 0)),
                    'away_score': int(away_data.get('score', 0)),
                    'status': event.get('status', {}).get('type', {}).get('name', ''),
                    'game_date': td.isoformat(),
                })
            return games
        except Exception as e:
            logger.error(f"ESPN scoreboard error: {e}")
            return []

    def fetch_team_schedule(self, team_name: str, limit: int = 15) -> List[Dict]:
        """Fetch recent games for a team from ESPN."""
        stats = self.get_team_stats(team_name)
        if not stats or not stats.get('team_id'):
            return []

        team_id = stats['team_id']
        url = f"{ESPN_BASE}/teams/{team_id}/schedule"
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            games = []
            for event in data.get('events', []):
                comp = event.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])
                if len(competitors) < 2:
                    continue
                home_data = away_data = None
                for c in competitors:
                    if c.get('homeAway') == 'home':
                        home_data = c
                    else:
                        away_data = c
                if not home_data or not away_data:
                    continue

                status = event.get('status', {}).get('type', {}).get('name', '')
                if status != 'STATUS_FINAL':
                    continue

                game_date = event.get('date', '')[:10]
                home_name = self.normalize_team_name(home_data['team'].get('displayName', ''))
                away_name = self.normalize_team_name(away_data['team'].get('displayName', ''))

                games.append({
                    'game_date': game_date,
                    'home_team': home_name,
                    'away_team': away_name,
                    'home_score': int(home_data.get('score', 0)),
                    'away_score': int(away_data.get('score', 0)),
                })

            # Return most recent games
            games.sort(key=lambda g: g['game_date'], reverse=True)
            return games[:limit]
        except Exception as e:
            logger.error(f"Schedule fetch error for {team_name}: {e}")
            return []

    def fetch_injuries(self) -> Dict[str, List[Dict]]:
        """Fetch NHL injuries from ESPN."""
        if self._injuries_cache:
            return self._injuries_cache

        try:
            # ESPN injuries endpoint
            url = f"{ESPN_BASE}/injuries"
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"ESPN injuries returned {resp.status_code}")
                return {}

            data = resp.json()
            injuries = {}
            for team_data in data.get('injuries', data.get('teams', [])):
                team_name = ''
                if 'team' in team_data:
                    team_name = self.normalize_team_name(
                        team_data['team'].get('displayName', ''))
                elif 'displayName' in team_data:
                    team_name = self.normalize_team_name(team_data['displayName'])

                if not team_name:
                    continue

                team_injuries = []
                for inj in team_data.get('injuries', []):
                    player = inj.get('athlete', {})
                    team_injuries.append({
                        'player': player.get('displayName', ''),
                        'position': player.get('position', {}).get('abbreviation', ''),
                        'status': inj.get('status', ''),
                        'detail': inj.get('details', {}).get('detail', ''),
                    })
                if team_injuries:
                    injuries[team_name] = team_injuries

            self._injuries_cache = injuries
            logger.info(f"Fetched injuries for {len(injuries)} NHL teams")
            return injuries
        except Exception as e:
            logger.error(f"Injuries fetch error: {e}")
            return {}

    def get_team_injury_impact(self, team_name: str) -> float:
        """
        Estimate injury impact for a team (0 = healthy, negative = hurt).
        Goalie injuries are most impactful in NHL.
        """
        injuries = self.fetch_injuries()
        team_inj = injuries.get(self.normalize_team_name(team_name), [])
        if not team_inj:
            return 0.0

        impact = 0.0
        for inj in team_inj:
            status = inj.get('status', '').lower()
            pos = inj.get('position', '').upper()

            if 'out' in status or 'injured reserve' in status.lower():
                if pos == 'G':
                    impact -= 0.08  # Goalie out is huge
                elif pos in ('C', 'LW', 'RW'):
                    impact -= 0.025
                elif pos == 'D':
                    impact -= 0.02
                else:
                    impact -= 0.015
            elif 'day-to-day' in status or 'questionable' in status.lower():
                if pos == 'G':
                    impact -= 0.04
                else:
                    impact -= 0.01

        return max(-0.20, impact)  # Cap at -20%

    def detect_back_to_back(self, team_name: str, game_date: date) -> bool:
        """Check if team played yesterday (back-to-back)."""
        yesterday = (game_date - timedelta(days=1)).isoformat()
        schedule = self.fetch_team_schedule(team_name, limit=5)
        for g in schedule:
            if g['game_date'] == yesterday:
                return True
        # Also check ESPN scoreboard for yesterday
        yesterday_games = self.fetch_scoreboard(game_date - timedelta(days=1))
        for g in yesterday_games:
            if team_name in (g['home_team'], g['away_team']):
                return True
        return False

    def get_rest_days(self, team_name: str, game_date: date) -> int:
        """Get number of rest days before this game."""
        schedule = self.fetch_team_schedule(team_name, limit=5)
        for g in schedule:
            try:
                gd = date.fromisoformat(g['game_date'])
                if gd < game_date:
                    return (game_date - gd).days
            except:
                pass
        return 2  # default assumption

    def get_line_movement(self, home_team: str, away_team: str, game_date: str) -> Dict:
        """Check for line movement by comparing stored odds over time."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT home_odds, away_odds, spread, total, timestamp
            FROM odds_history
            WHERE game_date = ? AND home_team = ? AND away_team = ?
            ORDER BY timestamp
        """, (game_date, home_team, away_team)).fetchall()
        conn.close()

        if len(rows) < 2:
            return {'movement': 0, 'sharp': False}

        first = rows[0]
        last = rows[-1]
        h_move = (last[0] or 0) - (first[0] or 0)
        spread_move = (last[2] or 0) - (first[2] or 0)
        total_move = (last[3] or 0) - (first[3] or 0)

        return {
            'movement': h_move,
            'spread_move': spread_move,
            'total_move': total_move,
            'sharp': abs(h_move) > 20 or abs(spread_move) > 0.5,
        }

    def is_divisional_game(self, home_team: str, away_team: str) -> bool:
        """Check if two teams are in the same division."""
        h = self.get_team_stats(home_team)
        a = self.get_team_stats(away_team)
        if h and a:
            return h.get('division', '') == a.get('division', '') and h.get('division', '') != ''
        return False

    def is_conference_game(self, home_team: str, away_team: str) -> bool:
        """Check if two teams are in the same conference."""
        h = self.get_team_stats(home_team)
        a = self.get_team_stats(away_team)
        if h and a:
            return h.get('conference', '') == a.get('conference', '') and h.get('conference', '') != ''
        return False

    # ─── DB helpers ─────────────────────────────────────────────

    def _save_team_stats(self, s: Dict):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""INSERT OR REPLACE INTO team_stats
                (team_name, wins, losses, otl, points, points_pct,
                 goals_for, goals_against, goals_per_game, goals_against_per_game,
                 pp_pct, pk_pct, shots_per_game, shots_against_per_game, faceoff_pct,
                 home_wins, home_losses, home_otl,
                 away_wins, away_losses, away_otl,
                 last10_wins, last10_losses, last10_otl,
                 streak, streak_count, division, conference, games_played, last_updated)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s.get('team_name'), s.get('wins', 0), s.get('losses', 0), s.get('otl', 0),
                 s.get('points', 0), s.get('points_pct', 0),
                 s.get('goals_for', 0), s.get('goals_against', 0),
                 s.get('goals_per_game', 0), s.get('goals_against_per_game', 0),
                 s.get('pp_pct', 0), s.get('pk_pct', 0),
                 s.get('shots_per_game', 0), s.get('shots_against_per_game', 0),
                 s.get('faceoff_pct', 0),
                 s.get('home_wins', 0), s.get('home_losses', 0), s.get('home_otl', 0),
                 s.get('away_wins', 0), s.get('away_losses', 0), s.get('away_otl', 0),
                 s.get('last10_wins', 0), s.get('last10_losses', 0), s.get('last10_otl', 0),
                 s.get('streak', ''), s.get('streak_count', 0),
                 s.get('division', ''), s.get('conference', ''),
                 s.get('games_played', 0), datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to save team stats: {e}")

    def _load_all_stats_from_db(self) -> Dict[str, Dict]:
        """Load all team stats from DB as fallback."""
        stats = {}
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT * FROM team_stats").fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM team_stats LIMIT 0").description]
            conn.close()
            for row in rows:
                d = dict(zip(cols, row))
                stats[d['team_name']] = d
        except:
            pass
        return stats
