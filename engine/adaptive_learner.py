#!/usr/bin/env python3
"""
ParlayGuarantee Adaptive Learning System
==========================================
Self-learning layer for Alpha V3 (NBA) and Rex V2 (NCAAB).

HOW IT WORKS:
  1. Each engine produces picks with per-factor edge scores + weights
  2. After results come in, we feed picks + outcomes to this learner
  3. The learner measures which factors predicted correctly vs incorrectly
  4. Factor weights shift: factors that called it right get boosted,
     factors that called it wrong get penalized
  5. Updated weights are saved and loaded on next engine run

LEARNING RULES:
  - Bayesian-style updates with a learning rate (not wild swings)
  - Minimum weight floor (no factor drops to zero — it might come back)
  - Recency bias: recent games weighted more than old ones
  - Separate weight files per engine (Alpha vs Rex)
  - Full audit trail: every update logged with before/after

STORAGE:
  engine/learned_weights/alpha_weights.json
  engine/learned_weights/rex_weights.json
  engine/learned_weights/history/alpha_YYYY-MM-DD.json  (daily snapshots)
  engine/learned_weights/history/rex_YYYY-MM-DD.json

Usage:
  from adaptive_learner import AdaptiveLearner
  learner = AdaptiveLearner("alpha")  # or "rex"
  weights = learner.get_weights(default_weights)  # loads learned or falls back
  # ... engine runs, produces picks with factor_scores ...
  learner.learn_from_results(picks_with_factor_scores, results)
  # weights auto-saved for next run
"""

import json
import logging
import math
import os
import sys
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
WEIGHTS_DIR = ENGINE_DIR / "learned_weights"
HISTORY_DIR = WEIGHTS_DIR / "history"

# ─── Configuration ───────────────────────────────────────────
LEARNING_RATE = 0.05        # How fast weights shift per lesson (conservative)
MIN_WEIGHT = 0.005          # No factor drops below 0.5% — it might recover
MAX_WEIGHT = 0.25           # No single factor dominates above 25%
RECENCY_HALFLIFE = 14       # Days — games 14 days ago count half as much
MIN_GAMES_TO_LEARN = 3      # Don't update weights until we have 3+ results
CONFIDENCE_THRESHOLD = 0.02 # Factor must have >2% edge signal to count as "called it"


class AdaptiveLearner:
    """Self-learning weight optimizer for prediction engines."""

    def __init__(self, engine_name: str):
        """
        Args:
            engine_name: "alpha" or "rex" — determines storage paths
        """
        self.engine_name = engine_name.lower()
        self.weights_file = WEIGHTS_DIR / f"{self.engine_name}_weights.json"
        self.results_file = WEIGHTS_DIR / f"{self.engine_name}_results.json"

        # Ensure directories exist
        WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    def get_weights(self, default_weights: Dict[str, float]) -> Dict[str, float]:
        """
        Load learned weights if they exist, otherwise return defaults.
        If new factors were added to defaults, they get the default weight.
        If old factors were removed, they're dropped.
        """
        if not self.weights_file.exists():
            logger.info(f"[{self.engine_name}] No learned weights found — using defaults")
            return dict(default_weights)

        try:
            with open(self.weights_file) as f:
                saved = json.load(f)

            learned = saved.get("weights", {})
            meta = saved.get("meta", {})
            games_learned = meta.get("total_games_learned", 0)
            logger.info(f"[{self.engine_name}] Loaded learned weights "
                        f"(trained on {games_learned} games, "
                        f"last update: {meta.get('last_update', 'unknown')})")

            # Merge: use learned for existing factors, default for new ones
            merged = {}
            for factor in default_weights:
                if factor in learned:
                    merged[factor] = learned[factor]
                else:
                    merged[factor] = default_weights[factor]
                    logger.info(f"[{self.engine_name}] New factor '{factor}' — using default weight {default_weights[factor]}")

            # Normalize to sum to 1.0
            total = sum(merged.values())
            if total > 0:
                merged = {k: round(v / total, 6) for k, v in merged.items()}

            return merged

        except Exception as e:
            logger.error(f"[{self.engine_name}] Error loading weights: {e} — using defaults")
            return dict(default_weights)

    def save_weights(self, weights: Dict[str, float], meta: Optional[Dict] = None):
        """Save current weights to disk."""
        payload = {
            "weights": {k: round(v, 6) for k, v in weights.items()},
            "meta": meta or {},
        }
        with open(self.weights_file, 'w') as f:
            json.dump(payload, f, indent=2)

        # Daily snapshot
        snapshot_file = HISTORY_DIR / f"{self.engine_name}_{date.today().isoformat()}.json"
        with open(snapshot_file, 'w') as f:
            json.dump(payload, f, indent=2)

        logger.info(f"[{self.engine_name}] Weights saved → {self.weights_file}")

    def _load_result_history(self) -> List[Dict]:
        """Load accumulated result history."""
        if not self.results_file.exists():
            return []
        try:
            with open(self.results_file) as f:
                return json.load(f)
        except Exception:
            return []

    def _save_result_history(self, history: List[Dict]):
        """Save result history (keeps last 90 days)."""
        cutoff = (date.today().toordinal() - 90)
        filtered = []
        for entry in history:
            try:
                d = date.fromisoformat(entry.get("date", "2000-01-01"))
                if d.toordinal() >= cutoff:
                    filtered.append(entry)
            except Exception:
                filtered.append(entry)

        with open(self.results_file, 'w') as f:
            json.dump(filtered, f, indent=2)

    def learn_from_results(self, picks: List[Dict], results: List[Dict],
                           current_weights: Dict[str, float]) -> Dict[str, float]:
        """
        Core learning function. Compares picks to outcomes and adjusts weights.

        Args:
            picks: List of pick dicts, each MUST contain:
                - 'pick': team name that was picked to cover
                - 'home': home team
                - 'away': away team
                - 'spread': spread line
                - 'factor_scores': {factor_name: edge_score} — the per-factor
                  edge that contributed to this pick. Positive = favored pick side,
                  negative = favored other side.
            results: List of result dicts:
                - 'home': home team
                - 'away': away team  
                - 'home_score': int
                - 'away_score': int
                - 'spread': spread line (from pick time)
            current_weights: Current weight dict to update

        Returns:
            Updated weights dict (also saved to disk)
        """
        if not picks or not results:
            logger.warning(f"[{self.engine_name}] No picks or results to learn from")
            return current_weights

        # Match picks to results
        matched = self._match_picks_to_results(picks, results)

        if len(matched) < MIN_GAMES_TO_LEARN:
            logger.warning(f"[{self.engine_name}] Only {len(matched)} matched games "
                           f"(need {MIN_GAMES_TO_LEARN}) — skipping weight update")
            return current_weights

        logger.info(f"[{self.engine_name}] Learning from {len(matched)} games...")

        # Load history and append new results
        history = self._load_result_history()
        today_str = date.today().isoformat()

        new_entries = []
        for pick, result in matched:
            covered = self._did_pick_cover(pick, result)
            clv_mult = self._get_clv_multiplier(pick)
            entry = {
                "date": today_str,
                "home": pick["home"],
                "away": pick["away"],
                "pick": pick["pick"],
                "spread": pick["spread"],
                "covered": covered,
                "factor_scores": pick.get("factor_scores", {}),
                "home_score": result.get("home_score"),
                "away_score": result.get("away_score"),
                "clv_multiplier": clv_mult,
            }
            new_entries.append(entry)
            history.append(entry)

        self._save_result_history(history)

        # ─── Calculate factor performance ───
        # For each factor, measure: when this factor was positive (agreeing with pick),
        # did the pick cover more often? When negative (disagreeing), did it miss?
        factor_hits = {}   # {factor: [hit_count, miss_count, total_edge]}
        today_ord = date.today().toordinal()

        for entry in history:
            try:
                entry_date = date.fromisoformat(entry["date"])
                days_ago = today_ord - entry_date.toordinal()
            except Exception:
                days_ago = 30

            # Recency weight: exponential decay, boosted/dampened by CLV
            recency = math.exp(-0.693 * days_ago / RECENCY_HALFLIFE)  # 0.693 = ln(2)
            clv_mult = entry.get("clv_multiplier", 1.0)
            recency *= clv_mult

            covered = entry["covered"]
            factor_scores = entry.get("factor_scores", {})

            for factor, edge in factor_scores.items():
                if factor not in factor_hits:
                    factor_hits[factor] = {"correct": 0.0, "incorrect": 0.0, "neutral": 0.0, "n": 0}

                if abs(edge) < CONFIDENCE_THRESHOLD:
                    factor_hits[factor]["neutral"] += recency
                elif (edge > 0 and covered) or (edge < 0 and not covered):
                    # Factor "called it" — its signal matched the outcome
                    factor_hits[factor]["correct"] += recency
                else:
                    # Factor was wrong
                    factor_hits[factor]["incorrect"] += recency

                factor_hits[factor]["n"] += 1

        # ─── Update weights ───
        old_weights = deepcopy(current_weights)
        new_weights = dict(current_weights)

        adjustments = {}
        for factor, stats in factor_hits.items():
            if factor not in new_weights:
                continue

            total_signal = stats["correct"] + stats["incorrect"]
            if total_signal < 1.0:
                continue  # Not enough data for this factor yet

            # Accuracy ratio (recency-weighted)
            accuracy = stats["correct"] / total_signal

            # How far from 50/50 is this factor?
            # accuracy > 0.5 → boost, accuracy < 0.5 → penalize
            # Scale: 0.6 accuracy → +0.02 adjustment, 0.4 → -0.02
            adjustment = (accuracy - 0.5) * LEARNING_RATE * 2

            new_weights[factor] = max(MIN_WEIGHT,
                                      min(MAX_WEIGHT,
                                          new_weights[factor] + adjustment))

            adjustments[factor] = {
                "accuracy": round(accuracy, 4),
                "correct": round(stats["correct"], 2),
                "incorrect": round(stats["incorrect"], 2),
                "games": stats["n"],
                "old_weight": round(old_weights[factor], 6),
                "new_weight": round(new_weights[factor], 6),
                "adjustment": round(adjustment, 6),
            }

        # Normalize weights to sum to 1.0
        total = sum(new_weights.values())
        if total > 0:
            new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

        # ─── Log the learning ───
        hits_today = sum(1 for p, r in matched if self._did_pick_cover(p, r))
        total_today = len(matched)

        logger.info(f"\n{'='*60}")
        logger.info(f"  [{self.engine_name.upper()}] LEARNING REPORT — {today_str}")
        logger.info(f"  Today: {hits_today}/{total_today} picks covered ({hits_today/total_today*100:.0f}%)")
        logger.info(f"  Total history: {len(history)} games")
        logger.info(f"{'='*60}")

        # Show biggest movers
        movers = sorted(adjustments.items(), key=lambda x: abs(x[1]["adjustment"]), reverse=True)
        for factor, adj in movers[:10]:
            direction = "↑" if adj["adjustment"] > 0 else "↓"
            logger.info(f"  {direction} {factor}: {adj['old_weight']:.4f} → {adj['new_weight']:.4f} "
                         f"(acc: {adj['accuracy']:.1%}, {adj['games']} games)")

        # Save
        meta = {
            "engine": self.engine_name,
            "last_update": today_str,
            "total_games_learned": len(history),
            "today_record": f"{hits_today}/{total_today}",
            "today_accuracy": round(hits_today / total_today, 4) if total_today > 0 else 0,
            "factor_performance": adjustments,
        }
        self.save_weights(new_weights, meta)

        return new_weights

    def _get_clv_multiplier(self, pick: Dict) -> float:
        """
        Query CLV tracker DB for this pick and return a learning multiplier.
        CLV-positive picks (we beat the closing line) → 1.5x weight on learning.
        CLV-negative picks → 0.7x weight on learning.
        No CLV data → 1.0x (neutral).
        """
        try:
            import sqlite3 as _sqlite3
            clv_db = ENGINE_DIR / "data" / "clv.db"
            if not clv_db.exists():
                return 1.0

            home = pick.get("home", "")
            away = pick.get("away", "")
            game_key = f"{away} @ {home}"
            predicted = pick.get("pick", "")

            conn = _sqlite3.connect(str(clv_db))
            conn.row_factory = _sqlite3.Row
            row = conn.execute("""
                SELECT clv_cents, beat_closing_line
                FROM picks_odds
                WHERE game_key = ? AND predicted_winner = ?
                AND closing_odds_american IS NOT NULL
                ORDER BY pick_date DESC LIMIT 1
            """, (game_key, predicted)).fetchone()
            conn.close()

            if row is None:
                return 1.0

            if row["beat_closing_line"]:
                return 1.5  # CLV-positive: boost learning
            else:
                return 0.7  # CLV-negative: dampen learning
        except Exception as e:
            logger.debug(f"CLV multiplier lookup failed (non-fatal): {e}")
            return 1.0

    @staticmethod
    def _normalize_team(name: str) -> str:
        """Strip to lowercase alphanumeric for fuzzy matching."""
        import re
        return re.sub(r'[^a-z]', '', name.lower())

    def _teams_match(self, a: str, b: str) -> bool:
        """Fuzzy team name match: substring containment after normalization."""
        na, nb = self._normalize_team(a), self._normalize_team(b)
        if not na or not nb:
            return False
        return na in nb or nb in na

    def _match_picks_to_results(self, picks: List[Dict], results: List[Dict]) -> List[Tuple[Dict, Dict]]:
        """Match picks to results by team names (fuzzy)."""
        matched = []

        # Build result lookup — exact first
        result_lookup = {}
        for r in results:
            key1 = (r.get("home", "").lower(), r.get("away", "").lower())
            key2 = (r.get("away", "").lower(), r.get("home", "").lower())
            result_lookup[key1] = r
            result_lookup[key2] = r

        for pick in picks:
            key = (pick.get("home", "").lower(), pick.get("away", "").lower())
            if key in result_lookup:
                matched.append((pick, result_lookup[key]))
            else:
                # Fuzzy matching: substring containment on normalized names
                ph = pick.get("home", "")
                pa = pick.get("away", "")
                found = False
                for r in results:
                    rh = r.get("home", "")
                    ra = r.get("away", "")
                    if (self._teams_match(ph, rh) and self._teams_match(pa, ra)) or \
                       (self._teams_match(ph, ra) and self._teams_match(pa, rh)):
                        matched.append((pick, r))
                        found = True
                        break
                if not found:
                    logger.warning(f"No result match for {pick.get('away')} @ {pick.get('home')}")

        return matched

    def _did_pick_cover(self, pick: Dict, result: Dict) -> bool:
        """Determine if the spread pick covered."""
        home_score = result.get("home_score", 0)
        away_score = result.get("away_score", 0)
        spread = pick.get("spread", 0)

        # Home adjusted score = home_score + spread
        # If pick is home team: they cover if home_score + spread > away_score
        # If pick is away team: they cover if away_score > home_score + spread
        home_adjusted = home_score + spread

        pick_team = pick.get("pick", "")
        home_team = pick.get("home", "")

        if pick_team.lower() == home_team.lower():
            return home_adjusted > away_score
        else:
            return away_score > home_adjusted

    def get_performance_summary(self) -> Dict:
        """Get a summary of learning progress."""
        history = self._load_result_history()
        if not history:
            return {"status": "no_data", "total_games": 0}

        total = len(history)
        wins = sum(1 for h in history if h.get("covered"))
        
        # Last 7 days
        week_ago = date.today().toordinal() - 7
        recent = [h for h in history 
                  if date.fromisoformat(h.get("date", "2000-01-01")).toordinal() > week_ago]
        recent_wins = sum(1 for h in recent if h.get("covered"))

        # Load current weights
        weights = {}
        if self.weights_file.exists():
            try:
                with open(self.weights_file) as f:
                    data = json.load(f)
                weights = data.get("weights", {})
            except Exception:
                pass

        # Top/bottom factors
        meta = {}
        if self.weights_file.exists():
            try:
                with open(self.weights_file) as f:
                    data = json.load(f)
                meta = data.get("meta", {})
            except Exception:
                pass

        return {
            "status": "active",
            "total_games": total,
            "overall_accuracy": round(wins / total, 4) if total > 0 else 0,
            "last_7_days": {
                "games": len(recent),
                "accuracy": round(recent_wins / len(recent), 4) if recent else 0,
            },
            "weights": weights,
            "meta": meta,
        }
