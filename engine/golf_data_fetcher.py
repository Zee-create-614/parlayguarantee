# -*- coding: utf-8 -*-
"""
ParlayGuarantee Golf Data Fetcher
Sources: ESPN Golf API, The Odds API — cached in SQLite
"""

import sys
import os
import json
import time
import logging
import sqlite3
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "golf_data.db")
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

ESPN_GOLF_BASE = "https://site.api.espn.com/apis/site/v2/sports/golf"

# Known Odds API golf sport keys
GOLF_SPORT_KEYS = [
    "golf_masters_tournament_winner",
    "golf_pga_championship_winner",
    "golf_us_open_winner",
    "golf_the_open_championship_winner",
    "golf_the_players_championship_winner",
]


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class GolfDataDB:
    """SQLite cache for golf data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                name TEXT,
                country TEXT,
                world_ranking INTEGER DEFAULT 9999,
                age INTEGER,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS player_stats (
                player_id TEXT,
                season TEXT,
                events_played INTEGER DEFAULT 0,
                cuts_made INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                top5 INTEGER DEFAULT 0,
                top10 INTEGER DEFAULT 0,
                top25 INTEGER DEFAULT 0,
                scoring_avg REAL DEFAULT 72.0,
                driving_distance REAL DEFAULT 290.0,
                driving_accuracy REAL DEFAULT 60.0,
                gir_pct REAL DEFAULT 65.0,
                scrambling_pct REAL DEFAULT 55.0,
                putting_avg REAL DEFAULT 29.0,
                sg_total REAL DEFAULT 0.0,
                sg_putting REAL DEFAULT 0.0,
                sg_approach REAL DEFAULT 0.0,
                sg_tee REAL DEFAULT 0.0,
                sg_around_green REAL DEFAULT 0.0,
                updated_at TEXT,
                PRIMARY KEY (player_id, season)
            );
            CREATE TABLE IF NOT EXISTS tournament_history (
                player_id TEXT,
                tournament TEXT,
                year TEXT,
                finish_position INTEGER,
                score_to_par INTEGER,
                rounds_played INTEGER,
                PRIMARY KEY (player_id, tournament, year)
            );
            CREATE TABLE IF NOT EXISTS odds_cache (
                cache_key TEXT PRIMARY KEY,
                data_json TEXT,
                fetched_at TEXT
            );
            CREATE TABLE IF NOT EXISTS api_cache (
                cache_key TEXT PRIMARY KEY,
                data_json TEXT,
                fetched_at TEXT
            );
        """)
        conn.commit()
        conn.close()

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def upsert_player(self, player: Dict):
        conn = self.get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO players (player_id, name, country, world_ranking, age, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            player.get("id", ""), player.get("name", ""),
            player.get("country", ""), player.get("world_ranking", 9999),
            player.get("age", 0), datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()

    def get_player(self, name: str) -> Optional[Dict]:
        conn = self.get_conn()
        row = conn.execute(
            "SELECT * FROM players WHERE LOWER(name) LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%{name.lower()}%",)
        ).fetchone()
        conn.close()
        if not row:
            return None
        cols = ["player_id", "name", "country", "world_ranking", "age", "updated_at"]
        return dict(zip(cols, row))

    def get_player_stats(self, player_id: str, season: str = "2026") -> Dict:
        conn = self.get_conn()
        row = conn.execute(
            "SELECT * FROM player_stats WHERE player_id=? AND season=?",
            (player_id, season)
        ).fetchone()
        conn.close()
        if not row:
            return {}
        cols = ["player_id", "season", "events_played", "cuts_made", "wins",
                "top5", "top10", "top25", "scoring_avg", "driving_distance",
                "driving_accuracy", "gir_pct", "scrambling_pct", "putting_avg",
                "sg_total", "sg_putting", "sg_approach", "sg_tee", "sg_around_green",
                "updated_at"]
        return dict(zip(cols, row))

    def get_course_history(self, player_id: str, tournament: str) -> List[Dict]:
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT * FROM tournament_history WHERE player_id=? AND LOWER(tournament) LIKE ? ORDER BY year DESC LIMIT 5",
            (player_id, f"%{tournament.lower()}%")
        ).fetchall()
        conn.close()
        cols = ["player_id", "tournament", "year", "finish_position", "score_to_par", "rounds_played"]
        return [dict(zip(cols, r)) for r in rows]

    def cache_get(self, key: str, max_age_hours: int = 6) -> Optional:
        conn = self.get_conn()
        row = conn.execute("SELECT data_json, fetched_at FROM api_cache WHERE cache_key=?", (key,)).fetchone()
        conn.close()
        if not row:
            return None
        try:
            fetched = datetime.fromisoformat(row[1])
            if (datetime.now() - fetched).total_seconds() > max_age_hours * 3600:
                return None
            return json.loads(row[0])
        except Exception:
            return None

    def cache_set(self, key: str, data):
        conn = self.get_conn()
        conn.execute("INSERT OR REPLACE INTO api_cache (cache_key, data_json, fetched_at) VALUES (?,?,?)",
                     (key, json.dumps(data, default=str), datetime.now().isoformat()))
        conn.commit()
        conn.close()


class GolfDataFetcher:
    """Fetch golf data from ESPN and Odds API."""

    def __init__(self):
        self.db = GolfDataDB()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ─── Odds API ──────────────────────────────

    def get_active_golf_sports(self) -> List[Dict]:
        """Get active golf sport keys."""
        cached = self.db.cache_get("active_golf_sports", max_age_hours=6)
        if cached:
            return cached
        try:
            resp = self.session.get(f"{ODDS_API_BASE}/sports",
                                    params={"apiKey": ODDS_API_KEY}, timeout=15)
            resp.raise_for_status()
            all_sports = resp.json()
            golf = [s for s in all_sports if s.get("group", "").lower() == "golf" and s.get("active")]
            self.db.cache_set("active_golf_sports", golf)
            logger.info(f"Found {len(golf)} active golf sport keys")
            return golf
        except Exception as e:
            logger.error(f"Failed to fetch golf sports: {e}")
            return []

    def get_golf_odds(self, sport_key: str = None) -> List[Dict]:
        """Fetch outright winner odds for golf tournaments."""
        if sport_key:
            keys = [sport_key]
        else:
            sports = self.get_active_golf_sports()
            keys = [s["key"] for s in sports]
            # Also try known keys
            for k in GOLF_SPORT_KEYS:
                if k not in keys:
                    keys.append(k)

        all_events = []
        for key in keys:
            cache_key = f"golf_odds_{key}"
            cached = self.db.cache_get(cache_key, max_age_hours=4)
            if cached:
                if isinstance(cached, list):
                    all_events.extend(cached)
                continue
            try:
                resp = self.session.get(
                    f"{ODDS_API_BASE}/sports/{key}/odds",
                    params={"apiKey": ODDS_API_KEY, "regions": "us",
                            "markets": "outrights", "oddsFormat": "american"},
                    timeout=15
                )
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                events = resp.json()
                for e in events:
                    e["_sport_key"] = key
                self.db.cache_set(cache_key, events)
                all_events.extend(events)
                logger.info(f"Fetched {len(events)} golf events for {key}")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Golf odds error for {key}: {e}")
        return all_events

    def parse_outright_odds(self, event: Dict) -> Dict:
        """Parse outright/futures odds into {player_name: implied_probability}."""
        result = {}
        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt.get("key") != "outrights":
                    continue
                for outcome in mkt.get("outcomes", []):
                    price = outcome.get("price", 0)
                    if price > 0:
                        impl = 100.0 / (price + 100.0)
                    elif price < 0:
                        impl = abs(price) / (abs(price) + 100.0)
                    else:
                        continue
                    name = outcome.get("name", "")
                    result[name] = {"implied_prob": impl, "american_odds": price}
            break  # First bookmaker
        return result

    # ─── ESPN ──────────────────────────────────

    def get_espn_scoreboard(self, tour: str = "pga") -> Dict:
        """Fetch current golf scoreboard/leaderboard from ESPN."""
        cache_key = f"espn_golf_{tour}"
        cached = self.db.cache_get(cache_key, max_age_hours=3)
        if cached:
            return cached
        try:
            url = f"{ESPN_GOLF_BASE}/{tour}/scoreboard"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.db.cache_set(cache_key, data)
            return data
        except Exception as e:
            logger.error(f"ESPN golf scoreboard error: {e}")
            return {}

    def get_espn_leaderboard(self, tour: str = "pga") -> List[Dict]:
        """Parse ESPN leaderboard into player list."""
        data = self.get_espn_scoreboard(tour)
        players = []
        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                for competitor in comp.get("competitors", []):
                    athlete = competitor.get("athlete", {})
                    stats_list = competitor.get("statistics", [])
                    stats = {}
                    for s in stats_list:
                        stats[s.get("name", "")] = s.get("displayValue", "")

                    players.append({
                        "id": str(athlete.get("id", "")),
                        "name": athlete.get("displayName", ""),
                        "country": athlete.get("flag", {}).get("alt", ""),
                        "position": competitor.get("status", {}).get("position", {}).get("id", 999),
                        "score_to_par": competitor.get("score", "E"),
                        "thru": competitor.get("status", {}).get("thru", ""),
                        "tournament": event.get("name", ""),
                        "stats": stats,
                    })
                    # Store player in DB
                    self.db.upsert_player({
                        "id": str(athlete.get("id", "")),
                        "name": athlete.get("displayName", ""),
                        "country": athlete.get("flag", {}).get("alt", ""),
                        "world_ranking": competitor.get("status", {}).get("position", {}).get("id", 9999),
                    })
        return players

    def get_espn_rankings(self, tour: str = "pga") -> List[Dict]:
        """Fetch world golf rankings from ESPN."""
        cache_key = f"espn_golf_rankings_{tour}"
        cached = self.db.cache_get(cache_key, max_age_hours=24)
        if cached:
            return cached
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/golf/{tour}/rankings"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            rankings = []
            for r in data.get("rankings", [{}]):
                for entry in r.get("entries", []):
                    athlete = entry.get("athlete", {})
                    rankings.append({
                        "id": str(athlete.get("id", "")),
                        "name": athlete.get("displayName", ""),
                        "ranking": entry.get("current", 9999),
                        "country": athlete.get("flag", {}).get("alt", ""),
                    })
            self.db.cache_set(cache_key, rankings)
            for p in rankings:
                self.db.upsert_player({**p, "world_ranking": p.get("ranking", 9999)})
            return rankings
        except Exception as e:
            logger.error(f"ESPN golf rankings error: {e}")
            return []

    def get_player_info(self, name: str) -> Dict:
        player = self.db.get_player(name)
        if player:
            return player
        # Try fetching rankings (only once per session via cache)
        if not getattr(self, '_rankings_fetched', False):
            self._rankings_fetched = True
            rankings = self.get_espn_rankings("pga")
            for r in rankings:
                if name.lower() in r.get("name", "").lower():
                    return {**r, "player_id": r["id"], "world_ranking": r.get("ranking", 9999), "age": 30}
        return {
            "player_id": name.lower().replace(" ", "_"),
            "name": name, "world_ranking": 9999, "age": 30, "country": "",
        }

    def get_tournament_field(self) -> List[str]:
        """Get names of players in the current tournament field."""
        players = self.get_espn_leaderboard("pga")
        return [p["name"] for p in players if p.get("name")]
