#!/usr/bin/env python3
"""
ParlayGuarantee — Feed Results to Self-Learning Engines
========================================================
Feeds yesterday's (or specified date's) results into Alpha V3 and Rex V2
so they learn and adapt their factor weights.

Usage:
  python feed_results.py                    # Feed yesterday's results
  python feed_results.py --date 2026-02-24  # Feed specific date
  python feed_results.py --summary          # Show learning progress

What happens:
  1. Loads the engine's picks JSON from that date
  2. Fetches actual scores (Odds API + ESPN fallback)
  3. Matches picks to outcomes
  4. Calls AdaptiveLearner.learn_from_results() for each engine
  5. Updated weights saved → next engine run uses them automatically
"""

import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('feed_results.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent

# Import what we need
sys.path.insert(0, str(ENGINE_DIR))
from adaptive_learner import AdaptiveLearner

try:
    from autopilot import fetch_scores, ODDS_API_KEY, fetch_espn_scores
except ImportError:
    fetch_scores = None
    fetch_espn_scores = None
    ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')


def load_picks(engine: str, target_date: date) -> List[Dict]:
    """Load picks JSON for a given engine and date."""
    ds = target_date.isoformat()

    if engine == "alpha":
        candidates = [
            ENGINE_DIR / f"alpha_v3_nba_picks_{ds}.json",
            ENGINE_DIR / f"picks_{ds}" / f"alpha_v3_nba_picks.json",
        ]
    elif engine == "rex":
        candidates = [
            ENGINE_DIR / f"rex_v2_ncaab_picks_{ds}.json",
            ENGINE_DIR / f"picks_{ds}" / f"rex_v2_ncaab_picks.json",
        ]
    else:
        return []

    for path in candidates:
        if path.exists():
            logger.info(f"Loading {engine} picks from {path}")
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict) and 'picks' in data:
                return data['picks']
            elif isinstance(data, list):
                return data
            return []

    logger.warning(f"No {engine} picks found for {ds}")
    return []


def fetch_actual_scores(target_date: date, sport: str = "nba") -> List[Dict]:
    """Fetch actual game scores from Odds API or ESPN."""
    results = []
    ds = target_date.isoformat()

    # Try Odds API first
    sport_key = "basketball_nba" if sport == "nba" else "basketball_ncaab"
    if fetch_scores:
        try:
            raw = fetch_scores(sport_key, days_from=3)
            for game in (raw or []):
                if not game.get('completed'):
                    continue
                # Check if game was on target date
                commence = game.get('commence_time', '')
                if ds not in commence and ds not in game.get('id', ''):
                    # Try to match by date
                    from datetime import datetime, timezone
                    try:
                        dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                        if dt.date() != target_date and (dt.date() - timedelta(days=1)) != target_date:
                            continue
                    except Exception:
                        continue

                scores = game.get('scores', [])
                if len(scores) >= 2:
                    home_name = game.get('home_team', '')
                    away_name = game.get('away_team', '')
                    home_score = 0
                    away_score = 0
                    for s in scores:
                        if s.get('name') == home_name:
                            home_score = int(s.get('score', 0))
                        elif s.get('name') == away_name:
                            away_score = int(s.get('score', 0))

                    results.append({
                        'home': home_name,
                        'away': away_name,
                        'home_score': home_score,
                        'away_score': away_score,
                    })

            if results:
                logger.info(f"Fetched {len(results)} {sport.upper()} scores from Odds API")
                return results
        except Exception as e:
            logger.warning(f"Odds API scores failed: {e}")

    # Fallback: ESPN
    if fetch_espn_scores:
        try:
            espn_data = fetch_espn_scores(ds, sport)
            if espn_data:
                for game_id, game in espn_data.items():
                    if game.get('status') == 'Final' or game.get('completed'):
                        results.append({
                            'home': game.get('home', ''),
                            'away': game.get('away', ''),
                            'home_score': int(game.get('home_score', 0)),
                            'away_score': int(game.get('away_score', 0)),
                        })
                if results:
                    logger.info(f"Fetched {len(results)} {sport.upper()} scores from ESPN")
                    return results
        except Exception as e:
            logger.warning(f"ESPN scores failed: {e}")

    # Fallback: check if result_tracker already scored
    results_db = ENGINE_DIR / "results.db"
    if results_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(results_db))
            rows = conn.execute(
                "SELECT home_team, away_team, home_score, away_score FROM results WHERE date = ?",
                (ds,)
            ).fetchall()
            conn.close()
            for row in rows:
                results.append({
                    'home': row[0],
                    'away': row[1],
                    'home_score': row[2],
                    'away_score': row[3],
                })
            if results:
                logger.info(f"Loaded {len(results)} scores from results.db")
                return results
        except Exception as e:
            logger.warning(f"results.db fallback failed: {e}")

    logger.error(f"Could not fetch scores for {ds}")
    return results


def normalize_pick_format(picks: List[Dict], engine: str) -> List[Dict]:
    """Normalize pick format so the learner can process them uniformly."""
    normalized = []
    for p in picks:
        # Alpha uses: home, away, pick, spread, factor_scores, edge_breakdown
        # Rex uses: home_team, away_team, spread_pick, v2_factors, factor_scores
        norm = {}

        if engine == "alpha":
            norm['home'] = p.get('home', '')
            norm['away'] = p.get('away', '')
            norm['pick'] = p.get('pick', '')
            norm['spread'] = p.get('spread', 0)
            norm['factor_scores'] = p.get('factor_scores', {})
            # If no factor_scores but has edge_breakdown, derive them
            if not norm['factor_scores'] and p.get('edge_breakdown'):
                norm['factor_scores'] = {k: round(v - 0.5, 4) for k, v in p['edge_breakdown'].items()}
        elif engine == "rex":
            norm['home'] = p.get('home_team', '')
            norm['away'] = p.get('away_team', '')
            # Parse spread pick to get pick team
            sp = p.get('spread_pick') or p.get('spread_pick_original', '')
            if sp:
                # "Team Name +3.5" or "Team Name -3.5"
                parts = sp.rsplit(' ', 1)
                norm['pick'] = parts[0] if parts else ''
            else:
                norm['pick'] = p.get('predicted_winner', '')
            norm['spread'] = p.get('spread', 0)
            norm['factor_scores'] = p.get('factor_scores', {})
            # Fallback to v2_factors
            if not norm['factor_scores'] and p.get('v2_factors'):
                norm['factor_scores'] = {k: v for k, v in p['v2_factors'].items() 
                                         if isinstance(v, (int, float))}

        if norm.get('home') and norm.get('pick'):
            normalized.append(norm)

    return normalized


def feed_engine(engine: str, target_date: date, sport: str):
    """Feed results to one engine."""
    print(f"\n{'─'*50}")
    print(f"  Feeding {engine.upper()} ({sport.upper()}) — {target_date}")
    print(f"{'─'*50}")

    # Load picks
    picks = load_picks(engine, target_date)
    if not picks:
        print(f"  ⚠️  No picks found for {engine} on {target_date}")
        return

    # Only process picks that were actual PICK (not PASS)
    active_picks = [p for p in picks if p.get('spread_status') == 'PICK' or 
                    (engine == 'alpha' and p.get('spread_status') != 'PASS')]
    print(f"  📊 Loaded {len(picks)} total, {len(active_picks)} active picks")

    # Fetch scores
    results = fetch_actual_scores(target_date, sport)
    if not results:
        print(f"  ❌ No scores available for {target_date}")
        return

    print(f"  🏀 Fetched {len(results)} game scores")

    # Normalize picks
    norm_picks = normalize_pick_format(active_picks, engine)
    print(f"  🔄 Normalized {len(norm_picks)} picks for learning")

    # Get current weights
    learner = AdaptiveLearner(engine)
    if engine == "alpha":
        from nba_engine_alpha_v3 import W as default_weights
    elif engine == "rex":
        from ncaab_engine_rex_v2 import V2_WEIGHTS as default_weights
    else:
        default_weights = {}

    current_weights = learner.get_weights(default_weights)

    # Learn!
    new_weights = learner.learn_from_results(norm_picks, results, current_weights)

    # Show delta
    print(f"\n  ✅ Learning complete!")
    print(f"  📁 Weights saved to: {learner.weights_file}")
    print(f"  📁 History saved to: {learner.results_file}")

    # Show top weight changes
    changes = []
    for k in new_weights:
        if k in current_weights:
            delta = new_weights[k] - current_weights[k]
            if abs(delta) > 0.0005:
                changes.append((k, current_weights[k], new_weights[k], delta))

    if changes:
        changes.sort(key=lambda x: abs(x[3]), reverse=True)
        print(f"\n  Top weight changes:")
        for name, old, new, delta in changes[:8]:
            arrow = "↑" if delta > 0 else "↓"
            print(f"    {arrow} {name}: {old:.4f} → {new:.4f} ({delta:+.4f})")


def show_summary():
    """Show learning progress for both engines."""
    print(f"\n{'='*60}")
    print(f"  ADAPTIVE LEARNING — PROGRESS REPORT")
    print(f"{'='*60}")

    for engine_name in ["alpha", "rex"]:
        learner = AdaptiveLearner(engine_name)
        summary = learner.get_performance_summary()

        print(f"\n  {'🐺' if engine_name == 'alpha' else '🦖'} {engine_name.upper()}")
        print(f"  Status: {summary['status']}")
        print(f"  Total games learned: {summary['total_games']}")

        if summary['total_games'] > 0:
            print(f"  Overall accuracy: {summary['overall_accuracy']:.1%}")
            l7 = summary.get('last_7_days', {})
            if l7.get('games'):
                print(f"  Last 7 days: {l7['accuracy']:.1%} ({l7['games']} games)")

            # Show top/bottom weights
            weights = summary.get('weights', {})
            if weights:
                sorted_w = sorted(weights.items(), key=lambda x: -x[1])
                print(f"  Top 5 weights: {', '.join(f'{k}={v:.3f}' for k,v in sorted_w[:5])}")
                print(f"  Bottom 5: {', '.join(f'{k}={v:.3f}' for k,v in sorted_w[-5:])}")
        else:
            print(f"  No data yet — feed first results tomorrow!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Feed results to self-learning engines')
    parser.add_argument('--date', type=str, help='Date to score (YYYY-MM-DD, default=yesterday)')
    parser.add_argument('--engine', choices=['alpha', 'rex', 'both'], default='both',
                        help='Which engine to feed (default: both)')
    parser.add_argument('--summary', action='store_true', help='Show learning progress')
    args = parser.parse_args()

    if args.summary:
        show_summary()
        sys.exit(0)

    target = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)

    print(f"🧠 Feeding results for {target} to self-learning engines...\n")

    if args.engine in ('alpha', 'both'):
        feed_engine('alpha', target, 'nba')

    if args.engine in ('rex', 'both'):
        feed_engine('rex', target, 'ncaab')

    # Also feed O/U engines (Pulse + Tempo)
    try:
        from feed_ou_results import feed_engine as feed_ou
        if args.engine in ('alpha', 'both'):
            feed_ou('pulse', target)
        if args.engine in ('rex', 'both'):
            feed_ou('tempo', target)
    except Exception as e:
        logger.warning(f"O/U engine feeding failed (non-critical): {e}")

    print(f"\n{'='*60}")
    print(f"  Done! Engines will use updated weights on next run.")
    print(f"{'='*60}")
