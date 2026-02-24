"""
NCAAB Data Fetcher — College Basketball Stats for ParlayGuarantee
Sources: ESPN, Odds API, cached rankings
"""

import requests
import json
import time
import logging
import os
import re
import sqlite3
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'ncaab_data.db')
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'ncaab_cache')
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Conference strength tiers (updated yearly — these are 2025-26 estimates)
CONFERENCE_STRENGTH = {
    # Power conferences
    'Big 12': 0.92, 'SEC': 0.91, 'Big Ten': 0.90, 'ACC': 0.85,
    'Big East': 0.84,
    # Upper mid-majors
    'Mountain West': 0.72, 'American Athletic': 0.70, 'Atlantic 10': 0.68,
    'West Coast': 0.66, 'Missouri Valley': 0.65, 'Colonial Athletic': 0.60,
    # Mid-majors
    'Conference USA': 0.58, 'Sun Belt': 0.57, 'MAC': 0.56,
    'Horizon League': 0.55, 'Southern': 0.55, 'WAC': 0.54,
    'Ohio Valley': 0.52, 'Summit League': 0.52, 'Patriot League': 0.51,
    'Ivy League': 0.54, 'MAAC': 0.50, 'Big Sky': 0.50,
    'Southland': 0.48, 'Big South': 0.48, 'Northeast': 0.45,
    'America East': 0.49, 'Atlantic Sun': 0.48, 'Big West': 0.53,
    'Coastal Athletic': 0.47, 'MEAC': 0.40, 'SWAC': 0.40,
}

# March Madness seed upset history (lower seed win % by matchup)
SEED_UPSET_HISTORY = {
    (1, 16): 0.01, (2, 15): 0.06, (3, 14): 0.15, (4, 13): 0.21,
    (5, 12): 0.36, (6, 11): 0.37, (7, 10): 0.39, (8, 9): 0.49,
    (1, 8): 0.20, (1, 9): 0.17, (2, 7): 0.25, (2, 10): 0.20,
    (3, 6): 0.35, (3, 11): 0.25, (4, 5): 0.44, (4, 12): 0.30,
}


class NCAABDataFetcher:
    """
    Fetches NCAAB data from multiple sources:
    1. Odds API (games + lines)
    2. ESPN (team stats, rankings, schedules)
    3. Local cache/DB
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.db_path = DB_PATH
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._init_db()
        self.team_stats_cache: Dict[str, Dict] = {}
        self.rankings_cache: List[Dict] = []
        self._team_id_map: Dict[str, Tuple[str, str]] = {}  # name -> (id, display_name)
        self._team_id_map_loaded = False

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_name TEXT, season TEXT, 
                wins INT, losses INT, 
                off_efficiency REAL, def_efficiency REAL, tempo REAL,
                fg_pct REAL, three_pct REAL, ft_pct REAL,
                rebounds REAL, turnovers REAL, assists REAL,
                sos REAL, conference TEXT, net_ranking INT,
                home_wins INT, home_losses INT, away_wins INT, away_losses INT,
                last_updated TEXT,
                PRIMARY KEY (team_name, season)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_results (
                game_id TEXT PRIMARY KEY, game_date TEXT,
                home_team TEXT, away_team TEXT,
                home_score INT, away_score INT,
                neutral_site INT DEFAULT 0, tournament INT DEFAULT 0,
                home_spread REAL, total REAL
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
            CREATE TABLE IF NOT EXISTS ncaab_odds_by_book (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                game_date TEXT,
                home_team TEXT,
                away_team TEXT,
                bookmaker TEXT,
                market TEXT,
                home_value REAL,
                away_value REAL,
                home_point REAL,
                away_point REAL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_id, bookmaker, market, timestamp)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_odds_by_book_date_game ON ncaab_odds_by_book(game_date, game_id)")
        conn.commit()
        conn.close()

    # ─── Odds API ───────────────────────────────────────────────

    def fetch_games_from_odds(self, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch NCAAB games + odds from The Odds API."""
        url = f"https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
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
            logger.info(f"Odds API: {len(events)} NCAAB events (requests remaining: {remaining})")
        except Exception as e:
            logger.error(f"Odds API fetch failed: {e}")
            return []

        games = []
        target_str = (target_date or date.today()).isoformat()

        for ev in events:
            commence = ev.get('commence_time', '')
            game_date_str = commence[:10] if commence else ''

            # Filter to target date if specified
            if target_date and game_date_str != target_str:
                try:
                    game_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    target_start = datetime.fromisoformat(f"{target_str}T00:00:00+00:00")
                    target_end = target_start + timedelta(hours=30)
                    if not (target_start <= game_dt <= target_end):
                        continue
                except:
                    continue

            home = ev.get('home_team', '')
            away = ev.get('away_team', '')
            game_id = ev.get('id', '')

            # Determine which sportsbooks carry this game
            from odds_fetcher import normalize_bookmaker_name
            available_books = []
            for bm in ev.get('bookmakers', []):
                display = normalize_bookmaker_name(bm.get('key', ''), bm.get('title', ''))
                if display not in available_books:
                    available_books.append(display)
            available_books.sort()

            # Store ALL per-bookmaker odds
            self._store_all_bookmaker_odds(ev, game_date_str)

            # Compute best available lines across all books
            best_h2h_home, best_h2h_away = None, None
            best_spread_val, best_spread_price = None, None
            best_total_val = None

            for bm in ev.get('bookmakers', []):
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'h2h':
                        for oc in mkt['outcomes']:
                            if oc['name'] == home:
                                price = oc.get('price')
                                if price is not None and (best_h2h_home is None or price > best_h2h_home):
                                    best_h2h_home = price
                            elif oc['name'] == away:
                                price = oc.get('price')
                                if price is not None and (best_h2h_away is None or price > best_h2h_away):
                                    best_h2h_away = price
                    elif mkt['key'] == 'spreads':
                        for oc in mkt['outcomes']:
                            if oc['name'] == home:
                                point = oc.get('point')
                                price = oc.get('price')
                                # Best spread = highest point value for home (most points given)
                                if point is not None and (best_spread_val is None or point > best_spread_val):
                                    best_spread_val = point
                                    best_spread_price = price
                    elif mkt['key'] == 'totals':
                        for oc in mkt['outcomes']:
                            if oc['name'] == 'Over':
                                point = oc.get('point')
                                if point is not None:
                                    # Use median-ish: just take first if none yet, otherwise keep lowest (conservative)
                                    if best_total_val is None:
                                        best_total_val = point
                                    else:
                                        best_total_val = min(best_total_val, point)

            # Convert American odds to implied probability
            home_prob = self._american_to_prob(best_h2h_home) if best_h2h_home else 0.5
            away_prob = self._american_to_prob(best_h2h_away) if best_h2h_away else 0.5

            games.append({
                'game_id': game_id,
                'game_date': game_date_str,
                'game_time': commence,
                'home_team': home,
                'away_team': away,
                'home_odds': best_h2h_home,
                'away_odds': best_h2h_away,
                'home_implied_prob': home_prob,
                'away_implied_prob': away_prob,
                'spread': best_spread_val,
                'total': best_total_val,
                'game_status': 'Scheduled',
                'available_books': available_books,
            })

            # Store consensus odds
            self._store_odds(game_date_str, home, away, 'consensus', best_h2h_home, best_h2h_away, best_spread_val, best_total_val)

        logger.info(f"Returning {len(games)} NCAAB games for {target_str}")
        return games

    def _american_to_prob(self, odds: float) -> float:
        if odds is None:
            return 0.5
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    def _store_odds(self, game_date, home, away, bookmaker, home_odds, away_odds, spread, total):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR IGNORE INTO odds_history (game_date, home_team, away_team, bookmaker, home_odds, away_odds, spread, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_date, home, away, bookmaker, home_odds, away_odds, spread, total))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store odds: {e}")

    def _store_all_bookmaker_odds(self, event: Dict, game_date_str: str):
        """Store every bookmaker × market combination from a raw Odds API event."""
        game_id = event.get('id', '')
        home = event.get('home_team', '')
        away = event.get('away_team', '')
        rows = []

        for bm in event.get('bookmakers', []):
            bm_name = bm.get('key', bm.get('title', 'unknown'))
            for mkt in bm.get('markets', []):
                market_key = mkt['key']
                home_value, away_value, home_point, away_point = None, None, None, None

                if market_key == 'h2h':
                    for oc in mkt['outcomes']:
                        if oc['name'] == home:
                            home_value = oc.get('price')
                        elif oc['name'] == away:
                            away_value = oc.get('price')
                elif market_key == 'spreads':
                    for oc in mkt['outcomes']:
                        if oc['name'] == home:
                            home_value = oc.get('price')
                            home_point = oc.get('point')
                        elif oc['name'] == away:
                            away_value = oc.get('price')
                            away_point = oc.get('point')
                elif market_key == 'totals':
                    for oc in mkt['outcomes']:
                        if oc['name'] == 'Over':
                            home_value = oc.get('price')
                            home_point = oc.get('point')
                        elif oc['name'] == 'Under':
                            away_value = oc.get('price')
                            away_point = oc.get('point')

                rows.append((game_id, game_date_str, home, away, bm_name, market_key,
                             home_value, away_value, home_point, away_point))

        if rows:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.executemany("""
                    INSERT OR IGNORE INTO ncaab_odds_by_book
                    (game_id, game_date, home_team, away_team, bookmaker, market,
                     home_value, away_value, home_point, away_point)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to store per-book odds: {e}")

    def get_odds_by_book(self, game_date: str, home_team: Optional[str] = None) -> List[Dict]:
        """Return per-bookmaker odds for a given date, optionally filtered by home team."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if home_team:
            rows = conn.execute(
                "SELECT * FROM ncaab_odds_by_book WHERE game_date = ? AND home_team LIKE ? ORDER BY bookmaker, market",
                (game_date, f"%{home_team}%")
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ncaab_odds_by_book WHERE game_date = ? ORDER BY game_id, bookmaker, market",
                (game_date,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_best_line(self, game_date: str, home_team: str, away_team: str, market: str = 'spreads') -> Optional[Dict]:
        """Find the best available line across all books for a specific game and market."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM ncaab_odds_by_book
            WHERE game_date = ? AND home_team LIKE ? AND away_team LIKE ? AND market = ?
            ORDER BY timestamp DESC
        """, (game_date, f"%{home_team}%", f"%{away_team}%", market)).fetchall()
        conn.close()

        if not rows:
            return None

        # Dedupe to latest per bookmaker
        latest = {}
        for r in rows:
            bm = r['bookmaker']
            if bm not in latest:
                latest[bm] = dict(r)

        books = list(latest.values())
        if market == 'h2h':
            # Best ML = highest home_value (best payout for home), highest away_value for away
            best_home = max(books, key=lambda x: x['home_value'] or -9999)
            best_away = max(books, key=lambda x: x['away_value'] or -9999)
            return {'best_home_ml': best_home, 'best_away_ml': best_away, 'all_books': books}
        elif market == 'spreads':
            # Best spread for home = highest home_point (most points)
            best = max(books, key=lambda x: x['home_point'] or -9999)
            return {'best_spread': best, 'all_books': books}
        elif market == 'totals':
            # Return both lowest and highest total available
            lowest = min(books, key=lambda x: x['home_point'] or 9999)
            highest = max(books, key=lambda x: x['home_point'] or -9999)
            return {'lowest_total': lowest, 'highest_total': highest, 'all_books': books}

    # ─── ESPN Scraping ──────────────────────────────────────────

    def fetch_espn_rankings(self) -> List[Dict]:
        """Fetch AP Top 25 + NET rankings from ESPN."""
        cache_file = os.path.join(CACHE_DIR, f"rankings_{date.today().isoformat()}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                self.rankings_cache = json.load(f)
                return self.rankings_cache

        rankings = []
        try:
            # AP Poll
            resp = self.session.get("https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/rankings", timeout=15)
            data = resp.json()
            for poll in data.get('rankings', []):
                poll_name = poll.get('name', '')
                if 'AP' in poll_name or 'Coaches' in poll_name:
                    for entry in poll.get('ranks', []):
                        team_data = entry.get('team', {})
                        rankings.append({
                            'rank': entry.get('current', 99),
                            'team': team_data.get('location', '') or team_data.get('name', ''),
                            'team_id': team_data.get('id'),
                            'record': entry.get('recordSummary', ''),
                            'poll': poll_name,
                        })
                    break  # Use first poll found
        except Exception as e:
            logger.warning(f"ESPN rankings fetch failed: {e}")

        if rankings:
            with open(cache_file, 'w') as f:
                json.dump(rankings, f)
        self.rankings_cache = rankings
        return rankings

    def fetch_espn_team_stats(self, team_name: str) -> Optional[Dict]:
        """Fetch team stats from ESPN API."""
        if team_name in self.team_stats_cache:
            return self.team_stats_cache[team_name]

        # Check DB cache (< 6 hours old)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM team_stats WHERE team_name = ? AND last_updated > ?",
            (team_name, (datetime.now() - timedelta(hours=6)).isoformat())
        ).fetchone()
        conn.close()

        if row:
            stats = self._row_to_stats(row)
            self.team_stats_cache[team_name] = stats
            return stats

        # Fetch from ESPN scoreboard API (team search)
        stats = self._scrape_espn_team(team_name)
        if stats:
            self.team_stats_cache[team_name] = stats
            self._save_team_stats(stats)
        return stats

    def _load_team_id_map(self):
        """Load full ESPN team ID map once, cache to disk."""
        if self._team_id_map_loaded:
            return
        cache_file = os.path.join(CACHE_DIR, "espn_team_ids.json")
        if os.path.exists(cache_file):
            mtime = os.path.getmtime(cache_file)
            if (time.time() - mtime) < 86400 * 7:  # 7 day cache
                with open(cache_file) as f:
                    self._team_id_map = json.load(f)
                self._team_id_map_loaded = True
                return
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams"
            resp = self.session.get(url, params={'limit': 400}, timeout=45)
            all_teams = resp.json().get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
            for t in all_teams:
                ti = t.get('team', {})
                tid = ti.get('id', '')
                display = ti.get('displayName', '')
                loc = ti.get('location', '')
                abbr = ti.get('abbreviation', '')
                # Index by multiple keys
                for key in [display.lower(), loc.lower(), abbr.lower()]:
                    if key:
                        self._team_id_map[key] = {'id': tid, 'name': display}
            with open(cache_file, 'w') as f:
                json.dump(self._team_id_map, f)
            logger.info(f"Loaded {len(all_teams)} ESPN teams")
        except Exception as e:
            logger.warning(f"Failed to load ESPN team map: {e}")
        self._team_id_map_loaded = True

    def _find_team_id(self, team_name: str) -> Tuple[Optional[str], str]:
        """Find ESPN team ID from name. Returns (id, display_name)."""
        self._load_team_id_map()
        tn = team_name.lower()
        # Exact match
        if tn in self._team_id_map:
            m = self._team_id_map[tn]
            return m['id'], m['name']
        # Substring match
        for key, val in self._team_id_map.items():
            if tn in key or key in tn:
                return val['id'], val['name']
        return None, team_name

    def _scrape_espn_team(self, team_name: str) -> Optional[Dict]:
        """Scrape team stats from ESPN college basketball."""
        try:
            # Use cached team ID map (loaded once, cached 7 days)
            team_id, team_full_name = self._find_team_id(team_name)

            if not team_id:
                logger.debug(f"Team not found on ESPN: {team_name}")
                return None

            # Fetch team stats
            stats_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}/statistics"
            resp = self.session.get(stats_url, timeout=15)
            stats_data = resp.json()
            time.sleep(0.5)

            # Fetch team record
            record_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/{team_id}"
            resp2 = self.session.get(record_url, timeout=15)
            record_data = resp2.json()
            time.sleep(0.3)

            # Parse stats
            stat_map = {}
            for cat in stats_data.get('results', {}).get('stats', {}).get('categories', []):
                for stat in cat.get('stats', []):
                    stat_map[stat.get('name', '')] = stat.get('value', 0)

            # Parse record
            team_rec = record_data.get('team', {})
            record = team_rec.get('record', {}).get('items', [{}])
            overall = record[0] if record else {}
            overall_stats = {s['name']: s['value'] for s in overall.get('stats', [])} if overall else {}

            wins = int(overall_stats.get('wins', 0))
            losses = int(overall_stats.get('losses', 0))

            # Conference info
            groups = team_rec.get('groups', {})
            conference = ''
            if groups and groups.get('parent'):
                conference = groups['parent'].get('name', '')

            # Compute efficiency metrics (points per possession approximation)
            ppg = stat_map.get('avgPoints', 70)
            opp_ppg = stat_map.get('avgPointsAgainst', stat_map.get('opponentPointsPerGame', 70))
            possessions_est = stat_map.get('avgFieldGoalsAttempted', 60) + \
                            0.44 * stat_map.get('avgFreeThrowsAttempted', 15) - \
                            stat_map.get('avgOffensiveRebounds', 10) + \
                            stat_map.get('avgTurnovers', 13)
            tempo = max(possessions_est, 55)
            off_eff = (ppg / tempo * 100) if tempo > 0 else 100
            def_eff = (opp_ppg / tempo * 100) if tempo > 0 else 100

            return {
                'team_name': team_full_name,
                'season': '2025-26',
                'wins': wins,
                'losses': losses,
                'off_efficiency': round(off_eff, 2),
                'def_efficiency': round(def_eff, 2),
                'tempo': round(tempo, 1),
                'fg_pct': stat_map.get('fieldGoalPct', 0.44),
                'three_pct': stat_map.get('threePointFieldGoalPct', 0.33),
                'ft_pct': stat_map.get('freeThrowPct', 0.70),
                'rebounds': stat_map.get('avgRebounds', 35),
                'turnovers': stat_map.get('avgTurnovers', 13),
                'assists': stat_map.get('avgAssists', 13),
                'sos': 0.5,  # Will be computed from conference
                'conference': conference,
                'net_ranking': 0,  # Will be filled from rankings
                'ppg': ppg,
                'opp_ppg': opp_ppg,
            }
        except Exception as e:
            logger.warning(f"ESPN scrape failed for {team_name}: {e}")
            return None

    def _save_team_stats(self, stats: Dict):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO team_stats
                (team_name, season, wins, losses, off_efficiency, def_efficiency, tempo,
                 fg_pct, three_pct, ft_pct, rebounds, turnovers, assists,
                 sos, conference, net_ranking, home_wins, home_losses, away_wins, away_losses, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?)
            """, (
                stats['team_name'], stats.get('season', '2025-26'),
                stats['wins'], stats['losses'],
                stats['off_efficiency'], stats['def_efficiency'], stats['tempo'],
                stats['fg_pct'], stats['three_pct'], stats['ft_pct'],
                stats['rebounds'], stats['turnovers'], stats['assists'],
                stats['sos'], stats['conference'], stats.get('net_ranking', 0),
                datetime.now().isoformat(),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to save team stats: {e}")

    def _row_to_stats(self, row) -> Dict:
        return {
            'team_name': row[0], 'season': row[1],
            'wins': row[2], 'losses': row[3],
            'off_efficiency': row[4], 'def_efficiency': row[5], 'tempo': row[6],
            'fg_pct': row[7], 'three_pct': row[8], 'ft_pct': row[9],
            'rebounds': row[10], 'turnovers': row[11], 'assists': row[12],
            'sos': row[13], 'conference': row[14], 'net_ranking': row[15],
        }

    def fetch_team_schedule(self, team_name: str, last_n: int = 10) -> List[Dict]:
        """Fetch recent game results for a team from ESPN."""
        # This would ideally use ESPN's schedule API
        # For now, return from our DB
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT * FROM game_results 
            WHERE (home_team LIKE ? OR away_team LIKE ?)
            ORDER BY game_date DESC LIMIT ?
        """, (f"%{team_name}%", f"%{team_name}%", last_n)).fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                'game_id': row[0], 'game_date': row[1],
                'home_team': row[2], 'away_team': row[3],
                'home_score': row[4], 'away_score': row[5],
            })
        return results

    def get_conference_strength(self, conference: str) -> float:
        """Return conference strength rating 0-1."""
        return CONFERENCE_STRENGTH.get(conference, 0.50)

    def get_seed_upset_rate(self, high_seed: int, low_seed: int) -> float:
        """Get historical upset rate for seed matchup (lower seed winning)."""
        key = (min(high_seed, low_seed), max(high_seed, low_seed))
        return SEED_UPSET_HISTORY.get(key, 0.35)

    def store_game_result(self, game: Dict):
        """Store a completed game result."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO game_results
                (game_id, game_date, home_team, away_team, home_score, away_score,
                 neutral_site, tournament, home_spread, total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game.get('game_id', ''), game.get('game_date', ''),
                game['home_team'], game['away_team'],
                game.get('home_score'), game.get('away_score'),
                game.get('neutral_site', 0), game.get('tournament', 0),
                game.get('spread'), game.get('total'),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store game result: {e}")

    def get_h2h_history(self, team1: str, team2: str, seasons: int = 3) -> Dict:
        """Get head-to-head history between two teams."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT * FROM game_results
            WHERE (home_team LIKE ? AND away_team LIKE ?)
               OR (home_team LIKE ? AND away_team LIKE ?)
            ORDER BY game_date DESC LIMIT 20
        """, (f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%")).fetchall()
        conn.close()

        t1_wins, t2_wins = 0, 0
        for row in rows:
            home, away, hs, aws = row[2], row[3], row[4], row[5]
            if hs and aws:
                winner = home if hs > aws else away
                if team1.lower() in winner.lower():
                    t1_wins += 1
                else:
                    t2_wins += 1

        return {'team1_wins': t1_wins, 'team2_wins': t2_wins, 'total': t1_wins + t2_wins}

    def get_ats_trends(self, team_name: str, last_n: int = 20) -> Dict:
        """Get ATS (against the spread) trends for a team."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT * FROM game_results
            WHERE (home_team LIKE ? OR away_team LIKE ?)
            AND home_spread IS NOT NULL
            ORDER BY game_date DESC LIMIT ?
        """, (f"%{team_name}%", f"%{team_name}%", last_n)).fetchall()
        conn.close()

        covers, pushes, fails = 0, 0, 0
        over_count, under_count = 0, 0
        for row in rows:
            home, away = row[2], row[3]
            hs, aws = row[4], row[5]
            spread, total = row[8], row[9]
            if hs is None or aws is None or spread is None:
                continue
            is_home = team_name.lower() in home.lower()
            actual_margin = (hs - aws) if is_home else (aws - hs)
            team_spread = spread if is_home else -spread

            if actual_margin + team_spread > 0:
                covers += 1
            elif actual_margin + team_spread == 0:
                pushes += 1
            else:
                fails += 1

            if total and (hs + aws) > total:
                over_count += 1
            elif total:
                under_count += 1

        total_games = covers + pushes + fails
        return {
            'ats_record': f"{covers}-{fails}-{pushes}",
            'ats_pct': covers / total_games if total_games > 0 else 0.5,
            'over_pct': over_count / total_games if total_games > 0 else 0.5,
            'total_games': total_games,
        }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fetcher = NCAABDataFetcher()

    print("Fetching NCAAB games from Odds API...")
    games = fetcher.fetch_games_from_odds(date.today())
    for g in games[:5]:
        print(f"  {g['away_team']} @ {g['home_team']} | Spread: {g.get('spread')} | Total: {g.get('total')}")

    print(f"\nFetching ESPN rankings...")
    rankings = fetcher.fetch_espn_rankings()
    for r in rankings[:10]:
        print(f"  #{r['rank']} {r['team']} ({r['record']})")
