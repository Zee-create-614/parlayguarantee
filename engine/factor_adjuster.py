#!/usr/bin/env python3
"""
Factor Adjuster — Applies learned weight adjustments to autopilot picks.
Blends factor-model insights with odds-consensus probabilities.

This bridges the gap between:
- Autopilot (pure odds consensus from bookmakers)
- Self-learner/Adaptive Engine (factor-weighted model that learns from results)

The learned weights tell us which factors are actually predictive (and which are harmful).
This module fetches real team stats, scores each game using the learned factor weights,
and applies a small adjustment to the autopilot's enhanced_prob.

Usage:
    # As a module (called from autopilot after upset composite):
    from factor_adjuster import apply_factor_adjustments
    apply_factor_adjustments(games)
    
    # Standalone test:
    python factor_adjuster.py
"""
import json, sys, logging, requests, sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("factor_adjuster")
ENGINE_DIR = Path(__file__).parent
LEARNED_WEIGHTS = ENGINE_DIR / "learned_weights.json"
ESPN_CACHE = ENGINE_DIR / "espn_cache"
ESPN_CACHE.mkdir(exist_ok=True)

# How much the factor model can adjust the odds-consensus prob
# 0.05 = max ±5% adjustment. Conservative to avoid overriding market consensus.
MAX_ADJUSTMENT = 0.05
# Blend ratio: 0 = pure odds, 1 = pure factor model. 0.15 = 15% factor influence.
BLEND_RATIO = 0.15


def load_weights() -> Dict[str, float]:
    """Load learned weights (or empty dict if none exist)."""
    if LEARNED_WEIGHTS.exists():
        with open(LEARNED_WEIGHTS) as f:
            data = json.load(f)
            return data.get('weights', data)
    return {}


def fetch_nba_team_stats() -> Dict[str, Dict]:
    """Fetch current NBA team stats from ESPN."""
    cache_file = ESPN_CACHE / f"nba_standings_{datetime.now().strftime('%Y-%m-%d')}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    
    stats = {}
    try:
        # Standings (win%, home/away records)
        r = requests.get("https://site.api.espn.com/apis/v2/sports/basketball/nba/standings", timeout=10)
        if r.status_code == 200:
            data = r.json()
            for group in data.get('children', []):
                for entry in group.get('standings', {}).get('entries', []):
                    team_name = entry.get('team', {}).get('displayName', '')
                    if not team_name:
                        continue
                    
                    stat_map = {}
                    for s in entry.get('stats', []):
                        stat_map[s.get('name', '')] = s.get('value', 0)
                    
                    overall = stat_map.get('overall', {})
                    stats[team_name] = {
                        'win_pct': stat_map.get('winPercent', 0.5),
                        'home_win_pct': stat_map.get('Home', 0.5),
                        'away_win_pct': stat_map.get('Road', 0.5),
                        'ppg': stat_map.get('pointsFor', 110) / max(stat_map.get('gamesPlayed', 1), 1) if 'pointsFor' in stat_map else 110,
                        'points_allowed': stat_map.get('pointsAgainst', 110) / max(stat_map.get('gamesPlayed', 1), 1) if 'pointsAgainst' in stat_map else 110,
                        'streak': stat_map.get('streak', 0),
                        'last_10_wins': stat_map.get('record10', 5),
                        'games_played': stat_map.get('gamesPlayed', 40),
                    }
        
        if stats:
            with open(cache_file, 'w') as f:
                json.dump(stats, f, indent=2)
    except Exception as e:
        log.warning(f"ESPN stats fetch failed: {e}")
    
    return stats


def compute_game_factors(game: dict, team_stats: Dict[str, Dict]) -> Dict[str, float]:
    """Compute factor values for a game using real team stats."""
    home = game.get('home', '')
    away = game.get('away', '')
    
    h_stats = team_stats.get(home, {})
    a_stats = team_stats.get(away, {})
    
    if not h_stats or not a_stats:
        return {}
    
    h_wp = h_stats.get('win_pct', 0.5)
    a_wp = a_stats.get('win_pct', 0.5)
    h_ppg = h_stats.get('ppg', 110)
    a_ppg = a_stats.get('ppg', 110)
    h_pa = h_stats.get('points_allowed', 110)
    a_pa = a_stats.get('points_allowed', 110)
    
    # Offensive rating proxy (ppg relative to league avg ~112)
    h_off = (h_ppg - 112) / 10  # normalized around 0
    a_off = (a_ppg - 112) / 10
    
    # Defensive rating proxy (lower allowed = better, so invert)
    h_def = (112 - h_pa) / 10
    a_def = (112 - a_pa) / 10
    
    # Home team advantage in each factor (positive = home is stronger)
    factors = {
        'home_win_pct': h_stats.get('home_win_pct', h_wp),
        'away_win_pct': a_stats.get('away_win_pct', a_wp),
        'season_win_pct': h_wp - a_wp,
        'offensive_rating': h_off - a_off,
        'defensive_rating': h_def - a_def,
        'net_rating': (h_off + h_def) - (a_off + a_def),
        'ppg': h_ppg - a_ppg,
        'points_allowed': a_pa - h_pa,  # positive = home allows fewer
        'last_10_record': (h_stats.get('last_10_wins', 5) - a_stats.get('last_10_wins', 5)) / 10,
        'last_5_record': 0,  # Would need more granular data
        'pace': 0,  # Would need pace data
        'day_of_week': 0,
        'days_since_last': 0,
        'division_rivalry': 0,  # Would need division data
        'rebound_diff': 0,  # Would need rebound data
        'three_pt_pct': 0,  # Would need 3pt data
        'defensive_activity': 0,
        'home_court': 0.03,  # Standard ~3pt home court advantage
    }
    
    return factors


def score_game_with_weights(factors: Dict[str, float], weights: Dict[str, float]) -> float:
    """Score a game using factor values and learned weights. Returns -1 to +1 (home advantage)."""
    score = 0.0
    total_weight = 0.0
    
    for factor_name, value in factors.items():
        w = weights.get(factor_name, 0)
        if w > 0 and value != 0:
            score += value * w
            total_weight += w
    
    if total_weight == 0:
        return 0.0
    
    return score / total_weight


def apply_factor_adjustments(games: List[dict], team_stats: Dict[str, Dict] = None):
    """
    Apply learned weight adjustments to a list of analyzed games.
    Modifies enhanced_prob in-place.
    """
    weights = load_weights()
    if not weights:
        log.info("No learned weights found — skipping factor adjustments")
        return
    
    if team_stats is None:
        team_stats = fetch_nba_team_stats()
    
    if not team_stats:
        log.warning("No team stats available — skipping factor adjustments")
        return
    
    adjusted_count = 0
    
    for game in games:
        factors = compute_game_factors(game, team_stats)
        if not factors:
            continue
        
        factor_score = score_game_with_weights(factors, weights)
        
        # Convert factor score to probability adjustment
        # factor_score is roughly -0.1 to +0.1 range
        # Positive = home team stronger, negative = away team stronger
        pick = game.get('pick', '')
        home = game.get('home', '')
        
        # If we picked home and factors say home is strong → boost
        # If we picked away and factors say away is strong → boost
        if pick == home:
            adjustment = factor_score * BLEND_RATIO
        else:
            adjustment = -factor_score * BLEND_RATIO
        
        # Clamp adjustment
        adjustment = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, adjustment))
        
        if abs(adjustment) > 0.001:
            old_prob = game.get('enhanced_prob', game.get('cover_prob', 0.5))
            new_prob = max(0.45, min(0.95, old_prob + adjustment))
            game['enhanced_prob'] = round(new_prob, 4)
            game['factor_adjustment'] = round(adjustment, 4)
            game['factor_score'] = round(factor_score, 4)
            adjusted_count += 1
    
    log.info(f"  📊 Factor adjustments applied to {adjusted_count}/{len(games)} games (blend={BLEND_RATIO:.0%})")


# ─── Standalone test ───
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    
    # Load today's picks
    EST = timezone(timedelta(hours=-5))
    today = datetime.now(EST).strftime('%Y-%m-%d')
    picks_file = ENGINE_DIR / f"picks_{today}" / "all_picks.json"
    
    if not picks_file.exists():
        print(f"No picks found at {picks_file}")
        sys.exit(1)
    
    import copy
    with open(picks_file) as f:
        raw = json.load(f)
    # all_picks.json has {all_games: [...]} structure
    if isinstance(raw, dict) and 'all_games' in raw:
        original = raw['all_games']
    elif isinstance(raw, list):
        original = raw
    else:
        original = []
    games = copy.deepcopy(original)
    
    print(f"Loaded {len(games)} games from {picks_file}")
    
    team_stats = fetch_nba_team_stats()
    print(f"Fetched stats for {len(team_stats)} teams")
    
    apply_factor_adjustments(games, team_stats)
    
    # Compare
    print(f"\n{'Game':50s} {'Pick':25s} {'Old Prob':>10s} {'New Prob':>10s} {'Δ':>8s}")
    print("-" * 100)
    
    for orig, adj in zip(original, games):
        old_p = orig.get('enhanced_prob', orig.get('cover_prob', 0.5))
        new_p = adj.get('enhanced_prob', adj.get('cover_prob', 0.5))
        delta = new_p - old_p
        if abs(delta) > 0.001:
            marker = "⬆️" if delta > 0 else "⬇️"
        else:
            marker = "  "
        game_str = f"{adj.get('away', '?')} @ {adj.get('home', '?')}"
        print(f"{game_str:50s} {adj.get('pick', '?'):25s} {old_p:10.1%} {new_p:10.1%} {delta:+8.1%} {marker}")
    
    # Save to test folder
    out_dir = ENGINE_DIR / "picks_with_13_weighted_adjustments"
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "all_picks_adjusted.json", 'w') as f:
        json.dump(games, f, indent=2, default=str)
    print(f"\nSaved to {out_dir / 'all_picks_adjusted.json'}")
