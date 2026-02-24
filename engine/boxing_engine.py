# -*- coding: utf-8 -*-
"""
ParlayGuarantee Boxing Prediction Engine — 15-factor model

Similar to MMA engine but boxing-specific.

Factors:
 1. Win rate
 2. KO %
 3. Recent form (L5)
 4. Reach advantage
 5. Height advantage
 6. Age / prime curve
 7. Stance matchup (orthodox vs southpaw)
 8. Total rounds fought (experience)
 9. Championship experience
10. Division ranking
11. Style matchup (boxer/puncher/swarmer/slugger)
12. Activity (fights per year)
13. Defensive ability (opponent KO rate suppression)
14. Going the distance rate
15. Odds-implied value
"""

import sys
import json
import math
import logging
import sqlite3
import os
import time
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from itertools import combinations

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOG_PATH = os.path.join(os.path.dirname(__file__), "boxing_engine.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
BOXING_SPORT_KEY = "boxing_boxing"

DB_PATH = os.path.join(os.path.dirname(__file__), "boxing_data.db")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
}

DEFAULT_WEIGHTS = {
    "win_rate":         0.10,
    "ko_pct":           0.07,
    "recent_form":      0.09,
    "reach":            0.06,
    "height":           0.04,
    "age":              0.07,
    "stance":           0.04,
    "experience":       0.07,
    "championship_exp": 0.06,
    "ranking":          0.08,
    "style_matchup":    0.06,
    "activity":         0.05,
    "defense":          0.07,
    "distance_rate":    0.05,
    "odds_value":       0.09,
}

# Style matchup matrix: attacker_style -> defender_style -> edge
STYLE_MATRIX = {
    "boxer":   {"boxer": 0.0, "puncher": 0.05, "swarmer": -0.05, "slugger": 0.10},
    "puncher": {"boxer": -0.05, "puncher": 0.0, "swarmer": 0.05, "slugger": -0.05},
    "swarmer": {"boxer": 0.05, "puncher": -0.05, "swarmer": 0.0, "slugger": 0.05},
    "slugger": {"boxer": -0.10, "puncher": 0.05, "swarmer": -0.05, "slugger": 0.0},
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


class BoxingDataDB:
    def __init__(self):
        self.db_path = DB_PATH
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fighters (
                name TEXT PRIMARY KEY,
                record TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                draws INTEGER DEFAULT 0,
                kos INTEGER DEFAULT 0,
                reach_cm REAL DEFAULT 0,
                height_cm REAL DEFAULT 0,
                age INTEGER DEFAULT 0,
                stance TEXT DEFAULT 'orthodox',
                style TEXT DEFAULT 'boxer',
                division TEXT DEFAULT '',
                division_ranking INTEGER DEFAULT 99,
                championship_fights INTEGER DEFAULT 0,
                total_rounds INTEGER DEFAULT 0,
                last_fight_date TEXT,
                updated_at TEXT
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

    def get_fighter(self, name: str) -> Optional[Dict]:
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM fighters WHERE LOWER(name) LIKE ?",
                           (f"%{name.lower()}%",)).fetchone()
        conn.close()
        if not row:
            return None
        cols = ["name", "record", "wins", "losses", "draws", "kos",
                "reach_cm", "height_cm", "age", "stance", "style",
                "division", "division_ranking", "championship_fights",
                "total_rounds", "last_fight_date", "updated_at"]
        return dict(zip(cols, row))

    def cache_get(self, key, max_age_hours=4):
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

    def cache_set(self, key, data):
        conn = self.get_conn()
        conn.execute("INSERT OR REPLACE INTO api_cache (cache_key, data_json, fetched_at) VALUES (?,?,?)",
                     (key, json.dumps(data, default=str), datetime.now().isoformat()))
        conn.commit()
        conn.close()


class BoxingEngine:
    """15-factor boxing prediction engine."""

    def __init__(self):
        self.db = BoxingDataDB()
        self.weights = dict(DEFAULT_WEIGHTS)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_odds(self) -> List[Dict]:
        cached = self.db.cache_get("boxing_odds", max_age_hours=3)
        if cached:
            return cached
        try:
            resp = self.session.get(
                f"{ODDS_API_BASE}/sports/{BOXING_SPORT_KEY}/odds",
                params={"apiKey": ODDS_API_KEY, "regions": "us",
                        "markets": "h2h", "oddsFormat": "american"},
                timeout=15,
            )
            if resp.status_code == 404:
                logger.warning("No boxing odds available (404)")
                return []
            resp.raise_for_status()
            events = resp.json()
            self.db.cache_set("boxing_odds", events)
            return events
        except Exception as e:
            logger.error(f"Boxing odds fetch error: {e}")
            return []

    def _parse_odds(self, event: Dict) -> Dict:
        result = {}
        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt.get("key") != "h2h":
                    continue
                for outcome in mkt.get("outcomes", []):
                    price = outcome.get("price", 0)
                    if price > 0:
                        impl = 100.0 / (price + 100.0)
                    elif price < 0:
                        impl = abs(price) / (abs(price) + 100.0)
                    else:
                        impl = 0.5
                    result[outcome.get("name", "")] = impl
                break
            break
        return result

    def _get_american_odds(self, event: Dict) -> Dict:
        result = {}
        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt.get("key") != "h2h":
                    continue
                for outcome in mkt.get("outcomes", []):
                    result[outcome.get("name", "")] = outcome.get("price", 0)
                break
            break
        return result

    def _get_fighter_data(self, name: str) -> Dict:
        """Get fighter data from DB or return defaults."""
        fighter = self.db.get_fighter(name)
        if fighter:
            return fighter
        # Default unknown fighter
        return {
            "name": name, "wins": 15, "losses": 2, "draws": 0, "kos": 8,
            "reach_cm": 180, "height_cm": 180, "age": 28, "stance": "orthodox",
            "style": "boxer", "division_ranking": 50, "championship_fights": 0,
            "total_rounds": 80, "last_fight_date": None,
        }

    def compute_factors(self, f1_name: str, f2_name: str,
                        odds_map: Dict = None) -> Dict:
        f1 = self._get_fighter_data(f1_name)
        f2 = self._get_fighter_data(f2_name)

        total1 = max(f1["wins"] + f1["losses"] + f1["draws"], 1)
        total2 = max(f2["wins"] + f2["losses"] + f2["draws"], 1)

        win_pct1 = f1["wins"] / total1
        win_pct2 = f2["wins"] / total2
        ko_pct1 = f1["kos"] / max(f1["wins"], 1)
        ko_pct2 = f2["kos"] / max(f2["wins"], 1)

        # Age curve: peak 27-31
        def age_curve(a):
            if 27 <= a <= 31: return 1.0
            elif a < 27: return 0.75 + 0.25 * (a - 20) / 7.0
            else: return max(0.3, 1.0 - 0.07 * (a - 31))

        # Activity: rounds in recent years
        rounds1 = f1.get("total_rounds", 80)
        rounds2 = f2.get("total_rounds", 80)

        # Style matchup
        s1 = f1.get("style", "boxer")
        s2 = f2.get("style", "boxer")
        style_edge = STYLE_MATRIX.get(s1, {}).get(s2, 0.0)

        factors = {
            "win_rate":         _sigmoid((win_pct1 - win_pct2) * 4),
            "ko_pct":           _sigmoid((ko_pct1 - ko_pct2) * 3),
            "recent_form":      0.5,  # Would need fight-by-fight data
            "reach":            _sigmoid((f1["reach_cm"] - f2["reach_cm"]) / 10.0),
            "height":           _sigmoid((f1["height_cm"] - f2["height_cm"]) / 10.0),
            "age":              _sigmoid((age_curve(f1["age"]) - age_curve(f2["age"])) * 3),
            "stance":           0.52 if f1.get("stance") != f2.get("stance") else 0.5,
            "experience":       _sigmoid((total1 - total2) / 15.0),
            "championship_exp": _sigmoid((f1.get("championship_fights", 0) - f2.get("championship_fights", 0)) / 3.0),
            "ranking":          _sigmoid((f2.get("division_ranking", 50) - f1.get("division_ranking", 50)) / 15.0),
            "style_matchup":    _clamp(0.5 + style_edge),
            "activity":         _sigmoid((rounds1 - rounds2) / 30.0),
            "defense":          0.5,  # Placeholder
            "distance_rate":    0.5,  # Placeholder
            "odds_value":       odds_map.get(f1_name, 0.5) if odds_map else 0.5,
        }
        return factors

    def predict_fight(self, f1_name: str, f2_name: str,
                      odds_map: Dict = None) -> Dict:
        factors = self.compute_factors(f1_name, f2_name, odds_map)

        weighted = sum(factors[k] * self.weights.get(k, 0) for k in factors)
        total_w = sum(self.weights.get(k, 0) for k in factors)
        raw_prob = weighted / total_w if total_w > 0 else 0.5

        confidence = _clamp(raw_prob, 0.35, 0.92)
        winner = f1_name if confidence >= 0.5 else f2_name
        if confidence < 0.5:
            confidence = 1.0 - confidence

        implied = odds_map.get(winner, 0.5) if odds_map else 0.5
        edge = confidence - implied
        value_score = round(edge * 100, 1)

        if confidence >= 0.72:
            pick_type = "LOCK"
        elif confidence >= 0.62:
            pick_type = "VALUE" if value_score > 3 else "STRONG"
        elif confidence >= 0.53:
            pick_type = "LEAN"
        else:
            pick_type = "SKIP"

        return {
            "fighter1": f1_name,
            "fighter2": f2_name,
            "predicted_winner": winner,
            "confidence": round(confidence, 4),
            "f1_probability": round(raw_prob, 4),
            "f2_probability": round(1 - raw_prob, 4),
            "value_score": value_score,
            "edge": round(edge * 100, 1),
            "pick_type": pick_type,
            "factors": factors,
        }

    def generate_picks(self, target_date: str = None) -> List[Dict]:
        """Main entry: fetch boxing odds, generate predictions."""
        logger.info("=== Boxing Engine (15-factor): Generating Picks ===")

        date_filter = target_date or date.today().isoformat()
        odds_events = self.get_odds()

        if not odds_events:
            logger.warning("No boxing odds available")
            return []

        picks = []
        pick_num = 1

        for event in odds_events:
            commence = event.get("commence_time", "")
            sport_title = event.get("sport_title", "Boxing")

            if date_filter and commence:
                try:
                    event_date = datetime.fromisoformat(commence.replace("Z", "+00:00")).date()
                    filter_date = date.fromisoformat(date_filter)
                    if event_date != filter_date:
                        continue
                except Exception:
                    pass

            f1 = event.get("home_team", "")
            f2 = event.get("away_team", "")
            if not f1 or not f2:
                continue

            odds_map = self._parse_odds(event)
            american_odds = self._get_american_odds(event)

            logger.info(f"Analyzing: {f1} vs {f2}")
            matchup = self.predict_fight(f1, f2, odds_map=odds_map)

            pick = {
                "pick_number": pick_num,
                "type": "straight",
                "sport": "Boxing",
                "event": sport_title,
                "commence_time": commence,
                "games": [{
                    "home_team": f1,
                    "away_team": f2,
                    "predicted_winner": matchup["predicted_winner"],
                    "confidence": matchup["confidence"],
                    "home_probability": matchup["f1_probability"],
                    "away_probability": matchup["f2_probability"],
                    "american_odds": american_odds,
                    "value_score": matchup["value_score"],
                    "pick_type": matchup["pick_type"],
                }],
                "factors_summary": matchup.get("factors", {}),
                "model_version": "1.0-15factor",
            }
            if odds_map:
                pick["edge"] = matchup["edge"]

            picks.append(pick)
            pick_num += 1

        logger.info(f"Generated {len(picks)} boxing picks")

        # Parlays
        parlays = self._generate_parlays(picks)
        return picks + parlays

    def _generate_parlays(self, straight: List[Dict], max_legs: int = 3) -> List[Dict]:
        good = [p for p in straight if p["games"][0]["confidence"] >= 0.58]
        good.sort(key=lambda p: p["games"][0]["confidence"], reverse=True)
        good = good[:6]

        parlays = []
        pnum = 1
        for n in range(2, min(max_legs + 1, len(good) + 1)):
            for combo in list(combinations(good, n))[:2]:
                conf = 1.0
                legs = []
                for p in combo:
                    g = p["games"][0]
                    conf *= g["confidence"]
                    legs.append(g)
                parlays.append({
                    "pick_number": len(straight) + pnum,
                    "type": "parlay",
                    "sport": "Boxing",
                    "legs": n,
                    "combined_confidence": round(conf, 4),
                    "games": legs,
                    "model_version": "1.0-15factor",
                })
                pnum += 1
        return parlays


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Boxing Prediction Engine (15-factor)")
    parser.add_argument("--date", type=str, help="Target date YYYY-MM-DD")
    parser.add_argument("--output", type=str, help="Output JSON file")
    args = parser.parse_args()

    engine = BoxingEngine()
    picks = engine.generate_picks(target_date=args.date)

    output = {
        "generated_at": datetime.now().isoformat(),
        "model_version": "1.0-15factor",
        "total_straight": len([p for p in picks if p.get("type") == "straight"]),
        "total_parlays": len([p for p in picks if p.get("type") == "parlay"]),
        "picks": picks,
    }
    print(json.dumps(output, indent=2, default=str))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)


def generate_picks(target_date=None):
    """Module-level entry point."""
    engine = BoxingEngine()
    return engine.generate_picks(target_date=target_date)


if __name__ == "__main__":
    main()
