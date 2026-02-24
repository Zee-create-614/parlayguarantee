"""
ParlayGuarantee MMA Prediction Engine — v2.0 (32-factor model)

Factors:
 1. Win rate differential
 2. Finish rate (KO + Sub)
 3. Recent form (last 5 fights)
 4. Win/loss streak momentum
 5. Striking volume differential (SLpM)
 6. Striking accuracy differential
 7. Striking defense differential
 8. Striking absorption rate
 9. Takedown offense differential
10. Takedown defense differential
11. Grappling advantage (sub avg)
12. Reach advantage
13. Height advantage
14. Stance matchup edge
15. Age factor / decline curve
16. Days since last fight (ring rust)
17. Experience differential (total fights)
18. Title fight adjustment (5 rounds)
19. Betting line value (model vs implied odds)
20. Method probability distribution
21. KO power factor (KO rate + knockdowns)
22. Cardio / late-fight factor
23. Missed weight history
24. Short notice / replacement fighter
25. Cage size (Apex vs arena)
26. Round prediction (avg fight time)
27. Judge scoring tendency (placeholder)
28. Fighter style classification
29. Style matchup matrix
30. Championship round experience
31. Comeback factor (win after loss)
32. Divisional ranking differential
"""

import sys
import json
import math
import logging
import sqlite3
import requests
import random
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from itertools import combinations

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mma_scraper import UFCScraper, MMADataDB, _safe_float

# Logging
LOG_PATH = Path(__file__).parent / "mma_engine.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# ── Factor weights (tuned starting points) ──
DEFAULT_WEIGHTS = {
    "win_rate":          0.10,
    "finish_rate":       0.04,
    "recent_form":       0.09,
    "streak":            0.04,
    "striking_volume":   0.06,
    "striking_accuracy": 0.05,
    "striking_defense":  0.06,
    "striking_absorbed": 0.04,
    "td_offense":        0.05,
    "td_defense":        0.05,
    "grappling":         0.04,
    "reach":             0.03,
    "height":            0.02,
    "stance":            0.02,
    "age":               0.04,
    "ring_rust":         0.03,
    "experience":        0.03,
    "title_fight":       0.02,
    "odds_value":        0.03,
    "ko_power":          0.03,
    "cardio":            0.02,
    # New factors (23-32)
    "missed_weight":     0.02,
    "short_notice":      0.02,
    "cage_size":         0.01,
    "style_matchup":     0.04,
    "championship_exp":  0.02,
    "comeback":          0.03,
    "ranking":           0.03,
    "judge_tendency":    0.01,
}

# Stance matchup edges (small empirical biases)
STANCE_EDGE = {
    ("Orthodox", "Southpaw"): -0.02,
    ("Southpaw", "Orthodox"):  0.02,
    ("Switch", "Orthodox"):    0.01,
    ("Switch", "Southpaw"):    0.01,
}

# Style matchup matrix — historical approximate edges
# Key: (winner_style, loser_style) → edge magnitude
STYLE_MATRIX = {
    ("Wrestler", "Striker"):      0.08,   # wrestlers beat strikers ~58%
    ("Grappler", "Wrestler"):     0.02,   # grapplers beat wrestlers ~52%
    ("Striker", "Grappler"):      0.05,   # strikers beat grapplers ~55%
    ("Well-Rounded", "Striker"):  0.04,
    ("Well-Rounded", "Wrestler"): 0.03,
    ("Well-Rounded", "Grappler"): 0.04,
}

# UFC Apex events (smaller cage — 25ft octagon)
APEX_KEYWORDS = ["apex", "ufc fight night", "vegas"]
ARENA_CAGE_FT = 30
APEX_CAGE_FT = 25


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


class MMAEngine:
    """Production MMA prediction engine with 32 factors."""

    def __init__(self, weights: Dict = None):
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.db = MMADataDB()
        self.scraper = UFCScraper(self.db)

    # ──────────────────────────────────────────────
    #  Data fetching
    # ──────────────────────────────────────────────

    def get_fighter_stats(self, name: str, force: bool = False) -> Optional[Dict]:
        return self.scraper.scrape_fighter(name, force=force)

    def get_fight_history(self, fighter_id: str) -> List[Dict]:
        return self.db.get_fight_history(fighter_id)

    def get_odds(self, sport: str = "mma_mixed_martial_arts") -> List[Dict]:
        cached = self.db.cache_get(f"odds:{sport}", max_age_hours=1)
        if cached:
            return json.loads(cached)
        url = f"{ODDS_API_BASE}/sports/{sport}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "american",
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.db.cache_set(f"odds:{sport}", json.dumps(data))
            logger.info(f"Fetched {len(data)} events from Odds API ({sport})")
            return data
        except Exception as e:
            logger.error(f"Odds API error: {e}")
            return []

    # ──────────────────────────────────────────────
    #  Style classification (Factor 28)
    # ──────────────────────────────────────────────

    def classify_style(self, fighter: Dict, history: List[Dict]) -> str:
        """Classify fighter as Striker / Wrestler / Grappler / Well-Rounded."""
        slpm = fighter.get("slpm", 0) or 0
        td_avg = fighter.get("td_avg", 0) or 0
        sub_avg = fighter.get("sub_avg", 0) or 0

        total_activity = slpm + td_avg * 2 + sub_avg * 3
        if total_activity == 0:
            return "Well-Rounded"

        strike_ratio = slpm / max(total_activity, 0.01)
        td_ratio = (td_avg * 2) / max(total_activity, 0.01)
        sub_ratio = (sub_avg * 3) / max(total_activity, 0.01)

        if strike_ratio > 0.6 and td_ratio < 0.2:
            return "Striker"
        elif td_ratio > 0.35 and sub_ratio < 0.2:
            return "Wrestler"
        elif sub_ratio > 0.25 or (sub_avg > 1.0 and td_ratio > 0.2):
            return "Grappler"
        else:
            return "Well-Rounded"

    # ──────────────────────────────────────────────
    #  New factor helpers (23-32)
    # ──────────────────────────────────────────────

    def _missed_weight_score(self, history: List[Dict]) -> float:
        """Count missed weight occurrences in fight history (approximation:
        look for 'catchweight' or significant weight-class changes)."""
        missed = 0
        for fight in history:
            method = (fight.get("method") or "").lower()
            event = (fight.get("event_name") or "").lower()
            wc = (fight.get("weight_class") or "").lower()
            if "catchweight" in wc or "catchweight" in event:
                missed += 1
            # Overweight penalty is sometimes noted in method_detail
            detail = (fight.get("method_detail") or "").lower()
            if "overweight" in detail or "missed weight" in detail:
                missed += 1
        # Normalize: 0 = clean, 1 = chronic weight misser
        return min(missed / 3.0, 1.0)

    def _short_notice_score(self, fighter_name: str, event_name: str) -> float:
        """Placeholder: short-notice replacements are hard to detect from stats alone.
        Returns 0 (normal camp). Override externally if known."""
        # Could be enhanced with news API integration
        return 0.0

    def _cage_size_factor(self, event_name: str, style1: str, style2: str) -> float:
        """Smaller cage favors pressure fighters (wrestlers, grapplers).
        Returns positive if f1 benefits, negative if f2 benefits."""
        is_apex = any(kw in (event_name or "").lower() for kw in APEX_KEYWORDS)
        if not is_apex:
            return 0.0

        # Smaller cage benefits: Wrestlers > Grapplers > Well-Rounded > Strikers
        cage_benefit = {"Wrestler": 0.06, "Grappler": 0.04, "Well-Rounded": 0.01, "Striker": -0.04}
        b1 = cage_benefit.get(style1, 0)
        b2 = cage_benefit.get(style2, 0)
        return _clamp(b1 - b2, -0.5, 0.5)

    def _predict_round(self, h1: List[Dict], h2: List[Dict], is_title: bool = False) -> Dict:
        """Predict what round the fight ends and average fight duration."""
        times1 = self._extract_fight_times(h1)
        times2 = self._extract_fight_times(h2)
        all_times = times1 + times2

        if not all_times:
            return {"predicted_round": 3 if is_title else 2, "avg_seconds": 600, "goes_distance_prob": 0.4}

        avg_secs = sum(all_times) / len(all_times)
        # How often do their fights go to decision?
        dec_count = sum(1 for f in h1 + h2 if "dec" in (f.get("method") or "").lower())
        total_fights = max(len(h1) + len(h2), 1)
        dec_rate = dec_count / total_fights

        total_rounds = 5 if is_title else 3
        round_time = 300  # 5 min per round

        if avg_secs <= round_time:
            predicted_round = 1
        elif avg_secs <= round_time * 2:
            predicted_round = 2
        elif avg_secs <= round_time * 3:
            predicted_round = 3
        elif is_title and avg_secs <= round_time * 4:
            predicted_round = 4
        else:
            predicted_round = total_rounds

        return {
            "predicted_round": predicted_round,
            "avg_seconds": round(avg_secs),
            "goes_distance_prob": round(dec_rate, 3),
            "total_rounds": total_rounds,
        }

    def _extract_fight_times(self, history: List[Dict]) -> List[float]:
        """Convert fight history rounds+time to total seconds."""
        times = []
        for f in history:
            rnd = f.get("round", 0) or 0
            time_str = f.get("fight_time", "") or ""
            if rnd and time_str:
                try:
                    parts = time_str.split(":")
                    mins = int(parts[0]) if len(parts) >= 1 else 0
                    secs = int(parts[1]) if len(parts) >= 2 else 0
                    total = (rnd - 1) * 300 + mins * 60 + secs
                    times.append(total)
                except (ValueError, IndexError):
                    pass
        return times

    def _championship_experience(self, history: List[Dict]) -> float:
        """Has the fighter been in 5-round fights before?"""
        five_rounders = 0
        for f in history:
            rnd = f.get("round", 0) or 0
            event = (f.get("event_name") or "").lower()
            # If they went 4+ rounds or it was a title/main event
            if rnd >= 4:
                five_rounders += 1
            elif any(kw in event for kw in ("title", "championship")):
                five_rounders += 1
        return min(five_rounders / 3.0, 1.0)

    def _comeback_factor(self, history: List[Dict]) -> float:
        """How well does the fighter perform after a loss?
        Positive = strong comeback fighter. Negative = tends to spiral."""
        if len(history) < 2:
            return 0.0
        comebacks = 0
        spirals = 0
        for i in range(len(history) - 1):
            if history[i + 1].get("result", "").lower().startswith("l"):
                # Fight after a loss
                if history[i].get("result", "").lower().startswith("w"):
                    comebacks += 1
                elif history[i].get("result", "").lower().startswith("l"):
                    spirals += 1
        total = comebacks + spirals
        if total == 0:
            return 0.0
        return (comebacks - spirals) / max(total, 1)

    def _ranking_factor(self, f1: Dict, f2: Dict) -> float:
        """Ranked vs unranked edge. Approximate from win rate + experience."""
        # True ranking requires external data. Approximate using record quality.
        def rank_score(fighter, history):
            wins = fighter.get("wins", 0)
            total = wins + fighter.get("losses", 0)
            if total < 5:
                return 0.3
            wr = wins / max(total, 1)
            # Bonus for beating fighters with good records (not available, so use win count)
            exp_bonus = min(total / 30, 0.3)
            return wr * 0.7 + exp_bonus
        # We don't have history here, but factors are computed in _compute_factors
        s1 = rank_score(f1, [])
        s2 = rank_score(f2, [])
        return _clamp((s1 - s2) * 2, -1, 1)

    # ──────────────────────────────────────────────
    #  Factor calculations (all 32)
    # ──────────────────────────────────────────────

    def _compute_factors(self, f1: Dict, f2: Dict,
                         h1: List[Dict], h2: List[Dict],
                         is_title: bool = False,
                         odds_implied: Dict = None,
                         event_name: str = "") -> Dict:
        """Compute all 32 factors. Positive = f1 edge."""
        factors = {}

        total1 = max(f1.get("wins", 0) + f1.get("losses", 0) + f1.get("draws", 0), 1)
        total2 = max(f2.get("wins", 0) + f2.get("losses", 0) + f2.get("draws", 0), 1)
        wr1 = f1.get("wins", 0) / total1
        wr2 = f2.get("wins", 0) / total2

        # 1. Win rate
        factors["win_rate"] = (wr1 - wr2) * 2

        # 2. Finish rate
        fr1 = self._finish_rate(h1)
        fr2 = self._finish_rate(h2)
        factors["finish_rate"] = (fr1 - fr2) * 1.5

        # 3. Recent form (last 5)
        rf1 = self._recent_form(h1, n=5)
        rf2 = self._recent_form(h2, n=5)
        factors["recent_form"] = (rf1 - rf2) * 2

        # 4. Streak
        s1 = self._streak(h1)
        s2 = self._streak(h2)
        factors["streak"] = _clamp((s1 - s2) / 5, -1, 1)

        # 5-8. Striking
        factors["striking_volume"] = _clamp((f1.get("slpm", 0) - f2.get("slpm", 0)) / 3, -1, 1)
        factors["striking_accuracy"] = _clamp((f1.get("str_acc", 0) - f2.get("str_acc", 0)) / 30, -1, 1)
        factors["striking_defense"] = _clamp((f1.get("str_def", 0) - f2.get("str_def", 0)) / 30, -1, 1)
        factors["striking_absorbed"] = _clamp((f2.get("sapm", 0) - f1.get("sapm", 0)) / 3, -1, 1)

        # 9-11. Grappling
        factors["td_offense"] = _clamp((f1.get("td_avg", 0) - f2.get("td_avg", 0)) / 3, -1, 1)
        factors["td_defense"] = _clamp((f1.get("td_def", 0) - f2.get("td_def", 0)) / 30, -1, 1)
        factors["grappling"] = _clamp((f1.get("sub_avg", 0) - f2.get("sub_avg", 0)) / 2, -1, 1)

        # 12-13. Physical
        r1 = f1.get("reach_inches", 0) or 0
        r2 = f2.get("reach_inches", 0) or 0
        factors["reach"] = _clamp((r1 - r2) / 6, -1, 1)
        h1_in = f1.get("height_inches", 0) or 0
        h2_in = f2.get("height_inches", 0) or 0
        factors["height"] = _clamp((h1_in - h2_in) / 5, -1, 1)

        # 14. Stance
        st1 = (f1.get("stance") or "Orthodox").title()
        st2 = (f2.get("stance") or "Orthodox").title()
        factors["stance"] = STANCE_EDGE.get((st1, st2), 0.0)

        # 15. Age
        age1 = self._fighter_age(f1)
        age2 = self._fighter_age(f2)
        factors["age"] = self._age_factor(age1, age2)

        # 16. Ring rust
        days1 = self._days_since_last(h1)
        days2 = self._days_since_last(h2)
        factors["ring_rust"] = self._ring_rust_factor(days1, days2)

        # 17. Experience
        factors["experience"] = _clamp((total1 - total2) / 15, -1, 1)

        # 18. Title fight
        if is_title:
            exp_edge = _clamp((total1 - total2) / 20, -0.3, 0.3)
            factors["title_fight"] = exp_edge
        else:
            factors["title_fight"] = 0.0

        # 19. Odds value (computed after initial score)
        if odds_implied:
            model_raw = sum(factors.get(k, 0) * self.weights.get(k, 0)
                            for k in factors if k in self.weights)
            model_prob = _sigmoid(model_raw * 3)
            implied1 = odds_implied.get("f1_implied", 0.5)
            factors["odds_value"] = _clamp((model_prob - implied1) * 2, -1, 1)
        else:
            factors["odds_value"] = 0.0

        # 20/21. KO power & Cardio
        ko1 = self._ko_rate(h1)
        ko2 = self._ko_rate(h2)
        factors["ko_power"] = _clamp((ko1 - ko2) * 1.5, -1, 1)
        c1 = self._cardio_score(f1, h1)
        c2 = self._cardio_score(f2, h2)
        factors["cardio"] = _clamp((c1 - c2) * 2, -1, 1)

        # ── NEW FACTORS (23-32) ──

        # 23. Missed weight
        mw1 = self._missed_weight_score(h1)
        mw2 = self._missed_weight_score(h2)
        factors["missed_weight"] = _clamp((mw2 - mw1) * 2, -1, 1)  # opponent missing = your edge

        # 24. Short notice (placeholder — 0 unless externally set)
        factors["short_notice"] = 0.0

        # 25. Cage size
        style1 = self.classify_style(f1, h1)
        style2 = self.classify_style(f2, h2)
        factors["cage_size"] = self._cage_size_factor(event_name, style1, style2)

        # 27. Judge tendency (placeholder — needs MMA Decisions data)
        factors["judge_tendency"] = 0.0

        # 28-29. Style matchup
        style_edge = STYLE_MATRIX.get((style1, style2), 0.0) - STYLE_MATRIX.get((style2, style1), 0.0)
        factors["style_matchup"] = _clamp(style_edge * 3, -1, 1)

        # 30. Championship round experience
        ce1 = self._championship_experience(h1)
        ce2 = self._championship_experience(h2)
        if is_title:
            factors["championship_exp"] = _clamp((ce1 - ce2) * 2, -1, 1)
        else:
            factors["championship_exp"] = _clamp((ce1 - ce2) * 0.5, -1, 1)

        # 31. Comeback factor
        cb1 = self._comeback_factor(h1)
        cb2 = self._comeback_factor(h2)
        # Weight more if fighter is coming off a loss
        is_f1_off_loss = len(h1) > 0 and h1[0].get("result", "").lower().startswith("l")
        is_f2_off_loss = len(h2) > 0 and h2[0].get("result", "").lower().startswith("l")
        cb_raw = (cb1 - cb2)
        if is_f1_off_loss:
            cb_raw += 0.1 * cb1  # boost if good comeback fighter and coming off loss
        if is_f2_off_loss:
            cb_raw -= 0.1 * cb2
        factors["comeback"] = _clamp(cb_raw, -1, 1)

        # 32. Ranking (approximated)
        factors["ranking"] = self._ranking_factor(f1, f2)

        return factors

    # ── Helper factor computations ──

    def _finish_rate(self, history: List[Dict]) -> float:
        wins = [f for f in history if f.get("result", "").lower().startswith("w")]
        if not wins:
            return 0.0
        finishes = [f for f in wins if any(k in (f.get("method") or "").upper()
                    for k in ("KO", "TKO", "SUB", "SUBMISSION"))]
        return len(finishes) / len(wins)

    def _recent_form(self, history: List[Dict], n: int = 5) -> float:
        recent = history[:n]
        if not recent:
            return 0.5
        wins = sum(1 for f in recent if f.get("result", "").lower().startswith("w"))
        return wins / len(recent)

    def _streak(self, history: List[Dict]) -> int:
        streak = 0
        for f in history:
            r = f.get("result", "").lower()
            if r.startswith("w"):
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif r.startswith("l"):
                if streak <= 0:
                    streak -= 1
                else:
                    break
            else:
                break
        return streak

    def _ko_rate(self, history: List[Dict]) -> float:
        wins = [f for f in history if f.get("result", "").lower().startswith("w")]
        if not wins:
            return 0.0
        kos = [f for f in wins if any(k in (f.get("method") or "").upper() for k in ("KO", "TKO"))]
        return len(kos) / len(wins)

    def _fighter_age(self, fighter: Dict) -> float:
        dob = fighter.get("dob", "")
        if not dob or dob == "--":
            return 30.0
        try:
            for fmt in ("%b %d, %Y", "%Y-%m-%d", "%B %d, %Y"):
                try:
                    born = datetime.strptime(dob.strip(), fmt)
                    return (datetime.now() - born).days / 365.25
                except ValueError:
                    continue
            return 30.0
        except Exception:
            return 30.0

    def _age_factor(self, age1: float, age2: float) -> float:
        def prime_score(age):
            if 28 <= age <= 33:
                return 1.0
            elif age < 28:
                return 0.8 + 0.2 * (age - 22) / 6
            else:
                return max(0.2, 1.0 - (age - 33) * 0.08)
        return _clamp((prime_score(age1) - prime_score(age2)) * 3, -1, 1)

    def _days_since_last(self, history: List[Dict]) -> int:
        if not history:
            return 999
        for f in history:
            d = f.get("event_date", "")
            if d:
                try:
                    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%B %d, %Y"):
                        try:
                            dt = datetime.strptime(d.strip(), fmt)
                            return (datetime.now() - dt).days
                        except ValueError:
                            continue
                except Exception:
                    pass
        return 365

    def _ring_rust_factor(self, days1: int, days2: int) -> float:
        def activity_score(days):
            if 60 <= days <= 180:
                return 1.0
            elif days < 60:
                return 0.85
            elif days <= 365:
                return max(0.5, 1.0 - (days - 180) / 400)
            else:
                return 0.4
        return _clamp((activity_score(days1) - activity_score(days2)) * 3, -1, 1)

    def _cardio_score(self, fighter: Dict, history: List[Dict]) -> float:
        sapm = fighter.get("sapm", 3.0)
        absorp_score = max(0, 1 - sapm / 6)
        dec_wins = sum(1 for f in history if f.get("result", "").lower().startswith("w")
                       and "dec" in (f.get("method") or "").lower())
        total_wins = max(1, sum(1 for f in history if f.get("result", "").lower().startswith("w")))
        dec_rate = dec_wins / total_wins
        return (absorp_score * 0.6 + dec_rate * 0.4)

    # ──────────────────────────────────────────────
    #  Prediction
    # ──────────────────────────────────────────────

    def predict_method(self, f1: Dict, f2: Dict,
                       h1: List[Dict] = None, h2: List[Dict] = None) -> Dict:
        if h1 is None:
            h1 = self.get_fight_history(f1["fighter_id"])
        if h2 is None:
            h2 = self.get_fight_history(f2["fighter_id"])

        ko1 = self._ko_rate(h1)
        ko2 = self._ko_rate(h2)
        avg_ko = (ko1 + ko2) / 2
        slpm_avg = (f1.get("slpm", 3) + f2.get("slpm", 3)) / 2
        ko_adj = avg_ko * (0.7 + 0.3 * min(slpm_avg / 5, 1))

        sub1 = f1.get("sub_avg", 0)
        sub2 = f2.get("sub_avg", 0)
        sub_rate1 = sum(1 for f in h1 if f.get("result", "").lower().startswith("w")
                        and "sub" in (f.get("method") or "").lower())
        sub_rate2 = sum(1 for f in h2 if f.get("result", "").lower().startswith("w")
                        and "sub" in (f.get("method") or "").lower())
        total_wins = max(1, sum(1 for f in h1 + h2 if f.get("result", "").lower().startswith("w")))
        sub_prob = (sub_rate1 + sub_rate2) / total_wins
        sub_prob = min(sub_prob, 0.4)

        dec_prob = max(0.15, 1.0 - ko_adj - sub_prob)

        total = ko_adj + sub_prob + dec_prob
        ko_adj /= total
        sub_prob /= total
        dec_prob /= total

        probs = {
            "KO/TKO": round(ko_adj, 3),
            "Submission": round(sub_prob, 3),
            "Decision": round(dec_prob, 3),
        }
        probs["most_likely"] = max(probs, key=lambda k: probs[k] if k != "most_likely" else 0)
        return probs

    def calculate_matchup(self, fighter1: str, fighter2: str,
                          is_title: bool = False,
                          odds_implied: Dict = None,
                          event_name: str = "") -> Dict:
        """Full matchup analysis between two fighters."""
        f1 = self.get_fighter_stats(fighter1)
        f2 = self.get_fighter_stats(fighter2)

        if not f1 or not f2:
            missing = []
            if not f1:
                missing.append(fighter1)
            if not f2:
                missing.append(fighter2)
            logger.warning(f"Missing fighter data: {missing}")
            return self._default_matchup(fighter1, fighter2)

        h1 = self.get_fight_history(f1["fighter_id"])
        h2 = self.get_fight_history(f2["fighter_id"])

        factors = self._compute_factors(f1, f2, h1, h2, is_title, odds_implied, event_name)

        raw_score = sum(factors.get(k, 0) * self.weights.get(k, 0) for k in self.weights)
        f1_prob = _sigmoid(raw_score * 4)
        f1_prob = _clamp(f1_prob, 0.10, 0.90)
        f2_prob = 1 - f1_prob

        method = self.predict_method(f1, f2, h1, h2)
        round_pred = self._predict_round(h1, h2, is_title)
        style1 = self.classify_style(f1, h1)
        style2 = self.classify_style(f2, h2)

        confidence = max(f1_prob, f2_prob) * 100
        predicted_winner = f1["name"] if f1_prob > 0.5 else f2["name"]

        return {
            "fighter1": f1["name"],
            "fighter2": f2["name"],
            "predicted_winner": predicted_winner,
            "confidence": round(confidence, 1),
            "f1_probability": round(f1_prob, 4),
            "f2_probability": round(f2_prob, 4),
            "method_prediction": method["most_likely"],
            "method_probs": method,
            "round_prediction": round_pred,
            "fighter1_style": style1,
            "fighter2_style": style2,
            "factors": {k: round(v, 4) for k, v in factors.items()},
            "raw_score": round(raw_score, 4),
            "model_version": "2.0-32factor",
        }

    def _default_matchup(self, f1_name: str, f2_name: str) -> Dict:
        return {
            "fighter1": f1_name,
            "fighter2": f2_name,
            "predicted_winner": f1_name,
            "confidence": 50.0,
            "f1_probability": 0.50,
            "f2_probability": 0.50,
            "method_prediction": "Decision",
            "method_probs": {"KO/TKO": 0.33, "Submission": 0.17, "Decision": 0.50, "most_likely": "Decision"},
            "round_prediction": {"predicted_round": 3, "avg_seconds": 600, "goes_distance_prob": 0.4},
            "fighter1_style": "Unknown",
            "fighter2_style": "Unknown",
            "factors": {},
            "raw_score": 0.0,
            "note": "Insufficient data — default prediction",
            "model_version": "2.0-32factor",
        }

    # ──────────────────────────────────────────────
    #  Odds integration
    # ──────────────────────────────────────────────

    def _parse_odds_for_fight(self, odds_event: Dict) -> Dict:
        bookmakers = odds_event.get("bookmakers", [])
        if not bookmakers:
            return {}
        outcomes = {}
        for bm in bookmakers:
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name = outcome["name"]
                    price = outcome["price"]
                    if price > 0:
                        impl = 100 / (price + 100)
                    else:
                        impl = abs(price) / (abs(price) + 100)
                    outcomes.setdefault(name, []).append(impl)
        result = {}
        for name, probs in outcomes.items():
            result[name] = sum(probs) / len(probs)
        total = sum(result.values())
        if total > 0:
            result = {k: v / total for k, v in result.items()}
        return result

    def _get_american_odds_for_fight(self, odds_event: Dict) -> Dict:
        """Extract consensus American odds for each fighter."""
        bookmakers = odds_event.get("bookmakers", [])
        if not bookmakers:
            return {}
        outcomes = {}
        for bm in bookmakers:
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    outcomes.setdefault(outcome["name"], []).append(outcome["price"])
        result = {}
        for name, prices in outcomes.items():
            result[name] = round(sum(prices) / len(prices))
        return result

    # ──────────────────────────────────────────────
    #  Parlay Generator (UPGRADE 2)
    # ──────────────────────────────────────────────

    def generate_mma_parlays(self, event_picks: List[Dict], num_parlays: int = 10) -> List[Dict]:
        """
        Generate parlays from UFC event picks.
        Mix: 4x 2-leg, 3x 3-leg, 2x 4-leg, 1x 5-leg
        """
        # Filter to picks with >55% confidence
        viable = [p for p in event_picks if p.get("games") and
                  p["games"][0].get("confidence", 0) > 55]

        if len(viable) < 2:
            logger.warning("Not enough viable picks for parlays")
            return []

        # Sort by confidence descending
        viable.sort(key=lambda p: p["games"][0]["confidence"], reverse=True)

        parlays = []
        parlay_configs = []

        # 4x 2-leg
        for _ in range(4):
            parlay_configs.append(2)
        # 3x 3-leg
        for _ in range(3):
            parlay_configs.append(3)
        # 2x 4-leg
        for _ in range(2):
            parlay_configs.append(4)
        # 1x 5-leg
        parlay_configs.append(5)

        used_combos = set()
        parlay_num = 1
        tier_labels = {2: "Safe", 3: "Medium", 4: "Aggressive", 5: "Moonshot"}

        for leg_count in parlay_configs:
            if len(viable) < leg_count:
                continue

            # Find a unique combination
            best_combo = None
            best_score = -1

            # Try multiple random combos, pick the best
            all_combos = list(combinations(range(len(viable)), leg_count))
            random.shuffle(all_combos)
            for combo in all_combos[:50]:  # check up to 50 combos
                combo_key = tuple(sorted(combo))
                if combo_key in used_combos:
                    continue

                # Check style diversity (avoid all same predicted method)
                methods = [viable[i]["games"][0].get("method_prediction", "") for i in combo]
                style_diversity = len(set(methods)) / max(len(methods), 1)

                # Score: weighted confidence + diversity bonus
                avg_conf = sum(viable[i]["games"][0]["confidence"] for i in combo) / leg_count
                min_conf = min(viable[i]["games"][0]["confidence"] for i in combo)
                score = avg_conf * 0.6 + min_conf * 0.3 + style_diversity * 10

                if score > best_score:
                    best_score = score
                    best_combo = combo_key

            if not best_combo:
                continue

            used_combos.add(best_combo)

            # Build parlay
            legs = []
            combined_prob = 1.0
            combined_american_decimal = 1.0

            for idx in best_combo:
                pick = viable[idx]
                game = pick["games"][0]
                winner_prob = max(game.get("home_probability", 0.5), game.get("away_probability", 0.5))
                combined_prob *= winner_prob

                # Convert to decimal odds for parlay calculation
                if winner_prob > 0:
                    decimal_odds = 1 / winner_prob
                else:
                    decimal_odds = 2.0
                combined_american_decimal *= decimal_odds

                legs.append({
                    "fighter": game["predicted_winner"],
                    "opponent": game["away_team"] if game["predicted_winner"] == game["home_team"]
                               else game["home_team"],
                    "confidence": game["confidence"],
                    "method_prediction": game.get("method_prediction", "Decision"),
                    "method_probs": game.get("method_probs", {}),
                    "event": pick.get("event", "UFC"),
                    "individual_probability": round(winner_prob, 4),
                    "edge": pick.get("edge", 0),
                })

            # Convert combined decimal to American
            if combined_american_decimal >= 2.0:
                combined_american = round((combined_american_decimal - 1) * 100)
            else:
                combined_american = round(-100 / (combined_american_decimal - 1))

            parlay = {
                "parlay_number": parlay_num,
                "type": "parlay",
                "sport": "MMA",
                "tier": tier_labels.get(leg_count, "Custom"),
                "leg_count": leg_count,
                "legs": legs,
                "combined_probability": round(combined_prob, 4),
                "combined_odds_american": combined_american,
                "combined_odds_decimal": round(combined_american_decimal, 2),
                "expected_value": round(combined_prob * combined_american_decimal - 1, 4),
                "risk_level": leg_count,
                "payout_per_100": round((combined_american_decimal - 1) * 100, 2),
                "model_version": "2.0-32factor",
            }
            parlays.append(parlay)
            parlay_num += 1

        logger.info(f"Generated {len(parlays)} MMA parlays")
        return parlays

    # ──────────────────────────────────────────────
    #  Generate picks
    # ──────────────────────────────────────────────

    def generate_picks(self, date_filter: str = None) -> List[Dict]:
        """Main entry: fetch odds, scrape fighters, generate predictions + parlays."""
        logger.info("=== MMA Engine v2.0 (32-factor): Generating Picks ===")

        odds_events = self.get_odds()
        if not odds_events:
            logger.warning("No MMA odds available")
            return self._generate_from_scrape()

        picks = []
        pick_num = 1

        for event in odds_events:
            event_name = event.get("sport_title", "MMA")
            commence = event.get("commence_time", "")

            if date_filter and commence:
                try:
                    event_date = datetime.fromisoformat(commence.replace("Z", "+00:00")).date()
                    filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
                    if event_date != filter_date:
                        continue
                except Exception:
                    pass

            home = event.get("home_team", "")
            away = event.get("away_team", "")
            if not home or not away:
                continue

            logger.info(f"Analyzing: {home} vs {away}")

            odds_map = self._parse_odds_for_fight(event)
            american_odds = self._get_american_odds_for_fight(event)
            odds_implied = None
            if odds_map:
                f1_impl = odds_map.get(home, 0.5)
                odds_implied = {"f1_implied": f1_impl, "f2_implied": 1 - f1_impl}

            is_title = any(k in (event_name or "").lower()
                           for k in ("title", "championship", "interim"))

            matchup = self.calculate_matchup(home, away, is_title=is_title,
                                              odds_implied=odds_implied,
                                              event_name=event_name)

            pick = {
                "pick_number": pick_num,
                "type": "straight",
                "sport": "MMA",
                "event": event_name,
                "commence_time": commence,
                "games": [{
                    "home_team": matchup["fighter1"],
                    "away_team": matchup["fighter2"],
                    "predicted_winner": matchup["predicted_winner"],
                    "confidence": matchup["confidence"],
                    "method_prediction": matchup["method_prediction"],
                    "method_probs": matchup.get("method_probs", {}),
                    "round_prediction": matchup.get("round_prediction", {}),
                    "fighter1_style": matchup.get("fighter1_style", ""),
                    "fighter2_style": matchup.get("fighter2_style", ""),
                    "home_probability": matchup["f1_probability"],
                    "away_probability": matchup["f2_probability"],
                    "american_odds": american_odds,
                }],
                "factors_summary": matchup.get("factors", {}),
                "model_version": "2.0-32factor",
            }

            if odds_implied:
                model_prob = matchup["f1_probability"] if matchup["predicted_winner"] == matchup["fighter1"] \
                    else matchup["f2_probability"]
                implied = odds_implied["f1_implied"] if matchup["predicted_winner"] == matchup["fighter1"] \
                    else odds_implied["f2_implied"]
                pick["edge"] = round((model_prob - implied) * 100, 1)

            picks.append(pick)
            pick_num += 1

        logger.info(f"Generated {len(picks)} MMA straight picks")

        # Generate parlays
        parlays = self.generate_mma_parlays(picks)

        return picks + parlays

    def _generate_from_scrape(self) -> List[Dict]:
        events = self.scraper.scrape_upcoming_events()
        if not events:
            return []

        picks = []
        pick_num = 1
        for event in events[:1]:
            fights = self.scraper.scrape_event_fights(event.get("url", ""))
            for fight in fights:
                f1 = fight.get("fighter1", "")
                f2 = fight.get("fighter2", "")
                if not f1 or not f2:
                    continue

                matchup = self.calculate_matchup(f1, f2, event_name=event.get("name", ""))
                pick = {
                    "pick_number": pick_num,
                    "type": "straight",
                    "sport": "MMA",
                    "event": event.get("name", "UFC Event"),
                    "games": [{
                        "home_team": matchup["fighter1"],
                        "away_team": matchup["fighter2"],
                        "predicted_winner": matchup["predicted_winner"],
                        "confidence": matchup["confidence"],
                        "method_prediction": matchup["method_prediction"],
                        "method_probs": matchup.get("method_probs", {}),
                        "round_prediction": matchup.get("round_prediction", {}),
                        "fighter1_style": matchup.get("fighter1_style", ""),
                        "fighter2_style": matchup.get("fighter2_style", ""),
                        "home_probability": matchup["f1_probability"],
                        "away_probability": matchup["f2_probability"],
                    }],
                    "model_version": "2.0-32factor",
                }
                picks.append(pick)
                pick_num += 1

        parlays = self.generate_mma_parlays(picks)
        return picks + parlays


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MMA Prediction Engine v2.0 (32-factor)")
    parser.add_argument("--matchup", nargs=2, metavar=("FIGHTER1", "FIGHTER2"),
                        help="Predict a specific matchup")
    parser.add_argument("--picks", action="store_true", help="Generate picks for upcoming events")
    parser.add_argument("--date", type=str, help="Filter by date (YYYY-MM-DD)")
    parser.add_argument("--output", type=str, help="Output JSON file path")
    parser.add_argument("--title", action="store_true", help="Mark as title fight")
    parser.add_argument("--parlays-only", action="store_true", help="Output only parlays")
    args = parser.parse_args()

    engine = MMAEngine()

    if args.matchup:
        result = engine.calculate_matchup(args.matchup[0], args.matchup[1],
                                          is_title=args.title)
        print(json.dumps(result, indent=2))
        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2)
    elif args.picks:
        picks = engine.generate_picks(date_filter=args.date)
        if args.parlays_only:
            picks = [p for p in picks if p.get("type") == "parlay"]
        output = {
            "generated_at": datetime.now().isoformat(),
            "model_version": "2.0-32factor",
            "total_picks": len([p for p in picks if p.get("type") == "straight"]),
            "total_parlays": len([p for p in picks if p.get("type") == "parlay"]),
            "picks": picks,
        }
        print(json.dumps(output, indent=2))
        if args.output:
            with open(args.output, "w") as f:
                json.dump(output, f, indent=2)
    else:
        picks = engine.generate_picks()
        output = {
            "generated_at": datetime.now().isoformat(),
            "model_version": "2.0-32factor",
            "picks": picks,
        }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
