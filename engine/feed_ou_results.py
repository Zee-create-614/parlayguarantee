#!/usr/bin/env python3
"""
ParlayGuarantee — Feed O/U Results to Pulse & Tempo
=====================================================
Feeds yesterday's (or specified date's) O/U results into the self-learning
Pulse (NBA) and Tempo (NCAAB) engines.

Usage:
  python feed_ou_results.py                     # Feed yesterday
  python feed_ou_results.py --date 2026-02-24   # Specific date
  python feed_ou_results.py --engine pulse       # Only Pulse
  python feed_ou_results.py --engine tempo       # Only Tempo
  python feed_ou_results.py --summary            # Show learning progress
"""

import json, logging, os, sys, sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('feed_ou_results.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
sys.path.insert(0, str(ENGINE_DIR))
from adaptive_learner import AdaptiveLearner


def load_ou_picks(engine_name: str, target_date: date) -> List[Dict]:
    """Load O/U picks for a given engine and date."""
    ds = target_date.isoformat()
    if engine_name == "pulse":
        candidates = [
            ENGINE_DIR / f"picks_{ds}" / "nba_ou_pulse_picks.json",
        ]
    elif engine_name == "tempo":
        candidates = [
            ENGINE_DIR / f"picks_{ds}" / "ncaab_ou_tempo_picks.json",
        ]
    else:
        return []

    for path in candidates:
        if path.exists():
            logger.info(f"Loading {engine_name} O/U picks from {path}")
            with open(path) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []

    logger.warning(f"No {engine_name} O/U picks found for {ds}")
    return []


def fetch_ou_scores(target_date: date, sport: str) -> List[Dict]:
    """Fetch actual game totals from the engine's score cache or ESPN."""
    if sport == "nba":
        db_path = ENGINE_DIR / "pulse_engine.db"
    else:
        db_path = ENGINE_DIR / "tempo_engine.db"

    results = []
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute('SELECT home_team, away_team, home_score, away_score, total FROM game_scores_cache WHERE game_date=?',
                      (target_date.isoformat(),))
            for row in c.fetchall():
                results.append({
                    'home': row[0], 'away': row[1],
                    'home_score': row[2], 'away_score': row[3],
                    'total': row[4],
                })
            conn.close()
        except Exception as e:
            logger.warning(f"DB score fetch failed: {e}")

    if not results:
        # Try caching scores via the engine
        try:
            if sport == "nba":
                from nba_ou_pulse import PulseEngine
                eng = PulseEngine()
                eng._cache_scores(target_date)
            else:
                from ncaab_ou_tempo import TempoEngine
                eng = TempoEngine()
                eng._cache_scores(target_date)
            # Retry
            db = ENGINE_DIR / ("pulse_engine.db" if sport == "nba" else "tempo_engine.db")
            conn = sqlite3.connect(str(db))
            c = conn.cursor()
            c.execute('SELECT home_team, away_team, home_score, away_score, total FROM game_scores_cache WHERE game_date=?',
                      (target_date.isoformat(),))
            for row in c.fetchall():
                results.append({
                    'home': row[0], 'away': row[1],
                    'home_score': row[2], 'away_score': row[3],
                    'total': row[4],
                })
            conn.close()
        except Exception as e:
            logger.warning(f"Score cache retry failed: {e}")

    logger.info(f"Fetched {len(results)} {sport.upper()} scores for {target_date}")
    return results


def normalize_ou_picks(picks: List[Dict]) -> List[Dict]:
    """
    Normalize O/U picks for the adaptive learner.
    The learner expects: home, away, pick, spread, factor_scores
    For O/U: pick = "OVER"/"UNDER", spread = posted_total (the line)
    factor_scores = the per-factor edge scores
    """
    normalized = []
    for p in picks:
        if p.get('pick') in ('PASS', None):
            continue
        norm = {
            'home': p.get('home', p.get('home_team', '')),
            'away': p.get('away', p.get('away_team', '')),
            'pick': p.get('home', p.get('home_team', '')),  # dummy — learner needs a "pick team"
            'spread': 0,  # Not used for O/U — we'll override _did_pick_cover
            'factor_scores': p.get('factor_scores', {}),
            'ou_pick': p.get('pick'),  # OVER or UNDER
            'posted_total': p.get('posted_total', 0),
        }
        if norm['home'] and norm['factor_scores']:
            normalized.append(norm)
    return normalized


def learn_ou(engine_name: str, picks: List[Dict], scores: List[Dict],
             default_weights: Dict[str, float]) -> Dict[str, float]:
    """
    Custom O/U learning — adapts factor weights based on O/U outcomes.
    Uses AdaptiveLearner infrastructure but with O/U-specific matching.
    """
    learner = AdaptiveLearner(engine_name)
    current_weights = learner.get_weights(default_weights)

    # Match picks to scores
    matched = []
    score_lookup = {}
    for s in scores:
        key = f"{s['home'].lower()}|{s['away'].lower()}"
        score_lookup[key] = s
        # Also reversed
        score_lookup[f"{s['away'].lower()}|{s['home'].lower()}"] = s

    for pick in picks:
        if pick.get('pick') in ('PASS', None):
            continue
        home = pick.get('home', pick.get('home_team', ''))
        away = pick.get('away', pick.get('away_team', ''))
        key = f"{home.lower()}|{away.lower()}"
        score = score_lookup.get(key)

        if not score:
            # Fuzzy match
            import re
            norm = lambda n: re.sub(r'[^a-z]', '', n.lower())
            ph, pa = norm(home), norm(away)
            for s in scores:
                sh, sa = norm(s['home']), norm(s['away'])
                if (ph in sh or sh in ph) and (pa in sa or sa in pa):
                    score = s
                    break

        if score:
            matched.append((pick, score))

    if len(matched) < 3:
        logger.warning(f"[{engine_name}] Only {len(matched)} matched — skipping")
        return current_weights

    # Build learner-compatible format
    import math
    from copy import deepcopy
    from datetime import date as d_mod

    history = learner._load_result_history()
    today_str = d_mod.today().isoformat()

    for pick, score in matched:
        actual_total = score['total']
        posted = pick.get('posted_total', 0)
        ou_pick = pick.get('pick', pick.get('ou_pick', ''))
        actual_result = "OVER" if actual_total > posted else "UNDER"
        covered = (ou_pick == actual_result)

        entry = {
            "date": today_str,
            "home": pick.get('home', pick.get('home_team', '')),
            "away": pick.get('away', pick.get('away_team', '')),
            "pick": ou_pick,
            "spread": posted,
            "covered": covered,
            "factor_scores": pick.get('factor_scores', {}),
            "actual_total": actual_total,
            "posted_total": posted,
        }
        history.append(entry)

    learner._save_result_history(history)

    # Calculate factor performance (same logic as AdaptiveLearner)
    LEARNING_RATE = 0.05
    MIN_WEIGHT = 0.005
    MAX_WEIGHT = 0.25
    RECENCY_HALFLIFE = 14
    today_ord = d_mod.today().toordinal()

    factor_hits = {}
    for entry in history:
        try:
            entry_date = d_mod.fromisoformat(entry["date"])
            days_ago = today_ord - entry_date.toordinal()
        except Exception:
            days_ago = 30
        recency = math.exp(-0.693 * days_ago / RECENCY_HALFLIFE)
        covered = entry.get("covered", False)

        for factor, edge in entry.get("factor_scores", {}).items():
            if factor not in factor_hits:
                factor_hits[factor] = {"correct": 0.0, "incorrect": 0.0, "n": 0}
            if abs(edge) < 0.02:
                continue
            # For O/U: positive factor = over lean. If pick was OVER and covered, factor was right.
            # If pick was UNDER, factor should have been negative to be "right".
            pick_dir = 1 if entry.get("pick") == "OVER" else -1
            factor_agreed = (edge * pick_dir) > 0  # factor leaned same direction as pick

            if (factor_agreed and covered) or (not factor_agreed and not covered):
                factor_hits[factor]["correct"] += recency
            else:
                factor_hits[factor]["incorrect"] += recency
            factor_hits[factor]["n"] += 1

    old_weights = deepcopy(current_weights)
    new_weights = dict(current_weights)

    for factor, stats in factor_hits.items():
        if factor not in new_weights:
            continue
        total_signal = stats["correct"] + stats["incorrect"]
        if total_signal < 1.0:
            continue
        accuracy = stats["correct"] / total_signal
        adjustment = (accuracy - 0.5) * LEARNING_RATE * 2
        new_weights[factor] = max(MIN_WEIGHT, min(MAX_WEIGHT, new_weights[factor] + adjustment))

    # Normalize
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

    # Save
    hits_today = sum(1 for p, s in matched
                     if (p.get('pick', p.get('ou_pick', '')) == ("OVER" if s['total'] > p.get('posted_total', 0) else "UNDER")))

    meta = {
        "engine": engine_name,
        "last_update": today_str,
        "total_games_learned": len(history),
        "today_record": f"{hits_today}/{len(matched)}",
        "today_accuracy": round(hits_today / len(matched), 4) if matched else 0,
    }
    learner.save_weights(new_weights, meta)

    # Log changes
    print(f"\n  ✅ {engine_name.upper()} learning complete!")
    print(f"  📊 Today: {hits_today}/{len(matched)} ({round(hits_today/len(matched)*100,1) if matched else 0}%)")
    print(f"  📁 Weights: {learner.weights_file}")

    changes = [(k, old_weights.get(k, 0), new_weights[k], new_weights[k] - old_weights.get(k, 0))
               for k in new_weights if abs(new_weights[k] - old_weights.get(k, 0)) > 0.0005]
    if changes:
        changes.sort(key=lambda x: abs(x[3]), reverse=True)
        print(f"  Top changes:")
        for name, old, new, delta in changes[:8]:
            arrow = "↑" if delta > 0 else "↓"
            print(f"    {arrow} {name}: {old:.4f} → {new:.4f} ({delta:+.4f})")

    return new_weights


def feed_engine(engine_name: str, target_date: date):
    sport = "nba" if engine_name == "pulse" else "ncaab"
    print(f"\n{'─'*50}")
    print(f"  Feeding {engine_name.upper()} ({sport.upper()} O/U) — {target_date}")
    print(f"{'─'*50}")

    picks = load_ou_picks(engine_name, target_date)
    if not picks:
        print(f"  ⚠️ No picks found")
        return

    active = [p for p in picks if p.get('pick') not in ('PASS', None)]
    print(f"  📊 Loaded {len(picks)} total, {len(active)} active picks")

    scores = fetch_ou_scores(target_date, sport)
    if not scores:
        print(f"  ❌ No scores available")
        return
    print(f"  🏀 {len(scores)} game scores")

    if engine_name == "pulse":
        from nba_ou_pulse import DEFAULT_WEIGHTS
    else:
        from ncaab_ou_tempo import DEFAULT_WEIGHTS

    learn_ou(engine_name, active, scores, DEFAULT_WEIGHTS)


def show_summary():
    print(f"\n{'='*60}")
    print(f"  O/U ADAPTIVE LEARNING — PROGRESS REPORT")
    print(f"{'='*60}")

    for engine_name in ["pulse", "tempo"]:
        learner = AdaptiveLearner(engine_name)
        summary = learner.get_performance_summary()
        emoji = "💓" if engine_name == "pulse" else "🎵"

        print(f"\n  {emoji} {engine_name.upper()}")
        print(f"  Status: {summary['status']}")
        print(f"  Total games learned: {summary['total_games']}")

        if summary['total_games'] > 0:
            print(f"  Overall accuracy: {summary['overall_accuracy']:.1%}")
            l7 = summary.get('last_7_days', {})
            if l7.get('games'):
                print(f"  Last 7 days: {l7['accuracy']:.1%} ({l7['games']} games)")
            weights = summary.get('weights', {})
            if weights:
                sorted_w = sorted(weights.items(), key=lambda x: -x[1])
                print(f"  Top 5: {', '.join(f'{k}={v:.3f}' for k,v in sorted_w[:5])}")
                print(f"  Bottom 5: {', '.join(f'{k}={v:.3f}' for k,v in sorted_w[-5:])}")
        else:
            print(f"  No data yet — run engines first, feed results tomorrow!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Feed O/U results to Pulse & Tempo')
    parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD, default=yesterday)')
    parser.add_argument('--engine', choices=['pulse', 'tempo', 'both'], default='both')
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()

    if args.summary:
        show_summary()
        sys.exit(0)

    target = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    print(f"🧠 Feeding O/U results for {target}...\n")

    if args.engine in ('pulse', 'both'):
        feed_engine('pulse', target)
    if args.engine in ('tempo', 'both'):
        feed_engine('tempo', target)

    print(f"\n{'='*60}")
    print(f"  Done! Engines will use updated weights on next run.")
    print(f"{'='*60}")
