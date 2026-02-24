"""
line_tracker.py — SQLite storage for line movement history.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional

from book_scraper import GameLine
from consensus import ConsensusGame

logger = logging.getLogger("line_tracker")

DB_PATH = "lines.db"


def _get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str = DB_PATH):
    conn = _get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scrapes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            game_count INTEGER NOT NULL,
            status TEXT DEFAULT 'ok'
        );
        CREATE TABLE IF NOT EXISTS game_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            start_time TEXT,
            spread_home REAL,
            spread_away REAL,
            total REAL,
            ml_home INTEGER,
            ml_away INTEGER,
            scraped_at TEXT NOT NULL,
            FOREIGN KEY (scrape_id) REFERENCES scrapes(id)
        );
        CREATE TABLE IF NOT EXISTS consensus_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            start_time TEXT,
            spread REAL,
            total REAL,
            ml_home INTEGER,
            ml_away INTEGER,
            confidence TEXT,
            flags TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gl_teams ON game_lines(home_team, away_team);
        CREATE INDEX IF NOT EXISTS idx_cl_teams ON consensus_lines(home_team, away_team);
    """)
    conn.close()
    logger.info("Database initialized")


def store_scrape(source: str, games: list[GameLine], db_path: str = DB_PATH) -> int:
    conn = _get_conn(db_path)
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO scrapes (source, scraped_at, game_count, status) VALUES (?, ?, ?, ?)",
        (source, now, len(games), "ok")
    )
    scrape_id = cur.lastrowid
    for g in games:
        conn.execute(
            "INSERT INTO game_lines (scrape_id, source, home_team, away_team, start_time, spread_home, spread_away, total, ml_home, ml_away, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (scrape_id, g.source, g.home_team, g.away_team, g.start_time,
             g.spread_home, g.spread_away, g.total, g.moneyline_home, g.moneyline_away, g.scraped_at)
        )
    conn.commit()
    conn.close()
    return scrape_id


def store_consensus(games: list[ConsensusGame], db_path: str = DB_PATH):
    conn = _get_conn(db_path)
    now = datetime.now(timezone.utc).isoformat()
    for g in games:
        conn.execute(
            "INSERT INTO consensus_lines (home_team, away_team, start_time, spread, total, ml_home, ml_away, confidence, flags, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (g.home_team, g.away_team, g.start_time, g.spread_home, g.total,
             g.moneyline_home, g.moneyline_away, g.confidence, "|".join(g.flags), now)
        )
    conn.commit()
    conn.close()


def get_line_movement(home_team: str, away_team: str, db_path: str = DB_PATH) -> list[dict]:
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM game_lines WHERE home_team=? AND away_team=? ORDER BY scraped_at",
        (home_team, away_team)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
