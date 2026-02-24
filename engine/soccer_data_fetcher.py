# -*- coding: utf-8 -*-
"""
Soccer Data Fetcher — Multi-league soccer data for ParlayGuarantee
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

DB_PATH = os.path.join(os.path.dirname(__file__), 'soccer_data.db')
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}

# League configs: odds_api_key -> (espn_slug, display_name)
LEAGUES = {
    'soccer_epl': ('eng.1', 'English Premier League'),
    'soccer_spain_la_liga': ('esp.1', 'La Liga'),
    'soccer_germany_bundesliga': ('ger.1', 'Bundesliga'),
    'soccer_italy_serie_a': ('ita.1', 'Serie A'),
    'soccer_france_ligue_one': ('fra.1', 'Ligue 1'),
    'soccer_usa_mls': ('usa.1', 'MLS'),
    'soccer_uefa_champs_league': ('uefa.champions', 'Champions League'),
}

# Known derbies/rivalries for boost factor
RIVALRIES = {
    # EPL
    frozenset({'Liverpool', 'Everton'}), frozenset({'Manchester United', 'Manchester City'}),
    frozenset({'Arsenal', 'Tottenham Hotspur'}), frozenset({'Chelsea', 'Tottenham Hotspur'}),
    frozenset({'Liverpool', 'Manchester United'}), frozenset({'Arsenal', 'Chelsea'}),
    # La Liga
    frozenset({'Barcelona', 'Real Madrid'}), frozenset({'Atletico Madrid', 'Real Madrid'}),
    frozenset({'Real Betis', 'Sevilla FC'}),
    # Bundesliga
    frozenset({'Borussia Dortmund', 'Bayern Munich'}), frozenset({'Borussia Dortmund', 'Schalke 04'}),
    # Serie A
    frozenset({'AC Milan', 'Inter Milan'}), frozenset({'AS Roma', 'Lazio'}),
    frozenset({'Juventus', 'Inter Milan'}), frozenset({'Juventus', 'AC Milan'}),
    # Ligue 1
    frozenset({'Paris Saint-Germain', 'Olympique de Marseille'}),
    frozenset({'Lyon', 'Saint-Etienne'}),
    # MLS
    frozenset({'LA Galaxy', 'Los Angeles FC'}), frozenset({'New York Red Bulls', 'New York City FC'}),
}


class SoccerDataFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.db_path = DB_PATH
        self._init_db()
        self._team_stats_cache: Dict[str, Dict] = {}

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_name TEXT, league TEXT, season TEXT,
                wins INT, draws INT, losses INT,
                goals_for INT, goals_against INT,
                clean_sheets INT, league_position INT,
                home_wins INT, home_draws INT, home_losses INT,
                away_wins INT, away_draws INT, away_losses INT,
                form_l5 TEXT,
                last_updated TEXT,
                PRIMARY KEY (team_name, league, season)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_results (
                game_id TEXT PRIMARY KEY, game_date TEXT, league TEXT,
                home_team TEXT, away_team TEXT,
                home_score INT, away_score INT,
                home_shots INT, away_shots INT,
                home_shots_target INT, away_shots_target INT,
                home_possession REAL, away_possession REAL,
                home_corners INT, away_corners INT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS odds_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_date TEXT, league TEXT,
                home_team TEXT, away_team TEXT,
                home_odds REAL, draw_odds REAL, away_odds REAL,
                spread REAL, total REAL,
                bookmaker TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_date, home_team, away_team, bookmaker)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS espn_cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    # ─── ESPN API ──────────────────────────────────────────────

    def _espn_get(self, espn_slug: str, endpoint: str = 'scoreboard',
                  params: Dict = None, cache_hours: float = 1.0) -> Optional[Dict]:
        cache_key = f"{espn_slug}:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT data, timestamp FROM espn_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        if row:
            ts = datetime.fromisoformat(row[1])
            if (datetime.now() - ts).total_seconds() < cache_hours * 3600:
                conn.close()
                return json.loads(row[0])
        conn.close()

        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_slug}/{endpoint}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO espn_cache (cache_key, data, timestamp) VALUES (?, ?, ?)",
                (cache_key, json.dumps(data), datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            time.sleep(0.4)
            return data
        except Exception as e:
            logger.warning(f"ESPN fetch failed ({espn_slug}/{endpoint}): {e}")
            return None

    def fetch_espn_scoreboard(self, espn_slug: str, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch games from ESPN scoreboard for a league."""
        params = {}
        if target_date:
            params['dates'] = target_date.strftime('%Y%m%d')
        data = self._espn_get(espn_slug, 'scoreboard', params, cache_hours=0.5)
        if not data:
            return []

        games = []
        for event in data.get('events', []):
            comp = event.get('competitions', [{}])[0]
            competitors = comp.get('competitors', [])
            if len(competitors) < 2:
                continue

            home_c = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
            away_c = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[1])

            home_team = home_c.get('team', {}).get('displayName', '')
            away_team = away_c.get('team', {}).get('displayName', '')
            status = comp.get('status', {}).get('type', {}).get('name', 'STATUS_SCHEDULED')

            game = {
                'game_id': event.get('id', ''),
                'game_date': event.get('date', '')[:10],
                'game_time': event.get('date', ''),
                'home_team': home_team,
                'away_team': away_team,
                'home_team_id': home_c.get('team', {}).get('id', ''),
                'away_team_id': away_c.get('team', {}).get('id', ''),
                'status': status,
                'home_score': int(home_c.get('score', 0) or 0),
                'away_score': int(away_c.get('score', 0) or 0),
            }

            # Extract stats if available (completed games)
            stats_map = {}
            for stat in home_c.get('statistics', []):
                stats_map[f"home_{stat.get('name', '')}"] = stat.get('displayValue', '0')
            for stat in away_c.get('statistics', []):
                stats_map[f"away_{stat.get('name', '')}"] = stat.get('displayValue', '0')
            game['stats'] = stats_map

            games.append(game)

        return games

    def fetch_espn_standings(self, espn_slug: str) -> List[Dict]:
        """Fetch league standings from ESPN."""
        data = self._espn_get(espn_slug, 'standings', cache_hours=6)
        if not data:
            return []

        standings = []
        for group in data.get('children', []):
            for entry in group.get('standings', {}).get('entries', []):
                team = entry.get('team', {})
                stat_map = {}
                for s in entry.get('stats', []):
                    stat_map[s.get('name', '')] = s.get('value', 0)

                standings.append({
                    'team': team.get('displayName', ''),
                    'team_id': team.get('id', ''),
                    'position': int(stat_map.get('rank', 99)),
                    'games_played': int(stat_map.get('gamesPlayed', 0)),
                    'wins': int(stat_map.get('wins', 0)),
                    'draws': int(stat_map.get('ties', 0)),
                    'losses': int(stat_map.get('losses', 0)),
                    'goals_for': int(stat_map.get('pointsFor', 0)),
                    'goals_against': int(stat_map.get('pointsAgainst', 0)),
                    'goal_diff': int(stat_map.get('pointDifferential', 0)),
                    'points': int(stat_map.get('points', 0)),
                })
        return standings

    def fetch_espn_team_stats(self, espn_slug: str, team_id: str) -> Optional[Dict]:
        """Fetch detailed team stats from ESPN."""
        data = self._espn_get(espn_slug, f'teams/{team_id}/statistics', cache_hours=6)
        if not data:
            return None
        stat_map = {}
        for cat in data.get('results', {}).get('stats', {}).get('categories', []):
            for s in cat.get('stats', []):
                stat_map[s.get('name', '')] = s.get('value', 0)
        return stat_map

    def fetch_team_schedule(self, espn_slug: str, team_id: str, last_n: int = 10) -> List[Dict]:
        """Fetch recent results for a team."""
        data = self._espn_get(espn_slug, f'teams/{team_id}/schedule', cache_hours=3)
        if not data:
            return []
        results = []
        for event in data.get('events', []):
            comp = event.get('competitions', [{}])[0]
            status = comp.get('status', {}).get('type', {}).get('name', '')
            if status != 'STATUS_FINAL':
                continue
            competitors = comp.get('competitors', [])
            if len(competitors) < 2:
                continue
            home_c = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
            away_c = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[1])
            results.append({
                'game_id': event.get('id', ''),
                'date': event.get('date', '')[:10],
                'home_team': home_c.get('team', {}).get('displayName', ''),
                'away_team': away_c.get('team', {}).get('displayName', ''),
                'home_score': int(home_c.get('score', 0) or 0),
                'away_score': int(away_c.get('score', 0) or 0),
            })
        # Return most recent N
        results.sort(key=lambda x: x['date'], reverse=True)
        return results[:last_n]

    # ─── Odds API ──────────────────────────────────────────────

    def fetch_odds(self, odds_sport: str, target_date: Optional[date] = None) -> List[Dict]:
        """Fetch odds from The Odds API for a soccer league."""
        url = f"https://api.the-odds-api.com/v4/sports/{odds_sport}/odds"
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us,uk',
            'markets': 'h2h,spreads,totals',
            'oddsFormat': 'american',
        }
        try:
            resp = self.session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            events = resp.json()
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"Odds API: {len(events)} {odds_sport} events (remaining: {remaining})")
        except Exception as e:
            logger.error(f"Odds API failed for {odds_sport}: {e}")
            return []

        games = []
        target_str = (target_date or date.today()).isoformat()

        for ev in events:
            commence = ev.get('commence_time', '')
            game_date_str = commence[:10] if commence else ''

            if target_date:
                try:
                    game_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    target_start = datetime.fromisoformat(f"{target_str}T00:00:00+00:00")
                    target_end = target_start + timedelta(hours=30)
                    if not (target_start <= game_dt <= target_end):
                        continue
                except Exception:
                    continue

            home = ev.get('home_team', '')
            away = ev.get('away_team', '')

            h2h_home, h2h_draw, h2h_away = None, None, None
            spread_val, spread_price = None, None
            total_val = None

            for bm in ev.get('bookmakers', []):
                for mkt in bm.get('markets', []):
                    if mkt['key'] == 'h2h':
                        for oc in mkt['outcomes']:
                            if oc['name'] == home:
                                h2h_home = oc.get('price')
                            elif oc['name'] == away:
                                h2h_away = oc.get('price')
                            elif oc['name'] == 'Draw':
                                h2h_draw = oc.get('price')
                    elif mkt['key'] == 'spreads':
                        for oc in mkt['outcomes']:
                            if oc['name'] == home:
                                spread_val = oc.get('point')
                                spread_price = oc.get('price')
                    elif mkt['key'] == 'totals':
                        for oc in mkt['outcomes']:
                            if oc['name'] == 'Over':
                                total_val = oc.get('point')
                if h2h_home is not None:
                    break

            home_prob = self._american_to_prob(h2h_home)
            draw_prob = self._american_to_prob(h2h_draw)
            away_prob = self._american_to_prob(h2h_away)
            # Remove vig
            total_prob = home_prob + draw_prob + away_prob
            if total_prob > 0:
                home_prob /= total_prob
                draw_prob /= total_prob
                away_prob /= total_prob

            games.append({
                'game_id': ev.get('id', ''),
                'game_date': game_date_str,
                'game_time': commence,
                'home_team': home,
                'away_team': away,
                'home_odds': h2h_home,
                'draw_odds': h2h_draw,
                'away_odds': h2h_away,
                'home_implied_prob': home_prob,
                'draw_implied_prob': draw_prob,
                'away_implied_prob': away_prob,
                'spread': spread_val,
                'total': total_val,
            })

            self._store_odds(game_date_str, odds_sport, home, away,
                             h2h_home, h2h_draw, h2h_away, spread_val, total_val)

        return games

    def _american_to_prob(self, odds) -> float:
        if odds is None:
            return 0.33
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)

    def _store_odds(self, game_date, league, home, away,
                    home_odds, draw_odds, away_odds, spread, total):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                INSERT OR REPLACE INTO odds_cache
                (game_date, league, home_team, away_team,
                 home_odds, draw_odds, away_odds, spread, total, bookmaker)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'consensus')
            """, (game_date, league, home, away,
                  home_odds, draw_odds, away_odds, spread, total))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store odds: {e}")

    # ─── Composite fetchers ───────────────────────────────────

    def fetch_all_games(self, target_date: Optional[date] = None,
                        leagues: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
        """Fetch games across all (or specified) leagues. Returns {league_key: [games]}."""
        target = target_date or date.today()
        league_keys = leagues or list(LEAGUES.keys())
        result = {}

        for lk in league_keys:
            if lk not in LEAGUES:
                logger.warning(f"Unknown league: {lk}")
                continue
            espn_slug, display = LEAGUES[lk]

            # Try odds API first (has lines)
            odds_games = self.fetch_odds(lk, target)

            # Also fetch ESPN scoreboard for team IDs and extra data
            espn_games = self.fetch_espn_scoreboard(espn_slug, target)

            # Merge: use odds games as base, enrich with ESPN data
            merged = self._merge_games(odds_games, espn_games, lk, display)
            if merged:
                result[lk] = merged
                logger.info(f"{display}: {len(merged)} games")

        return result

    def _merge_games(self, odds_games: List[Dict], espn_games: List[Dict],
                     league_key: str, league_name: str) -> List[Dict]:
        """Merge odds and ESPN data."""
        if not odds_games and not espn_games:
            return []

        # Index ESPN games by team names (fuzzy)
        espn_map = {}
        for eg in espn_games:
            key = (eg['home_team'].lower(), eg['away_team'].lower())
            espn_map[key] = eg

        merged = []
        seen = set()

        for og in odds_games:
            og['league'] = league_key
            og['league_name'] = league_name

            # Try to find ESPN match
            hk = og['home_team'].lower()
            ak = og['away_team'].lower()
            espn = espn_map.get((hk, ak))
            if not espn:
                # Fuzzy match
                for (eh, ea), ev in espn_map.items():
                    if (hk in eh or eh in hk) and (ak in ea or ea in ak):
                        espn = ev
                        break

            if espn:
                og['home_team_id'] = espn.get('home_team_id', '')
                og['away_team_id'] = espn.get('away_team_id', '')
                og['stats'] = espn.get('stats', {})
            else:
                og['home_team_id'] = ''
                og['away_team_id'] = ''
                og['stats'] = {}

            merged.append(og)
            seen.add((og['home_team'], og['away_team']))

        # Add ESPN-only games (no odds)
        for eg in espn_games:
            if (eg['home_team'], eg['away_team']) not in seen:
                eg['league'] = league_key
                eg['league_name'] = league_name
                eg['home_odds'] = None
                eg['draw_odds'] = None
                eg['away_odds'] = None
                eg['home_implied_prob'] = 0.33
                eg['draw_implied_prob'] = 0.33
                eg['away_implied_prob'] = 0.33
                eg['spread'] = None
                eg['total'] = None
                merged.append(eg)

        return merged

    def get_standings(self, league_key: str) -> List[Dict]:
        if league_key not in LEAGUES:
            return []
        espn_slug = LEAGUES[league_key][0]
        return self.fetch_espn_standings(espn_slug)

    def get_team_recent_form(self, espn_slug: str, team_id: str, n: int = 5) -> Dict:
        """Compute recent form stats for a team."""
        schedule = self.fetch_team_schedule(espn_slug, team_id, last_n=n)
        if not schedule:
            return {'form_str': '', 'wins': 0, 'draws': 0, 'losses': 0,
                    'goals_for': 0, 'goals_against': 0, 'clean_sheets': 0,
                    'games': 0}

        wins, draws, losses = 0, 0, 0
        gf, ga, cs = 0, 0, 0
        form_chars = []

        for g in schedule:
            ht, at = g['home_team'], g['away_team']
            hs, aws = g['home_score'], g['away_score']
            # Determine if this team is home or away
            is_home = team_id == ''  # We'll match by name below
            # Just use scores
            if hs == aws:
                draws += 1
                form_chars.append('D')
            elif hs > aws:
                form_chars.append('W')
                wins += 1
            else:
                form_chars.append('L')
                losses += 1
            gf += hs
            ga += aws
            if aws == 0:
                cs += 1

        return {
            'form_str': ''.join(form_chars[:n]),
            'wins': wins, 'draws': draws, 'losses': losses,
            'goals_for': gf, 'goals_against': ga,
            'clean_sheets': cs, 'games': len(schedule),
        }

    def is_rivalry(self, home: str, away: str) -> bool:
        """Check if this is a known derby/rivalry match."""
        pair = frozenset({home, away})
        # Direct match
        if pair in RIVALRIES:
            return True
        # Fuzzy match
        for r in RIVALRIES:
            names = list(r)
            if len(names) == 2:
                if (names[0].lower() in home.lower() or home.lower() in names[0].lower()) and \
                   (names[1].lower() in away.lower() or away.lower() in names[1].lower()):
                    return True
                if (names[1].lower() in home.lower() or home.lower() in names[1].lower()) and \
                   (names[0].lower() in away.lower() or away.lower() in names[0].lower()):
                    return True
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    fetcher = SoccerDataFetcher()
    print("Fetching soccer games across all leagues...")
    all_games = fetcher.fetch_all_games()
    for league, games in all_games.items():
        print(f"\n{LEAGUES[league][1]}: {len(games)} games")
        for g in games[:3]:
            print(f"  {g['home_team']} vs {g['away_team']} | "
                  f"Spread: {g.get('spread')} | Total: {g.get('total')}")
