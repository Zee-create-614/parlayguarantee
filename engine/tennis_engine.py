# -*- coding: utf-8 -*-
"""
ParlayGuarantee Tennis Prediction Engine — 22-factor model

Factors:
 1. ATP/WTA ranking differential
 2. Ranking points ratio
 3. Surface win % (hard/clay/grass)
 4. H2H record
 5. Recent form (L10)
 6. Aces per match
 7. Double faults per match
 8. Break point conversion rate
 9. Return games won %
10. Tournament history at venue
11. Fatigue (matches played this week)
12. Travel / timezone
13. Age / peak curve
14. Set win %
15. Tiebreak record
16. First serve %
17. Indoor / outdoor adjustment
18. Seeding advantage
19. Odds-implied value
20. Experience (career matches)
21. Momentum / streak
22. Surface specialist bonus
"""

import sys
import json
import math
import logging
import sqlite3
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from itertools import combinations

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from tennis_data_fetcher import TennisDataFetcher, _safe_float

LOG_PATH = os.path.join(os.path.dirname(__file__), "tennis_engine.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── Factor weights (sum ≈ 1.0) ──
DEFAULT_WEIGHTS = {
    "ranking":              0.10,
    "ranking_points":       0.06,
    "surface_win_pct":      0.08,
    "h2h":                  0.06,
    "recent_form":          0.08,
    "aces":                 0.03,
    "double_faults":        0.03,
    "break_point_conv":     0.05,
    "return_games":         0.05,
    "tournament_history":   0.04,
    "fatigue":              0.04,
    "travel":               0.02,
    "age_curve":            0.04,
    "set_win_pct":          0.04,
    "tiebreak":             0.03,
    "first_serve":          0.04,
    "indoor_outdoor":       0.02,
    "seeding":              0.03,
    "odds_value":           0.05,
    "experience":           0.03,
    "momentum":             0.04,
    "surface_specialist":   0.04,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _clamp(val: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


class TennisEngine:
    """22-factor tennis prediction engine."""

    def __init__(self):
        self.fetcher = TennisDataFetcher()
        self.weights = dict(DEFAULT_WEIGHTS)

    def _ranking_factor(self, r1: int, r2: int) -> float:
        """Higher = player 1 has better ranking."""
        if r1 == 0: r1 = 500
        if r2 == 0: r2 = 500
        return _sigmoid((r2 - r1) / 50.0)

    def _ranking_points_factor(self, pts1: float, pts2: float) -> float:
        total = pts1 + pts2
        if total == 0:
            return 0.5
        return pts1 / total

    def _surface_win_pct_factor(self, stats1: Dict, stats2: Dict) -> float:
        w1 = stats1.get("matches_won", 0)
        p1 = stats1.get("matches_played", 1) or 1
        w2 = stats2.get("matches_won", 0)
        p2 = stats2.get("matches_played", 1) or 1
        pct1 = w1 / p1
        pct2 = w2 / p2
        return _sigmoid((pct1 - pct2) * 3.0)

    def _h2h_factor(self, h2h: Dict) -> float:
        total = h2h.get("total", 0)
        if total == 0:
            return 0.5
        return h2h.get("p1_wins", 0) / total

    def _recent_form_factor(self, form1: Dict, form2: Dict) -> float:
        pct1 = form1.get("win_pct", 0.5)
        pct2 = form2.get("win_pct", 0.5)
        return _sigmoid((pct1 - pct2) * 3.0)

    def _serve_factor(self, stats1: Dict, stats2: Dict, key: str) -> float:
        v1 = _safe_float(stats1.get(key, 0.5))
        v2 = _safe_float(stats2.get(key, 0.5))
        return _sigmoid((v1 - v2) * 4.0)

    def _double_faults_factor(self, stats1: Dict, stats2: Dict) -> float:
        """Fewer double faults is better, so invert."""
        df1 = _safe_float(stats1.get("double_faults_per_match", 3.0))
        df2 = _safe_float(stats2.get("double_faults_per_match", 3.0))
        return _sigmoid((df2 - df1) * 0.5)

    def _age_curve(self, age: int) -> float:
        """Peak at 26-28, decline after 32."""
        if age <= 0:
            return 0.5
        if 26 <= age <= 28:
            return 1.0
        elif age < 26:
            return 0.7 + 0.3 * (age - 18) / 8.0
        else:
            return max(0.3, 1.0 - 0.08 * (age - 28))

    def _age_factor(self, age1: int, age2: int) -> float:
        c1 = self._age_curve(age1)
        c2 = self._age_curve(age2)
        return _sigmoid((c1 - c2) * 3.0)

    def _set_win_pct_factor(self, stats1: Dict, stats2: Dict) -> float:
        sw1 = stats1.get("sets_won", 0)
        sl1 = stats1.get("sets_lost", 1) or 1
        sw2 = stats2.get("sets_won", 0)
        sl2 = stats2.get("sets_lost", 1) or 1
        pct1 = sw1 / (sw1 + sl1) if (sw1 + sl1) > 0 else 0.5
        pct2 = sw2 / (sw2 + sl2) if (sw2 + sl2) > 0 else 0.5
        return _sigmoid((pct1 - pct2) * 3.0)

    def _tiebreak_factor(self, stats1: Dict, stats2: Dict) -> float:
        tw1 = stats1.get("tiebreaks_won", 0)
        tl1 = stats1.get("tiebreaks_lost", 1) or 1
        tw2 = stats2.get("tiebreaks_won", 0)
        tl2 = stats2.get("tiebreaks_lost", 1) or 1
        pct1 = tw1 / (tw1 + tl1) if (tw1 + tl1) > 0 else 0.5
        pct2 = tw2 / (tw2 + tl2) if (tw2 + tl2) > 0 else 0.5
        return _sigmoid((pct1 - pct2) * 3.0)

    def _seeding_factor(self, seed1: str, seed2: str) -> float:
        s1 = int(seed1) if seed1 and str(seed1).isdigit() else 99
        s2 = int(seed2) if seed2 and str(seed2).isdigit() else 99
        return _sigmoid((s2 - s1) / 10.0)

    def _odds_implied_factor(self, odds_map: Dict, p1_name: str) -> float:
        if not odds_map:
            return 0.5
        return odds_map.get(p1_name, 0.5)

    def _parse_odds(self, event: Dict) -> Dict:
        """Parse odds event into {player_name: implied_probability}."""
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
                    name = outcome.get("name", "")
                    if name not in result or impl > result[name]:
                        result[name] = impl
                break  # Use first bookmaker
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

    def compute_factors(self, p1_name: str, p2_name: str,
                        surface: str = "hard", odds_map: Dict = None,
                        seed1: str = "", seed2: str = "",
                        indoor: bool = False) -> Dict:
        """Compute all 22 factors. Returns dict of factor_name -> score (0-1, p1 favored > 0.5)."""
        p1_info = self.fetcher.get_player_info(p1_name)
        p2_info = self.fetcher.get_player_info(p2_name)

        p1_id = p1_info.get("player_id", "")
        p2_id = p2_info.get("player_id", "")

        # Surface-specific stats
        p1_surf = self.fetcher.db.get_player_stats(p1_id, surface)
        p2_surf = self.fetcher.db.get_player_stats(p2_id, surface)
        # Overall stats as fallback
        p1_all = self.fetcher.db.get_player_stats(p1_id, "all") if not p1_surf else p1_surf
        p2_all = self.fetcher.db.get_player_stats(p2_id, "all") if not p2_surf else p2_surf

        h2h = self.fetcher.db.get_h2h(p1_name, p2_name)
        form1 = self.fetcher.get_recent_form(p1_name, 10)
        form2 = self.fetcher.get_recent_form(p2_name, 10)

        r1 = int(p1_info.get("ranking", 500) or 500)
        r2 = int(p2_info.get("ranking", 500) or 500)
        pts1 = _safe_float(p1_info.get("ranking_points", 0))
        pts2 = _safe_float(p2_info.get("ranking_points", 0))
        age1 = int(p1_info.get("age", 25) or 25)
        age2 = int(p2_info.get("age", 25) or 25)

        factors = {
            "ranking":            self._ranking_factor(r1, r2),
            "ranking_points":     self._ranking_points_factor(pts1, pts2),
            "surface_win_pct":    self._surface_win_pct_factor(p1_surf or {}, p2_surf or {}),
            "h2h":                self._h2h_factor(h2h),
            "recent_form":        self._recent_form_factor(form1, form2),
            "aces":               self._serve_factor(p1_all or {}, p2_all or {}, "aces_per_match"),
            "double_faults":      self._double_faults_factor(p1_all or {}, p2_all or {}),
            "break_point_conv":   self._serve_factor(p1_all or {}, p2_all or {}, "break_points_converted"),
            "return_games":       self._serve_factor(p1_all or {}, p2_all or {}, "return_games_won_pct"),
            "tournament_history": 0.5,  # Placeholder — needs venue-specific data
            "fatigue":            0.5,  # Placeholder — needs week schedule data
            "travel":             0.5,  # Placeholder
            "age_curve":          self._age_factor(age1, age2),
            "set_win_pct":        self._set_win_pct_factor(p1_all or {}, p2_all or {}),
            "tiebreak":           self._tiebreak_factor(p1_all or {}, p2_all or {}),
            "first_serve":        self._serve_factor(p1_all or {}, p2_all or {}, "first_serve_pct"),
            "indoor_outdoor":     0.52 if indoor and r1 < r2 else 0.5,
            "seeding":            self._seeding_factor(seed1, seed2),
            "odds_value":         self._odds_implied_factor(odds_map, p1_name),
            "experience":         _sigmoid((form1.get("total", 0) - form2.get("total", 0)) / 20.0),
            "momentum":           _sigmoid((form1.get("wins", 0) - form2.get("wins", 0)) / 5.0),
            "surface_specialist":  0.5,  # Would need career surface split
        }

        return factors

    def predict_match(self, p1_name: str, p2_name: str,
                      surface: str = "hard", odds_map: Dict = None,
                      seed1: str = "", seed2: str = "",
                      indoor: bool = False, tournament: str = "") -> Dict:
        """Predict a single match."""
        factors = self.compute_factors(p1_name, p2_name, surface, odds_map, seed1, seed2, indoor)

        # Weighted score
        weighted_sum = sum(factors[k] * self.weights.get(k, 0) for k in factors)
        total_weight = sum(self.weights.get(k, 0) for k in factors)
        raw_prob = weighted_sum / total_weight if total_weight > 0 else 0.5

        # Calibrate to reasonable range
        confidence = _clamp(raw_prob, 0.35, 0.95)

        predicted_winner = p1_name if confidence >= 0.5 else p2_name
        if confidence < 0.5:
            confidence = 1.0 - confidence

        # Value score: model prob vs implied odds
        implied = odds_map.get(predicted_winner, 0.5) if odds_map else 0.5
        edge = confidence - implied
        value_score = round(edge * 100, 1)

        # Pick type
        if confidence >= 0.75:
            pick_type = "LOCK"
        elif confidence >= 0.65:
            pick_type = "VALUE" if value_score > 3 else "STRONG"
        elif confidence >= 0.55:
            pick_type = "LEAN"
        else:
            pick_type = "SKIP"

        return {
            "player1": p1_name,
            "player2": p2_name,
            "predicted_winner": predicted_winner,
            "confidence": round(confidence, 4),
            "p1_probability": round(raw_prob, 4),
            "p2_probability": round(1 - raw_prob, 4),
            "value_score": value_score,
            "edge": round(edge * 100, 1),
            "pick_type": pick_type,
            "tournament": tournament,
            "surface": surface,
            "factors": factors,
        }

    def generate_picks(self, target_date: str = None) -> List[Dict]:
        """Main entry: fetch odds, generate predictions for all tennis matches."""
        logger.info("=== Tennis Engine (22-factor): Generating Picks ===")

        date_filter = target_date or date.today().isoformat()

        # Fetch all tennis odds
        odds_events = self.fetcher.get_tennis_odds()
        if not odds_events:
            logger.warning("No tennis odds found — trying ESPN fallback")
            return self._generate_from_espn(date_filter)

        picks = []
        pick_num = 1

        for event in odds_events:
            commence = event.get("commence_time", "")
            sport_key = event.get("_sport_key", event.get("sport_key", ""))
            sport_title = event.get("sport_title", "Tennis")

            # Date filter
            if date_filter and commence:
                try:
                    event_date = datetime.fromisoformat(commence.replace("Z", "+00:00")).date()
                    filter_date = date.fromisoformat(date_filter)
                    if event_date != filter_date:
                        continue
                except Exception:
                    pass

            p1 = event.get("home_team", "")
            p2 = event.get("away_team", "")
            if not p1 or not p2:
                continue

            surface = self.fetcher.detect_surface(sport_title, sport_key)
            odds_map = self._parse_odds(event)
            american_odds = self._get_american_odds(event)

            logger.info(f"Analyzing: {p1} vs {p2} ({sport_title}, {surface})")

            matchup = self.predict_match(
                p1, p2, surface=surface, odds_map=odds_map,
                tournament=sport_title,
            )

            pick = {
                "pick_number": pick_num,
                "type": "straight",
                "sport": "Tennis",
                "event": sport_title,
                "tournament": sport_title,
                "surface": surface,
                "commence_time": commence,
                "games": [{
                    "home_team": p1,
                    "away_team": p2,
                    "predicted_winner": matchup["predicted_winner"],
                    "confidence": matchup["confidence"],
                    "home_probability": matchup["p1_probability"],
                    "away_probability": matchup["p2_probability"],
                    "american_odds": american_odds,
                    "value_score": matchup["value_score"],
                    "pick_type": matchup["pick_type"],
                }],
                "factors_summary": matchup.get("factors", {}),
                "model_version": "1.0-22factor",
            }

            if odds_map:
                pick["edge"] = matchup["edge"]

            picks.append(pick)
            pick_num += 1

        logger.info(f"Generated {len(picks)} tennis picks")

        # Generate parlays from high-confidence picks
        parlays = self._generate_parlays(picks)
        return picks + parlays

    def _generate_from_espn(self, date_filter: str) -> List[Dict]:
        """Fallback: use ESPN data."""
        picks = []
        pick_num = 1
        for tour in ["atp", "wta"]:
            events = self.fetcher.get_espn_scoreboard(tour)
            matches = self.fetcher.parse_espn_matches(events)
            for m in matches:
                if m.get("status") in ("STATUS_FINAL", "STATUS_IN_PROGRESS"):
                    continue
                surface = self.fetcher.detect_surface(m.get("tournament", ""))
                matchup = self.predict_match(
                    m["player1"], m["player2"],
                    surface=surface,
                    seed1=m.get("player1_seed", ""),
                    seed2=m.get("player2_seed", ""),
                    tournament=m.get("tournament", ""),
                )
                picks.append({
                    "pick_number": pick_num,
                    "type": "straight",
                    "sport": "Tennis",
                    "event": m.get("tournament", "Tennis"),
                    "tournament": m.get("tournament", ""),
                    "surface": surface,
                    "games": [{
                        "home_team": m["player1"],
                        "away_team": m["player2"],
                        "predicted_winner": matchup["predicted_winner"],
                        "confidence": matchup["confidence"],
                        "home_probability": matchup["p1_probability"],
                        "away_probability": matchup["p2_probability"],
                        "value_score": matchup["value_score"],
                        "pick_type": matchup["pick_type"],
                    }],
                    "model_version": "1.0-22factor",
                })
                pick_num += 1
        return picks

    def _generate_parlays(self, straight_picks: List[Dict], max_legs: int = 4) -> List[Dict]:
        """Generate parlays from best straight picks."""
        good = [p for p in straight_picks
                if p["games"][0]["confidence"] >= 0.58
                and p["games"][0].get("pick_type") != "SKIP"]
        good.sort(key=lambda p: p["games"][0]["confidence"], reverse=True)
        good = good[:8]  # Top 8 for combo pool

        parlays = []
        parlay_num = 1
        for n_legs in range(2, min(max_legs + 1, len(good) + 1)):
            combos = list(combinations(good, n_legs))
            # Score each combo
            scored = []
            for combo in combos:
                combined_conf = 1.0
                legs = []
                for p in combo:
                    g = p["games"][0]
                    combined_conf *= g["confidence"]
                    legs.append(g)
                scored.append((combined_conf, legs, combo))
            scored.sort(key=lambda x: x[0], reverse=True)

            for conf, legs, combo in scored[:2]:
                parlays.append({
                    "pick_number": len(straight_picks) + parlay_num,
                    "type": "parlay",
                    "sport": "Tennis",
                    "legs": n_legs,
                    "combined_confidence": round(conf, 4),
                    "games": legs,
                    "model_version": "1.0-22factor",
                })
                parlay_num += 1

        return parlays


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tennis Prediction Engine (22-factor)")
    parser.add_argument("--date", type=str, help="Target date YYYY-MM-DD")
    parser.add_argument("--output", type=str, help="Output JSON file")
    args = parser.parse_args()

    engine = TennisEngine()
    picks = engine.generate_picks(target_date=args.date)

    output = {
        "generated_at": datetime.now().isoformat(),
        "model_version": "1.0-22factor",
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
    engine = TennisEngine()
    return engine.generate_picks(target_date=target_date)


if __name__ == "__main__":
    main()
