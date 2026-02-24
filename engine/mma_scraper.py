"""
MMA Scraper — UFC Stats (ufcstats.com) scraper with SQLite caching
Production-grade fighter data collection for MMAEngine
"""

import re
import sys
import time
import json
import logging
import sqlite3
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "mma_data.db"
CACHE_HOURS = 48  # re-scrape fighter data every 48 hours
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def _safe_float(val: str, default: float = 0.0) -> float:
    """Parse a string to float, stripping %, --, etc."""
    if not val or val.strip() in ("", "--", "---", "N/A"):
        return default
    val = val.strip().replace("%", "").replace(",", "")
    try:
        return float(val)
    except ValueError:
        return default


def _safe_int(val: str, default: int = 0) -> int:
    if not val or val.strip() in ("", "--", "---", "N/A"):
        return default
    val = val.strip().replace(",", "")
    try:
        return int(val)
    except ValueError:
        return default


def _inches_from_str(val: str) -> float:
    """Convert height/reach strings like 6' 2\" or 72\" to inches."""
    if not val or val.strip() in ("", "--"):
        return 0.0
    val = val.strip().replace('"', '').replace("″", "")
    # Format: 6' 2
    m = re.match(r"(\d+)'\s*(\d+)", val)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2))
    # Just inches
    try:
        return float(val.replace("'", "").strip())
    except ValueError:
        return 0.0


class MMADataDB:
    """SQLite cache for fighter stats and fight history."""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS fighters (
            fighter_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            nickname TEXT,
            record TEXT,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0,
            no_contests INTEGER DEFAULT 0,
            height_inches REAL DEFAULT 0,
            reach_inches REAL DEFAULT 0,
            stance TEXT,
            dob TEXT,
            slpm REAL DEFAULT 0,
            str_acc REAL DEFAULT 0,
            sapm REAL DEFAULT 0,
            str_def REAL DEFAULT 0,
            td_avg REAL DEFAULT 0,
            td_acc REAL DEFAULT 0,
            td_def REAL DEFAULT 0,
            sub_avg REAL DEFAULT 0,
            weight_class TEXT,
            profile_url TEXT,
            last_scraped TEXT,
            raw_json TEXT
        );
        CREATE TABLE IF NOT EXISTS fight_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fighter_id TEXT,
            opponent_name TEXT,
            result TEXT,
            method TEXT,
            method_detail TEXT,
            round INTEGER,
            fight_time TEXT,
            event_name TEXT,
            event_date TEXT,
            weight_class TEXT,
            kd INTEGER DEFAULT 0,
            sig_str TEXT,
            sig_str_pct REAL DEFAULT 0,
            total_str TEXT,
            td TEXT,
            td_pct REAL DEFAULT 0,
            sub_att INTEGER DEFAULT 0,
            rev INTEGER DEFAULT 0,
            ctrl TEXT,
            UNIQUE(fighter_id, event_name, opponent_name)
        );
        CREATE TABLE IF NOT EXISTS events_cache (
            cache_key TEXT PRIMARY KEY,
            data TEXT,
            cached_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_fh_fighter ON fight_history(fighter_id);
        CREATE INDEX IF NOT EXISTS idx_fighters_name ON fighters(name);
        """)
        conn.commit()
        conn.close()

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    def get_fighter(self, fighter_id: str) -> Optional[Dict]:
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM fighters WHERE fighter_id = ?", (fighter_id,)).fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def find_fighter_by_name(self, name: str) -> Optional[Dict]:
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        # exact match first
        row = conn.execute("SELECT * FROM fighters WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
        if not row:
            # fuzzy: LIKE
            row = conn.execute("SELECT * FROM fighters WHERE LOWER(name) LIKE ?",
                               (f"%{name.lower()}%",)).fetchone()
        conn.close()
        return dict(row) if row else None

    def is_stale(self, fighter_id: str) -> bool:
        f = self.get_fighter(fighter_id)
        if not f or not f.get("last_scraped"):
            return True
        last = datetime.fromisoformat(f["last_scraped"])
        return (datetime.now() - last).total_seconds() > CACHE_HOURS * 3600

    def upsert_fighter(self, data: Dict):
        conn = self.get_conn()
        conn.execute("""
            INSERT INTO fighters (fighter_id, name, nickname, record, wins, losses, draws, no_contests,
                height_inches, reach_inches, stance, dob, slpm, str_acc, sapm, str_def,
                td_avg, td_acc, td_def, sub_avg, weight_class, profile_url, last_scraped, raw_json)
            VALUES (:fighter_id, :name, :nickname, :record, :wins, :losses, :draws, :no_contests,
                :height_inches, :reach_inches, :stance, :dob, :slpm, :str_acc, :sapm, :str_def,
                :td_avg, :td_acc, :td_def, :sub_avg, :weight_class, :profile_url, :last_scraped, :raw_json)
            ON CONFLICT(fighter_id) DO UPDATE SET
                name=:name, nickname=:nickname, record=:record, wins=:wins, losses=:losses,
                draws=:draws, no_contests=:no_contests, height_inches=:height_inches,
                reach_inches=:reach_inches, stance=:stance, dob=:dob,
                slpm=:slpm, str_acc=:str_acc, sapm=:sapm, str_def=:str_def,
                td_avg=:td_avg, td_acc=:td_acc, td_def=:td_def, sub_avg=:sub_avg,
                weight_class=:weight_class, profile_url=:profile_url,
                last_scraped=:last_scraped, raw_json=:raw_json
        """, data)
        conn.commit()
        conn.close()

    def upsert_fight(self, data: Dict):
        conn = self.get_conn()
        conn.execute("""
            INSERT INTO fight_history (fighter_id, opponent_name, result, method, method_detail,
                round, fight_time, event_name, event_date, weight_class,
                kd, sig_str, sig_str_pct, total_str, td, td_pct, sub_att, rev, ctrl)
            VALUES (:fighter_id, :opponent_name, :result, :method, :method_detail,
                :round, :fight_time, :event_name, :event_date, :weight_class,
                :kd, :sig_str, :sig_str_pct, :total_str, :td, :td_pct, :sub_att, :rev, :ctrl)
            ON CONFLICT(fighter_id, event_name, opponent_name) DO UPDATE SET
                result=:result, method=:method, method_detail=:method_detail,
                round=:round, fight_time=:fight_time, event_date=:event_date,
                weight_class=:weight_class, kd=:kd, sig_str=:sig_str,
                sig_str_pct=:sig_str_pct, total_str=:total_str, td=:td,
                td_pct=:td_pct, sub_att=:sub_att, rev=:rev, ctrl=:ctrl
        """, data)
        conn.commit()
        conn.close()

    def get_fight_history(self, fighter_id: str) -> List[Dict]:
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM fight_history WHERE fighter_id = ? ORDER BY event_date DESC",
            (fighter_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def cache_get(self, key: str, max_age_hours: float = 6) -> Optional[str]:
        conn = self.get_conn()
        row = conn.execute("SELECT data, cached_at FROM events_cache WHERE cache_key = ?", (key,)).fetchone()
        conn.close()
        if row:
            cached_at = datetime.fromisoformat(row[1])
            if (datetime.now() - cached_at).total_seconds() < max_age_hours * 3600:
                return row[0]
        return None

    def cache_set(self, key: str, data: str):
        conn = self.get_conn()
        conn.execute("""
            INSERT INTO events_cache (cache_key, data, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET data=?, cached_at=?
        """, (key, data, datetime.now().isoformat(), data, datetime.now().isoformat()))
        conn.commit()
        conn.close()


class UFCScraper:
    """Scrapes fighter stats and fight history from ufcstats.com."""

    BASE = "http://www.ufcstats.com/statistics/fighters"
    FIGHTER_DETAIL = "http://www.ufcstats.com/fighter-details/"
    EVENT_LIST = "http://www.ufcstats.com/statistics/events/completed"
    UPCOMING = "http://www.ufcstats.com/statistics/events/upcoming"

    def __init__(self, db: MMADataDB = None):
        self.db = db or MMADataDB()
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0

    def _throttle(self, delay: float = 1.5):
        elapsed = time.time() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.time()

    def _get(self, url: str) -> Optional[BeautifulSoup]:
        self._throttle()
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Fighter search & detail
    # ------------------------------------------------------------------

    def search_fighter_url(self, name: str) -> Optional[str]:
        """Search ufcstats.com for a fighter by name, return profile URL."""
        # Try first letter search
        first = name.strip().split()[-1][0].lower()  # last name first letter
        url = f"{self.BASE}?char={first}&page=all"
        soup = self._get(url)
        if not soup:
            return None

        name_lower = name.lower().strip()
        rows = soup.select("tr.b-statistics__table-row")
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 2:
                first_name = cols[0].get_text(strip=True)
                last_name = cols[1].get_text(strip=True)
                full = f"{first_name} {last_name}".lower()
                if full == name_lower or name_lower in full:
                    link = cols[0].find("a")
                    if link and link.get("href"):
                        return link["href"]
        # Fallback: try first name letter
        first2 = name.strip().split()[0][0].lower()
        if first2 != first:
            url = f"{self.BASE}?char={first2}&page=all"
            soup = self._get(url)
            if soup:
                rows = soup.select("tr.b-statistics__table-row")
                for row in rows:
                    cols = row.select("td")
                    if len(cols) >= 2:
                        first_name = cols[0].get_text(strip=True)
                        last_name = cols[1].get_text(strip=True)
                        full = f"{first_name} {last_name}".lower()
                        if full == name_lower or name_lower in full:
                            link = cols[0].find("a")
                            if link and link.get("href"):
                                return link["href"]
        logger.warning(f"Fighter not found on ufcstats: {name}")
        return None

    def scrape_fighter_detail(self, profile_url: str) -> Optional[Dict]:
        """Scrape full fighter stats from their ufcstats detail page."""
        soup = self._get(profile_url)
        if not soup:
            return None

        fighter_id = profile_url.rstrip("/").split("/")[-1]
        data = {"fighter_id": fighter_id, "profile_url": profile_url}

        # Name
        name_el = soup.select_one("span.b-content__title-highlight")
        data["name"] = name_el.get_text(strip=True) if name_el else "Unknown"

        # Nickname
        nick_el = soup.select_one("p.b-content__Nickname")
        data["nickname"] = nick_el.get_text(strip=True) if nick_el else ""

        # Record
        record_el = soup.select_one("span.b-content__title-record")
        record_text = record_el.get_text(strip=True) if record_el else "0-0-0"
        record_text = record_text.replace("Record:", "").strip()
        data["record"] = record_text
        parts = re.match(r"(\d+)-(\d+)-(\d+)(?:\s*\((\d+)\s*NC\))?", record_text)
        if parts:
            data["wins"] = int(parts.group(1))
            data["losses"] = int(parts.group(2))
            data["draws"] = int(parts.group(3))
            data["no_contests"] = int(parts.group(4)) if parts.group(4) else 0
        else:
            data["wins"] = data["losses"] = data["draws"] = data["no_contests"] = 0

        # Bio box — height, weight, reach, stance, dob
        bio_items = soup.select("ul.b-list__box-list li.b-list__box-list-item")
        for item in bio_items:
            text = item.get_text(separator="|", strip=True)
            if "Height:" in text:
                val = text.split("Height:")[-1].strip().strip("|").strip()
                data["height_inches"] = _inches_from_str(val)
            elif "Weight:" in text:
                pass  # we use weight class instead
            elif "Reach:" in text:
                val = text.split("Reach:")[-1].strip().strip("|").strip()
                data["reach_inches"] = _inches_from_str(val)
            elif "STANCE:" in text.upper():
                val = text.split(":")[-1].strip().strip("|").strip()
                data["stance"] = val if val and val != "--" else "Orthodox"
            elif "DOB:" in text.upper():
                val = text.split(":")[-1].strip().strip("|").strip()
                data["dob"] = val if val and val != "--" else ""

        # Career stats box
        stat_boxes = soup.select("div.b-list__info-box-left li, div.b-list__info-box li")
        for box in stat_boxes:
            text = box.get_text(separator="|", strip=True)
            if "SLpM:" in text:
                data["slpm"] = _safe_float(text.split("SLpM:")[-1].strip("|").strip())
            elif "Str. Acc.:" in text:
                data["str_acc"] = _safe_float(text.split("Str. Acc.:")[-1].strip("|").strip())
            elif "SApM:" in text:
                data["sapm"] = _safe_float(text.split("SApM:")[-1].strip("|").strip())
            elif "Str. Def:" in text or "Str. Def.:" in text:
                val = text.split("Str. Def")[-1].replace(":", "").replace(".", "").strip("|").strip()
                data["str_def"] = _safe_float(val)
            elif "TD Avg.:" in text:
                data["td_avg"] = _safe_float(text.split("TD Avg.:")[-1].strip("|").strip())
            elif "TD Acc.:" in text:
                data["td_acc"] = _safe_float(text.split("TD Acc.:")[-1].strip("|").strip())
            elif "TD Def.:" in text:
                data["td_def"] = _safe_float(text.split("TD Def.:")[-1].strip("|").strip())
            elif "Sub. Avg.:" in text:
                data["sub_avg"] = _safe_float(text.split("Sub. Avg.:")[-1].strip("|").strip())

        # Defaults
        for key in ("height_inches", "reach_inches", "slpm", "str_acc", "sapm",
                     "str_def", "td_avg", "td_acc", "td_def", "sub_avg"):
            data.setdefault(key, 0.0)
        data.setdefault("stance", "Orthodox")
        data.setdefault("dob", "")
        data.setdefault("nickname", "")
        data.setdefault("weight_class", "")

        data["last_scraped"] = datetime.now().isoformat()
        data["raw_json"] = json.dumps(data, default=str)

        return data

    def scrape_fight_history(self, fighter_id: str, profile_url: str) -> List[Dict]:
        """Scrape fight-by-fight history from fighter detail page.
        
        ufcstats table columns (10 cols):
          [0] result (win/loss/draw/nc)
          [1] fighters (pipe-separated: "Fighter|Opponent")
          [2] KD (pipe: "0|0")
          [3] STR (pipe: "30|18")
          [4] TD (pipe: "4|0")
          [5] SUB (pipe: "0|0")
          [6] Event name|date
          [7] Method (pipe: "SUB|D'Arce Choke" or "U-DEC")
          [8] Round
          [9] Time
        """
        soup = self._get(profile_url)
        if not soup:
            return []

        fights = []
        table = soup.select_one("table.b-fight-details__table")
        if not table:
            return []

        # Get fighter's own name for splitting the fighters column
        fighter_rec = self.db.get_fighter(fighter_id)
        fighter_name = (fighter_rec["name"] if fighter_rec else "").lower()

        rows = table.select("tr.b-fight-details__table-row")[1:]  # skip header
        for row in rows:
            cols = row.select("td.b-fight-details__table-col")
            if len(cols) < 10:
                continue
            try:
                result_text = cols[0].get_text(strip=True).lower()

                # Col 1: fighters separated by pipe
                fighters_parts = [p.strip() for p in cols[1].get_text(separator="|", strip=True).split("|")]
                # Find opponent: the one that isn't us
                opponent = ""
                for part in fighters_parts:
                    if part.lower() != fighter_name and part.strip():
                        opponent = part
                        break
                if not opponent and len(fighters_parts) >= 2:
                    opponent = fighters_parts[1]

                # Col 2: KD (take first value = ours)
                kd_parts = cols[2].get_text(separator="|", strip=True).split("|")
                kd = _safe_int(kd_parts[0])

                # Col 3: STR
                sig_str = cols[3].get_text(separator="/", strip=True)

                # Col 4: TD
                td = cols[4].get_text(separator="/", strip=True)

                # Col 5: SUB
                sub_parts = cols[5].get_text(separator="|", strip=True).split("|")
                sub_att = _safe_int(sub_parts[0])

                # Col 6: Event|Date
                event_parts = [p.strip() for p in cols[6].get_text(separator="|", strip=True).split("|")]
                event_name = event_parts[0] if event_parts else ""
                event_date = event_parts[1] if len(event_parts) > 1 else ""

                # Col 7: Method (e.g. "SUB|D'Arce Choke" or "U-DEC" or "KO/TKO|Punch")
                method_parts = [p.strip() for p in cols[7].get_text(separator="|", strip=True).split("|")]
                method = method_parts[0] if method_parts else ""
                method_detail = method_parts[1] if len(method_parts) > 1 else ""

                # Col 8: Round
                rnd = _safe_int(cols[8].get_text(strip=True))

                # Col 9: Time
                fight_time = cols[9].get_text(strip=True)

                fight_data = {
                    "fighter_id": fighter_id,
                    "opponent_name": opponent,
                    "result": result_text,
                    "method": method,
                    "method_detail": method_detail,
                    "round": rnd,
                    "fight_time": fight_time,
                    "event_name": event_name,
                    "event_date": event_date,
                    "weight_class": "",
                    "kd": kd,
                    "sig_str": sig_str,
                    "sig_str_pct": 0.0,
                    "total_str": "",
                    "td": td,
                    "td_pct": 0.0,
                    "sub_att": sub_att,
                    "rev": 0,
                    "ctrl": "",
                }
                fights.append(fight_data)
            except Exception as e:
                logger.debug(f"Error parsing fight row: {e}")
                continue

        return fights

    def scrape_fighter(self, name: str, force: bool = False) -> Optional[Dict]:
        """
        Full pipeline: search → detail → fight history → cache.
        Returns fighter dict or None.
        """
        # Check cache first
        cached = self.db.find_fighter_by_name(name)
        if cached and not force and not self.db.is_stale(cached["fighter_id"]):
            logger.info(f"Using cached data for {name}")
            return cached

        # Search
        url = None
        if cached and cached.get("profile_url"):
            url = cached["profile_url"]
        else:
            url = self.search_fighter_url(name)

        if not url:
            logger.warning(f"Could not find fighter: {name}")
            return cached  # return stale data if we have it

        # Scrape detail
        data = self.scrape_fighter_detail(url)
        if not data:
            return cached

        self.db.upsert_fighter(data)

        # Scrape fight history
        fights = self.scrape_fight_history(data["fighter_id"], url)
        for f in fights:
            try:
                self.db.upsert_fight(f)
            except Exception as e:
                logger.debug(f"Fight upsert error: {e}")

        logger.info(f"Scraped {data['name']}: {data['record']} ({len(fights)} fights)")
        return data

    def scrape_upcoming_events(self) -> List[Dict]:
        """Scrape upcoming UFC events from ufcstats.com."""
        cached = self.db.cache_get("upcoming_events", max_age_hours=6)
        if cached:
            return json.loads(cached)

        soup = self._get(self.UPCOMING)
        if not soup:
            return []

        events = []
        rows = soup.select("tr.b-statistics__table-row")
        for row in rows:
            link = row.select_one("a.b-link")
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link.get("href", "")
            date_el = row.select_one("span.b-statistics__date")
            date_text = date_el.get_text(strip=True) if date_el else ""
            location_el = row.select_one("td:nth-child(2)")
            location = location_el.get_text(strip=True) if location_el else ""
            events.append({
                "name": name,
                "url": href,
                "date": date_text,
                "location": location,
            })

        self.db.cache_set("upcoming_events", json.dumps(events))
        return events

    def scrape_event_fights(self, event_url: str) -> List[Dict]:
        """Scrape fight card from an event page."""
        cached = self.db.cache_get(f"event:{event_url}", max_age_hours=6)
        if cached:
            return json.loads(cached)

        soup = self._get(event_url)
        if not soup:
            return []

        fights = []
        rows = soup.select("tr.b-fight-details__table-row")
        for row in rows:
            cols = row.select("td")
            if len(cols) < 2:
                continue
            # fighters are in links within the row
            links = row.select("a.b-link_style_black")
            if len(links) >= 2:
                f1 = links[0].get_text(strip=True)
                f2 = links[1].get_text(strip=True)
                weight_class_el = row.select_one("td.b-fight-details__table-col:nth-child(7)")
                wc = weight_class_el.get_text(strip=True) if weight_class_el else ""
                fights.append({
                    "fighter1": f1,
                    "fighter2": f2,
                    "weight_class": wc,
                })

        self.db.cache_set(f"event:{event_url}", json.dumps(fights))
        return fights


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scraper = UFCScraper()

    # Quick test
    print("=== Upcoming Events ===")
    events = scraper.scrape_upcoming_events()
    for e in events[:3]:
        print(f"  {e['name']} — {e['date']}")

    print("\n=== Test Fighter Scrape ===")
    for name in ["Islam Makhachev", "Jon Jones"]:
        data = scraper.scrape_fighter(name)
        if data:
            print(f"  {data['name']}: {data['record']} | SLpM: {data['slpm']} | TD Avg: {data['td_avg']}")
        else:
            print(f"  {name}: NOT FOUND")
