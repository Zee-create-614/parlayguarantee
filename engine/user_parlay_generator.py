"""
Per-user unique parlay generator for ParlayGuarantee.
Takes analyzed games (with probabilities) + user_id → deterministic unique parlays per user.
"""
import hashlib
import random
import json
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional


def _user_seed(user_id: str, date_str: str) -> int:
    """Generate a deterministic seed from user_id + date so parlays are stable per user per day."""
    raw = f"{user_id}:{date_str}:parlayguarantee"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:12], 16)


def generate_user_parlays(
    analyzed_games: List[Dict],
    user_id: str,
    product_mix: List[int],
    date_str: str = "",
) -> List[Dict]:
    """
    Generate unique parlay combinations for a specific user.

    Args:
        analyzed_games: list of dicts with keys: home, away, pick, win_prob, game_date, game_time (optional)
        user_id: unique user identifier (email, uid, etc.)
        product_mix: list of leg counts e.g. [2,2,2,2,3,3,4,4,5,6]
        date_str: date string for seed stability (defaults to today)

    Returns:
        list of parlay dicts ready for output
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    if len(analyzed_games) < 2:
        return []

    # Sort by probability descending as base ordering
    games_sorted = sorted(analyzed_games, key=lambda g: g.get("win_prob", 0.5), reverse=True)

    # Create user-specific RNG
    seed = _user_seed(user_id, date_str)
    rng = random.Random(seed)

    # Shuffle a copy to create user-unique ordering while keeping high-prob games weighted
    # Strategy: weighted shuffle — higher prob games more likely to appear first
    def weighted_shuffle(games: List[Dict], rng_inst: random.Random) -> List[Dict]:
        pool = list(games)
        result = []
        while pool:
            weights = [g.get("win_prob", 0.5) ** 2 for g in pool]
            total = sum(weights)
            if total == 0:
                result.extend(pool)
                break
            r = rng_inst.random() * total
            cumulative = 0
            for i, w in enumerate(weights):
                cumulative += w
                if r <= cumulative:
                    result.append(pool.pop(i))
                    break
        return result

    user_games = weighted_shuffle(games_sorted, rng)

    parlays = []
    for i, legs_count in enumerate(product_mix):
        if len(user_games) < legs_count:
            # Not enough games — skip this parlay size
            continue

        # Pick legs using rotating offset unique to this parlay index
        parlay_rng = random.Random(seed + i * 7919)  # different seed per parlay slot
        indices = list(range(len(user_games)))
        parlay_rng.shuffle(indices)
        selected_indices = indices[:legs_count]

        parlay_games = [user_games[idx] for idx in sorted(selected_indices)]

        # Calculate combined probability
        combined_prob = 1.0
        for g in parlay_games:
            combined_prob *= g.get("win_prob", 0.5)

        # Payout multiplier
        if combined_prob > 0:
            payout_mult = 1.0 / combined_prob
        else:
            payout_mult = 1.0

        # Earliest game time for delivery scheduling
        game_times = [g.get("game_time", "") for g in parlay_games if g.get("game_time")]
        earliest_game_time = min(game_times) if game_times else ""

        parlays.append({
            "pick_number": i + 1,
            "type": "parlay",
            "legs": legs_count,
            "games": parlay_games,
            "combined_prob": round(combined_prob, 4),
            "implied_payout": f"{payout_mult:.1f}x",
            "earliest_game_time": earliest_game_time,
            "user_id": user_id,
        })

    # CRITICAL FIX: If no parlays generated but we have 2+ games, create at least one 2-leg parlay
    if not parlays and len(user_games) >= 2:
        min_games = user_games[:2]
        combined_prob = 1.0
        for g in min_games:
            combined_prob *= g.get("win_prob", 0.5)
        
        payout_mult = 1.0 / combined_prob if combined_prob > 0 else 1.0
        
        game_times = [g.get("game_time", "") for g in min_games if g.get("game_time")]
        earliest_game_time = min(game_times) if game_times else ""
        
        parlays.append({
            "pick_number": 1,
            "type": "parlay", 
            "legs": 2,
            "games": min_games,
            "combined_prob": round(combined_prob, 4),
            "implied_payout": f"{payout_mult:.1f}x",
            "earliest_game_time": earliest_game_time,
            "user_id": user_id,
        })

    return parlays


def get_delivery_times(picks: List[Dict], hours_before: float = 2.0) -> List[Dict]:
    """
    Given a list of parlay picks with earliest_game_time, return delivery schedule.

    Returns list of {pick_number, earliest_game_time, deliver_at} dicts.
    """
    from datetime import timedelta

    schedule = []
    for pick in picks:
        egt = pick.get("earliest_game_time", "")
        if not egt:
            continue
        try:
            game_dt = datetime.fromisoformat(egt.replace("Z", "+00:00"))
            deliver_at = game_dt - timedelta(hours=hours_before)
            schedule.append({
                "pick_number": pick.get("pick_number"),
                "earliest_game_time": egt,
                "deliver_at": deliver_at.isoformat(),
            })
        except (ValueError, TypeError):
            continue

    return schedule


# CLI usage for testing
if __name__ == "__main__":
    # Load analyzed games from picks_output.json or analyzed_games.json
    input_file = sys.argv[1] if len(sys.argv) > 1 else "analyzed_games.json"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "test-user@example.com"

    if not os.path.exists(input_file):
        print(f"Input file {input_file} not found")
        sys.exit(1)

    with open(input_file, "r") as f:
        games = json.load(f)

    mix = [2, 2, 2, 2, 3, 3, 4, 4, 5, 6]
    parlays = generate_user_parlays(games, user_id, mix)
    print(json.dumps(parlays, indent=2))

    delivery = get_delivery_times(parlays)
    if delivery:
        print("\nDelivery schedule:")
        print(json.dumps(delivery, indent=2))
