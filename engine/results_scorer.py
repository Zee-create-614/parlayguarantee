"""
ParlayGuarantee Results Scorer — Fetches actual scores and grades picks.
Supports NBA and NCAAB via ESPN API. Stores everything in the ResultsDB.

Usage:
    python results_scorer.py --date 2026-02-20
    python results_scorer.py --date 2026-02-20 --sport NCAAB
    python results_scorer.py                          # scores yesterday
    python results_scorer.py --pending                # scores all pending picks
    python results_scorer.py --dry-run --date 2026-02-20   # preview only
"""

import sys
import json
import argparse
import logging
import requests
from datetime import date, timedelta
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from results_db import ResultsDB

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ESPN endpoints per sport
ESPN_ENDPOINTS = {
    'NBA': "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    'NCAAB': "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
    'NFL': "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    'NHL': "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    'MLB': "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
}

# Team name normalization (reuse from existing codebase patterns)
TEAM_ALIASES = {
    'la clippers': 'LA Clippers',
    'los angeles clippers': 'LA Clippers',
    'los angeles lakers': 'Los Angeles Lakers',
    'la lakers': 'Los Angeles Lakers',
    'okc thunder': 'Oklahoma City Thunder',
    'oklahoma city thunder': 'Oklahoma City Thunder',
}


def normalize_team(name: str) -> str:
    if not name:
        return name
    lower = name.lower().strip()
    return TEAM_ALIASES.get(lower, name)


def fetch_espn_scores(game_date: str, sport: str = 'NBA') -> Dict[str, Dict]:
    """Fetch actual game scores from ESPN. Returns dict keyed by team name AND 'away@home'."""
    url = ESPN_ENDPOINTS.get(sport)
    if not url:
        logger.error(f"No ESPN endpoint for sport: {sport}")
        return {}

    date_str = game_date.replace('-', '')
    try:
        # ESPN sometimes needs group param for NCAAB to get all games
        params = {'dates': date_str}
        if sport == 'NCAAB':
            params['limit'] = 200
            params['groups'] = 50  # Division I

        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"ESPN fetch failed for {sport} {game_date}: {e}")
        return {}

    results = {}
    for event in data.get('events', []):
        comps = event.get('competitions', [])
        if not comps:
            continue
        comp = comps[0]
        status = comp.get('status', {}).get('type', {}).get('name', '')
        if status != 'STATUS_FINAL':
            continue

        teams_data = comp.get('competitors', [])
        if len(teams_data) < 2:
            continue

        home = away = None
        home_score = away_score = 0
        for t in teams_data:
            team_name = t.get('team', {}).get('displayName', '')
            score = int(t.get('score', 0))
            if t.get('homeAway') == 'home':
                home = normalize_team(team_name)
                home_score = score
            else:
                away = normalize_team(team_name)
                away_score = score

        if home and away:
            winner = home if home_score > away_score else away
            result = {
                'home_team': home, 'away_team': away,
                'home_score': home_score, 'away_score': away_score,
                'winner': winner, 'total': home_score + away_score,
                'margin': home_score - away_score,
            }
            # Multiple lookup keys
            results[home] = result
            results[away] = result
            results[f"{away}@{home}"] = result
            results[f"{away}@{home}_{game_date}"] = result

    logger.info(f"ESPN: {len([v for k,v in results.items() if '@' in k])} final {sport} games for {game_date}")
    return results


def _match_result(pick: Dict, results: Dict) -> Optional[Dict]:
    """Find the ESPN result matching a pick."""
    home = normalize_team(pick.get('home_team', ''))
    away = normalize_team(pick.get('away_team', ''))

    for key in [f"{away}@{home}", f"{away}@{home}_{pick.get('pick_date','')}",
                home, away]:
        if key in results:
            r = results[key]
            # Verify it's actually this game
            if normalize_team(r['home_team']) == home or normalize_team(r['away_team']) == away:
                return r
    return None


def score_picks_for_date(db: ResultsDB, game_date: str, sport: str = 'NBA',
                         dry_run: bool = False) -> Dict:
    """Score all picks for a given date against actual results."""
    picks = db.get_picks_for_date(game_date, sport=sport)
    if not picks:
        logger.warning(f"No picks found for {game_date} ({sport})")
        return {'error': 'no picks'}

    pending = [p for p in picks if p.get('game_status') == 'pending']
    if not pending:
        logger.info(f"All {len(picks)} picks for {game_date} already scored")
        return {'already_scored': True, 'total': len(picks)}

    results = fetch_espn_scores(game_date, sport)
    if not results:
        logger.error(f"No ESPN results for {game_date}")
        return {'error': 'no espn results'}

    stats = {'ml_correct': 0, 'ml_total': 0,
             'spread_correct': 0, 'spread_total': 0,
             'ou_correct': 0, 'ou_total': 0,
             'matched': 0, 'unmatched': 0}

    for pick in pending:
        r = _match_result(pick, results)
        if not r:
            stats['unmatched'] += 1
            logger.warning(f"  No result for {pick.get('away_team','')} @ {pick.get('home_team','')}")
            continue

        stats['matched'] += 1
        game_id = pick['game_id']

        if dry_run:
            predicted = pick.get('predicted_winner', '')
            ml_hit = predicted == r['winner']
            emoji = "✅" if ml_hit else "❌"
            logger.info(f"  [DRY-RUN] {emoji} {pick['away_team']} @ {pick['home_team']}: "
                         f"picked {predicted} | Actual: {r['winner']} "
                         f"({r['away_score']}-{r['home_score']})")
            if ml_hit:
                stats['ml_correct'] += 1
            stats['ml_total'] += 1
            continue

        # Store outcome (this also grades ML/spread/O/U)
        db.store_outcome(game_id, game_date, r)

        # Re-fetch graded pick for stats
        graded = db.get_picks_for_date(game_date, sport)
        for g in graded:
            if g['game_id'] == game_id:
                if g['ml_correct'] is not None:
                    stats['ml_total'] += 1
                    if g['ml_correct']:
                        stats['ml_correct'] += 1
                if g['spread_correct'] is not None:
                    stats['spread_total'] += 1
                    if g['spread_correct']:
                        stats['spread_correct'] += 1
                if g['ou_correct'] is not None:
                    stats['ou_total'] += 1
                    if g['ou_correct']:
                        stats['ou_correct'] += 1
                break

    # Compute accuracies
    stats['ml_accuracy'] = round(stats['ml_correct'] / stats['ml_total'] * 100, 1) if stats['ml_total'] else 0
    stats['spread_accuracy'] = round(stats['spread_correct'] / stats['spread_total'] * 100, 1) if stats['spread_total'] else 0
    stats['ou_accuracy'] = round(stats['ou_correct'] / stats['ou_total'] * 100, 1) if stats['ou_total'] else 0
    stats['total'] = len(pending)

    # Save daily summary
    if not dry_run:
        db.save_daily_summary(game_date, sport, stats)

    # Print summary
    logger.info(f"\n{'[DRY-RUN] ' if dry_run else ''}=== {game_date} {sport} Results ===")
    logger.info(f"  ML:     {stats['ml_correct']}/{stats['ml_total']} ({stats['ml_accuracy']}%)")
    logger.info(f"  Spread: {stats['spread_correct']}/{stats['spread_total']} ({stats['spread_accuracy']}%)")
    logger.info(f"  O/U:    {stats['ou_correct']}/{stats['ou_total']} ({stats['ou_accuracy']}%)")
    logger.info(f"  Matched: {stats['matched']}, Unmatched: {stats['unmatched']}")

    return stats


def score_all_pending(db: ResultsDB, dry_run: bool = False) -> Dict:
    """Score all pending picks across all dates."""
    pending = db.get_pending_picks()
    if not pending:
        logger.info("No pending picks to score")
        return {}

    # Group by date+sport
    groups = {}
    for p in pending:
        key = (p['pick_date'], p.get('sport', 'NBA'))
        groups.setdefault(key, []).append(p)

    all_stats = {}
    for (d, s), picks in sorted(groups.items()):
        logger.info(f"\nScoring {len(picks)} pending picks for {d} ({s})...")
        stats = score_picks_for_date(db, d, s, dry_run=dry_run)
        all_stats[f"{d}_{s}"] = stats

    return all_stats


def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Results Scorer')
    parser.add_argument('--date', type=str, help='Date to score (YYYY-MM-DD). Default: yesterday')
    parser.add_argument('--sport', type=str, default='NBA', help='Sport (NBA, NCAAB, NFL, etc.)')
    parser.add_argument('--pending', action='store_true', help='Score all pending picks')
    parser.add_argument('--dry-run', action='store_true', help='Preview without storing')
    parser.add_argument('--db', type=str, help='Custom DB path')
    args = parser.parse_args()

    from pathlib import Path
    db_path = Path(args.db) if args.db else None
    db = ResultsDB(db_path) if db_path else ResultsDB()

    if args.pending:
        score_all_pending(db, dry_run=args.dry_run)
    else:
        game_date = args.date or (date.today() - timedelta(days=1)).isoformat()
        score_picks_for_date(db, game_date, args.sport, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
