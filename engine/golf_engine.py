# -*- coding: utf-8 -*-
"""
ParlayGuarantee Golf Prediction Engine — 22-factor model

Golf is fundamentally different: 100+ player field, outright winner odds.
Output: ranked list with win/top5/top10/top20/cut probabilities + value scores.

Factors:
 1. World ranking
 2. Recent form (L5 tournaments)
 3. Course history
 4. Strokes gained total
 5. SG putting
 6. SG approach
 7. SG tee-to-green
 8. SG around green
 9. Driving distance
10. Driving accuracy
11. GIR %
12. Scrambling %
13. Par 3 scoring
14. Par 4 scoring
15. Par 5 scoring
16. Cut made %
17. Top 10 finish rate
18. Scoring average
19. Putting average
20. Wind/weather susceptibility
21. Course fit (length)
22. Momentum / recent wins
"""

import sys
import json
import math
import logging
import os
from datetime import datetime, date
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from golf_data_fetcher import GolfDataFetcher, _safe_float

LOG_PATH = os.path.join(os.path.dirname(__file__), "golf_engine.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Factor weights
DEFAULT_WEIGHTS = {
    "world_ranking":      0.10,
    "recent_form":        0.08,
    "course_history":     0.07,
    "sg_total":           0.08,
    "sg_putting":         0.05,
    "sg_approach":        0.06,
    "sg_tee":             0.05,
    "sg_around_green":    0.04,
    "driving_distance":   0.03,
    "driving_accuracy":   0.04,
    "gir_pct":            0.05,
    "scrambling":         0.04,
    "par3_scoring":       0.02,
    "par4_scoring":       0.03,
    "par5_scoring":       0.03,
    "cut_made_pct":       0.04,
    "top10_rate":         0.05,
    "scoring_avg":        0.04,
    "putting_avg":        0.03,
    "weather":            0.02,
    "course_fit":         0.02,
    "momentum":           0.03,
}


def _rank_score(ranking: int) -> float:
    """Convert world ranking to 0-1 score. #1 -> ~1.0, #200 -> ~0.1."""
    if ranking <= 0:
        ranking = 200
    return max(0.05, 1.0 - math.log(ranking) / math.log(300))


class GolfEngine:
    """22-factor golf prediction engine for field sports."""

    def __init__(self):
        self.fetcher = GolfDataFetcher()
        self.weights = dict(DEFAULT_WEIGHTS)

    def score_player(self, name: str, tournament: str = "",
                     odds_data: Dict = None) -> Dict:
        """Score a single player across all factors. Returns factor scores + probabilities."""
        info = self.fetcher.get_player_info(name)
        pid = info.get("player_id", info.get("id", ""))
        ranking = int(info.get("world_ranking", 9999) or 9999)

        stats = self.fetcher.db.get_player_stats(pid)
        course_hist = self.fetcher.db.get_course_history(pid, tournament) if tournament else []

        # Compute factors (each 0-1, higher = better)
        events_played = max(stats.get("events_played", 1), 1)
        cuts = stats.get("cuts_made", 0)
        wins = stats.get("wins", 0)
        top5 = stats.get("top5", 0)
        top10 = stats.get("top10", 0)

        factors = {
            "world_ranking":   _rank_score(ranking),
            "recent_form":     min(1.0, (top10 / events_played) * 2) if events_played > 0 else 0.3,
            "course_history":  self._course_history_score(course_hist),
            "sg_total":        self._sg_score(stats.get("sg_total", 0)),
            "sg_putting":      self._sg_score(stats.get("sg_putting", 0)),
            "sg_approach":     self._sg_score(stats.get("sg_approach", 0)),
            "sg_tee":          self._sg_score(stats.get("sg_tee", 0)),
            "sg_around_green": self._sg_score(stats.get("sg_around_green", 0)),
            "driving_distance": min(1.0, _safe_float(stats.get("driving_distance", 290)) / 320.0),
            "driving_accuracy": _safe_float(stats.get("driving_accuracy", 60)) / 100.0,
            "gir_pct":         _safe_float(stats.get("gir_pct", 65)) / 100.0,
            "scrambling":      _safe_float(stats.get("scrambling_pct", 55)) / 100.0,
            "par3_scoring":    0.5,  # Placeholder — needs per-hole data
            "par4_scoring":    0.5,
            "par5_scoring":    0.5,
            "cut_made_pct":    cuts / events_played if events_played > 0 else 0.5,
            "top10_rate":      top10 / events_played if events_played > 0 else 0.1,
            "scoring_avg":     max(0, 1.0 - (_safe_float(stats.get("scoring_avg", 72)) - 68) / 8.0),
            "putting_avg":     max(0, 1.0 - (_safe_float(stats.get("putting_avg", 29)) - 27) / 4.0),
            "weather":         0.5,  # Placeholder
            "course_fit":      0.5,  # Placeholder
            "momentum":        min(1.0, wins * 0.3 + top5 * 0.1) if events_played > 0 else 0.2,
        }

        # Weighted composite score
        composite = sum(factors[k] * self.weights.get(k, 0) for k in factors)
        total_w = sum(self.weights.get(k, 0) for k in factors)
        raw_score = composite / total_w if total_w > 0 else 0.3

        # Convert to probabilities (field of ~150)
        # These are rough calibrations
        win_prob = max(0.001, raw_score ** 3 * 0.15)
        top5_prob = max(win_prob, raw_score ** 2 * 0.25)
        top10_prob = max(top5_prob, raw_score ** 1.5 * 0.40)
        top20_prob = max(top10_prob, raw_score * 0.55)
        cut_prob = max(top20_prob, min(0.95, raw_score * 0.85 + 0.15))

        # Value score vs odds
        value_score = 0.0
        implied_win = 0.0
        american_odds = 0
        if odds_data and name in odds_data:
            implied_win = odds_data[name].get("implied_prob", 0)
            american_odds = odds_data[name].get("american_odds", 0)
            if implied_win > 0:
                value_score = round((win_prob - implied_win) / implied_win * 100, 1)

        return {
            "player": name,
            "world_ranking": ranking,
            "composite_score": round(raw_score, 4),
            "win_probability": round(win_prob, 4),
            "top5_probability": round(top5_prob, 4),
            "top10_probability": round(top10_prob, 4),
            "top20_probability": round(top20_prob, 4),
            "make_cut_probability": round(cut_prob, 4),
            "value_score": value_score,
            "implied_win_prob": round(implied_win, 4),
            "american_odds": american_odds,
            "factors": factors,
        }

    def _course_history_score(self, history: List[Dict]) -> float:
        if not history:
            return 0.4  # No data = slight penalty
        scores = []
        for h in history:
            pos = h.get("finish_position", 50)
            if pos <= 1:
                scores.append(1.0)
            elif pos <= 5:
                scores.append(0.85)
            elif pos <= 10:
                scores.append(0.70)
            elif pos <= 20:
                scores.append(0.55)
            elif pos <= 40:
                scores.append(0.40)
            else:
                scores.append(0.25)
        return sum(scores) / len(scores) if scores else 0.4

    def _sg_score(self, sg_value: float) -> float:
        """Convert strokes gained to 0-1. SG of +2 ≈ 0.9, SG of -2 ≈ 0.1."""
        return max(0.05, min(0.95, 0.5 + _safe_float(sg_value) * 0.2))

    def generate_picks(self, target_date: str = None) -> List[Dict]:
        """Main entry: score full field and rank players."""
        logger.info("=== Golf Engine (22-factor): Generating Picks ===")

        # Get odds events
        odds_events = self.fetcher.get_golf_odds()

        if odds_events:
            return self._generate_from_odds(odds_events)

        # Fallback to ESPN leaderboard
        return self._generate_from_espn()

    def _generate_from_odds(self, odds_events: List[Dict]) -> List[Dict]:
        """Generate picks from odds data."""
        all_picks = []

        for event in odds_events:
            sport_title = event.get("sport_title", "Golf")
            sport_key = event.get("_sport_key", "")
            commence = event.get("commence_time", "")

            odds_map = self.fetcher.parse_outright_odds(event)
            if not odds_map:
                continue

            logger.info(f"Scoring {len(odds_map)} players for {sport_title}")

            scored = []
            for player_name in odds_map:
                try:
                    result = self.score_player(player_name, tournament=sport_title,
                                               odds_data=odds_map)
                    scored.append(result)
                except Exception as e:
                    logger.warning(f"Error scoring {player_name}: {e}")

            # Sort by composite score
            scored.sort(key=lambda x: x["composite_score"], reverse=True)

            # Assign tiers
            for i, s in enumerate(scored):
                if s["value_score"] > 20:
                    s["pick_type"] = "STRONG VALUE"
                elif s["value_score"] > 5:
                    s["pick_type"] = "VALUE"
                elif s["composite_score"] > 0.7:
                    s["pick_type"] = "FAVORITE"
                elif s["composite_score"] > 0.5:
                    s["pick_type"] = "CONTENDER"
                else:
                    s["pick_type"] = "LONGSHOT"

            pick = {
                "pick_number": len(all_picks) + 1,
                "type": "golf_field",
                "sport": "Golf",
                "event": sport_title,
                "sport_key": sport_key,
                "commence_time": commence,
                "field_size": len(scored),
                "players": scored[:50],  # Top 50
                "top_values": [s for s in scored if s["value_score"] > 5][:10],
                "model_version": "1.0-22factor",
            }
            all_picks.append(pick)

        logger.info(f"Generated {len(all_picks)} golf field predictions")
        return all_picks

    def _generate_from_espn(self) -> List[Dict]:
        """Fallback: use ESPN leaderboard data."""
        players = self.fetcher.get_espn_leaderboard("pga")
        if not players:
            logger.warning("No ESPN golf data available")
            return []

        tournament = players[0].get("tournament", "PGA Tour Event") if players else ""
        scored = []
        for p in players:
            try:
                result = self.score_player(p["name"], tournament=tournament)
                scored.append(result)
            except Exception as e:
                logger.warning(f"Error scoring {p['name']}: {e}")

        scored.sort(key=lambda x: x["composite_score"], reverse=True)

        return [{
            "pick_number": 1,
            "type": "golf_field",
            "sport": "Golf",
            "event": tournament,
            "field_size": len(scored),
            "players": scored[:50],
            "top_values": scored[:10],
            "model_version": "1.0-22factor",
        }]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Golf Prediction Engine (22-factor)")
    parser.add_argument("--date", type=str, help="Target date YYYY-MM-DD")
    parser.add_argument("--output", type=str, help="Output JSON file")
    args = parser.parse_args()

    engine = GolfEngine()
    picks = engine.generate_picks(target_date=args.date)

    output = {
        "generated_at": datetime.now().isoformat(),
        "model_version": "1.0-22factor",
        "total_events": len(picks),
        "picks": picks,
    }
    print(json.dumps(output, indent=2, default=str))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)


def generate_picks(target_date=None):
    """Module-level entry point."""
    engine = GolfEngine()
    return engine.generate_picks(target_date=target_date)


if __name__ == "__main__":
    main()
