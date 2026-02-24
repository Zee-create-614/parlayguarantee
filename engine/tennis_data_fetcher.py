# -*- coding: utf-8 -*-
"""
ParlayGuarantee Tennis Data Fetcher
Sources: ESPN API, The Odds API — cached in SQLite
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

DB_PATH = os.path.join(os.path.dirname(__file__), "tennis_data.db")
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# ESPN endpoints
ESPN_TENNIS_BASE = "https://site.api.espn.com/apis/site/v2/sports/tennis"

# Surface mapping from tournament names
SURFACE_HINTS = {
    "australian_open": "hard", "us_open": "hard", "indian_wells": "hard",
    "miami": "hard", "qatar": "hard", "dubai": "hard", "doha": "hard",
    "beijing": "hard", "shanghai": "hard", "cincinnati": "hard",
    "canadian": "hard", "montreal": "hard", "toronto": "hard",
    "french_open": "clay", "roland_garros": "clay", "rome": "clay",
    "madrid": "clay", "monte_carlo": "clay", "barcelona": "clay",
    "hamburg": "clay", "buenos_aires": "clay", "rio": "clay",
    "wimbledon": "grass", "halle": "grass", "queens": "grass",
    "stuttgart": "grass", "s_hertogenbosch": "grass",
}


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class TennisDataDB:
    """SQLite cache for tennis data."""

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
                ranking INTEGER,
                ranking_points REAL,
                age INTEGER,
                height_cm REAL,
                hand TEXT,
                tour TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS player_stats (
                player_id TEXT,
                season TEXT,
                surface TEXT,
                matches_played INTEGER DEFAULT 0,
                matches_won INTEGER DEFAULT 0,
                aces_per_match REAL DEFAULT 0,
                double_faults_per_match REAL DEFAULT 0,
                first_serve_pct REAL DEFAULT 0,
                break_points_converted REAL DEFAULT 0,
                return_games_won_pct REAL DEFAULT 0,
                sets_won INTEGER DEFAULT 0,
                sets_lost INTEGER DEFAULT 0,
                tiebreaks_won INTEGER DEFAULT 0,
                tiebreaks_lost INTEGER DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (player_id, season, surface)
            );
            CREATE TABLE IF NOT EXISTS match_history (
                match_id TEXT PRIMARY KEY,
                date TEXT,
                tournament TEXT,
                surface TEXT,
                indoor INTEGER DEFAULT 0,
                player1_id TEXT,
                player2_id TEXT,
                winner_id TEXT,
                score TEXT,
                round TEXT
            );
            CREATE TABLE IF NOT EXISTS odds_cache (
                event_id TEXT PRIMARY KEY,
                sport_key TEXT,
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
            INSERT OR REPLACE INTO players
            (player_id, name, country, ranking, ranking_points, age, height_cm, hand, tour, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player.get("id", ""), player.get("name", ""), player.get("country", ""),
            player.get("ranking", 9999), player.get("ranking_points", 0),
            player.get("age", 0), player.get("height_cm", 0),
            player.get("hand", "R"), player.get("tour", "ATP"),
            datetime.now().isoformat(),
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
        cols = ["player_id", "name", "country", "ranking", "ranking_points",
                "age", "height_cm", "hand", "tour", "updated_at"]
        return dict(zip(cols, row))

    def get_player_stats(self, player_id: str, surface: str = "all") -> Dict:
        conn = self.get_conn()
        row = conn.execute(
            "SELECT * FROM player_stats WHERE player_id = ? AND surface = ? ORDER BY season DESC LIMIT 1",
            (player_id, surface)
        ).fetchone()
        conn.close()
        if not row:
            return {}
        cols = ["player_id", "season", "surface", "matches_played", "matches_won",
                "aces_per_match", "double_faults_per_match", "first_serve_pct",
                "break_points_converted", "return_games_won_pct",
                "sets_won", "sets_lost", "tiebreaks_won", "tiebreaks_lost", "updated_at"]
        return dict(zip(cols, row))

    def get_h2h(self, p1_name: str, p2_name: str) -> Dict:
        """Get head-to-head record between two players."""
        conn = self.get_conn()
        # Find player IDs
        p1 = conn.execute("SELECT player_id FROM players WHERE LOWER(name) LIKE ?",
                          (f"%{p1_name.lower()}%",)).fetchone()
        p2 = conn.execute("SELECT player_id FROM players WHERE LOWER(name) LIKE ?",
                          (f"%{p2_name.lower()}%",)).fetchone()
        if not p1 or not p2:
            conn.close()
            return {"p1_wins": 0, "p2_wins": 0, "total": 0}
        p1_id, p2_id = p1[0], p2[0]
        p1_wins = conn.execute(
            "SELECT COUNT(*) FROM match_history WHERE winner_id=? AND ((player1_id=? AND player2_id=?) OR (player1_id=? AND player2_id=?))",
            (p1_id, p1_id, p2_id, p2_id, p1_id)
        ).fetchone()[0]
        p2_wins = conn.execute(
            "SELECT COUNT(*) FROM match_history WHERE winner_id=? AND ((player1_id=? AND player2_id=?) OR (player1_id=? AND player2_id=?))",
            (p2_id, p1_id, p2_id, p2_id, p1_id)
        ).fetchone()[0]
        conn.close()
        return {"p1_wins": p1_wins, "p2_wins": p2_wins, "total": p1_wins + p2_wins}

    def cache_get(self, key: str, max_age_hours: int = 6) -> Optional[Dict]:
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


class TennisDataFetcher:
    """Fetch tennis data from ESPN and Odds API."""

    def __init__(self):
        self.db = TennisDataDB()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ─── Odds API ──────────────────────────────

    def get_active_tennis_sports(self) -> List[Dict]:
        """Get all active tennis sport keys from Odds API."""
        cached = self.db.cache_get("active_tennis_sports", max_age_hours=4)
        if cached:
            return cached
        try:
            resp = self.session.get(f"{ODDS_API_BASE}/sports", params={"apiKey": ODDS_API_KEY}, timeout=15)
            resp.raise_for_status()
            all_sports = resp.json()
            tennis = [s for s in all_sports if s.get("group", "").lower() == "tennis" and s.get("active")]
            self.db.cache_set("active_tennis_sports", tennis)
            logger.info(f"Found {len(tennis)} active tennis sport keys")
            return tennis
        except Exception as e:
            logger.error(f"Failed to fetch tennis sports: {e}")
            return []

    def get_tennis_odds(self, sport_key: str = None) -> List[Dict]:
        """Fetch odds for tennis matches. If no sport_key, fetches all active."""
        if sport_key:
            keys = [sport_key]
        else:
            sports = self.get_active_tennis_sports()
            keys = [s["key"] for s in sports]

        all_events = []
        for key in keys:
            cache_key = f"tennis_odds_{key}"
            cached = self.db.cache_get(cache_key, max_age_hours=2)
            if cached:
                all_events.extend(cached)
                continue
            try:
                resp = self.session.get(
                    f"{ODDS_API_BASE}/sports/{key}/odds",
                    params={"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h",
                            "oddsFormat": "american"},
                    timeout=15
                )
                resp.raise_for_status()
                events = resp.json()
                for e in events:
                    e["_sport_key"] = key
                self.db.cache_set(cache_key, events)
                all_events.extend(events)
                logger.info(f"Fetched {len(events)} events for {key}")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Odds API error for {key}: {e}")
        return all_events

    # ─── ESPN ──────────────────────────────────

    def get_espn_scoreboard(self, tour: str = "atp") -> List[Dict]:
        """Fetch current tennis scoreboard from ESPN."""
        cache_key = f"espn_tennis_{tour}"
        cached = self.db.cache_get(cache_key, max_age_hours=3)
        if cached:
            return cached
        try:
            url = f"{ESPN_TENNIS_BASE}/{tour}/scoreboard"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            events = data.get("events", [])
            self.db.cache_set(cache_key, events)
            return events
        except Exception as e:
            logger.error(f"ESPN tennis fetch error: {e}")
            return []

    def get_espn_player_rankings(self, tour: str = "atp") -> List[Dict]:
        """Fetch rankings from ESPN."""
        cache_key = f"espn_tennis_rankings_{tour}"
        cached = self.db.cache_get(cache_key, max_age_hours=24)
        if cached:
            return cached
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/rankings"
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
                        "country": athlete.get("flag", {}).get("alt", ""),
                        "ranking": entry.get("current", 9999),
                        "ranking_points": _safe_float(entry.get("stats", [{}])[0].get("value") if entry.get("stats") else 0),
                    })
            self.db.cache_set(cache_key, rankings)
            # Store in DB
            for p in rankings:
                self.db.upsert_player({**p, "tour": tour.upper()})
            return rankings
        except Exception as e:
            logger.error(f"ESPN rankings error: {e}")
            return []

    def parse_espn_matches(self, events: List[Dict]) -> List[Dict]:
        """Parse ESPN event data into match dicts."""
        matches = []
        for event in events:
            tournament = event.get("name", "")
            for comp in event.get("competitions", []):
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue
                p1 = competitors[0].get("athlete", {})
                p2 = competitors[1].get("athlete", {})
                matches.append({
                    "tournament": tournament,
                    "player1": p1.get("displayName", competitors[0].get("team", {}).get("displayName", "Unknown")),
                    "player2": p2.get("displayName", competitors[1].get("team", {}).get("displayName", "Unknown")),
                    "player1_id": str(p1.get("id", "")),
                    "player2_id": str(p2.get("id", "")),
                    "player1_seed": competitors[0].get("seed", ""),
                    "player2_seed": competitors[1].get("seed", ""),
                    "status": comp.get("status", {}).get("type", {}).get("name", ""),
                    "round": comp.get("round", {}).get("displayName", ""),
                })
        return matches

    def detect_surface(self, tournament_name: str, sport_key: str = "") -> str:
        """Guess surface from tournament name."""
        combined = (tournament_name + " " + sport_key).lower()
        for hint, surface in SURFACE_HINTS.items():
            if hint in combined:
                return surface
        # Default to hard court (most common)
        return "hard"

    def get_player_info(self, name: str) -> Dict:
        """Get or create player info, checking DB first then ESPN."""
        player = self.db.get_player(name)
        if player:
            return player
        # Try fetching rankings to populate DB
        for tour in ["atp", "wta"]:
            rankings = self.get_espn_player_rankings(tour)
            for r in rankings:
                if name.lower() in r.get("name", "").lower():
                    return {**r, "tour": tour.upper(), "hand": "R", "height_cm": 180, "age": 25}
        # Fallback
        return {
            "player_id": name.lower().replace(" ", "_"),
            "name": name, "ranking": 9999, "ranking_points": 0,
            "age": 25, "height_cm": 180, "hand": "R", "tour": "ATP",
            "country": "",
        }

    def get_recent_form(self, player_name: str, n: int = 10) -> Dict:
        """Get recent match results from DB."""
        conn = self.db.get_conn()
        player = conn.execute("SELECT player_id FROM players WHERE LOWER(name) LIKE ?",
                              (f"%{player_name.lower()}%",)).fetchone()
        if not player:
            conn.close()
            return {"wins": 0, "losses": 0, "total": 0, "win_pct": 0.5}
        pid = player[0]
        rows = conn.execute("""
            SELECT winner_id FROM match_history
            WHERE player1_id=? OR player2_id=?
            ORDER BY date DESC LIMIT ?
        """, (pid, pid, n)).fetchall()
        conn.close()
        wins = sum(1 for r in rows if r[0] == pid)
        total = len(rows)
        return {"wins": wins, "losses": total - wins, "total": total,
                "win_pct": wins / total if total > 0 else 0.5}
