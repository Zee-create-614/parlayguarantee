"""
NCAAB Backtest Script for ParlayGuarantee
Validates the NCAAB engine accuracy against historical results.

Usage:
    python ncaab_backtest.py                        # Backtest last 7 days
    python ncaab_backtest.py --days 30              # Backtest last 30 days
    python ncaab_backtest.py --start 2026-01-01 --end 2026-02-15
"""

import sys
import json
import os
import logging
import sqlite3
import argparse
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(ENGINE_DIR, 'ncaab_backtest.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

from ncaab_data_fetcher import NCAABDataFetcher

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"


def fetch_ncaab_scores(target_date: date) -> List[Dict]:
    """
    Fetch completed NCAAB game scores. 
    Primary: ESPN scoreboard. Fallback: Odds API scores endpoint.
    """
    import requests
    
    # Try ESPN first (free, no API key, reliable)
    results = _fetch_scores_espn(target_date)
    if results:
        return results
    
    # Fallback: Odds API
    return _fetch_scores_odds_api(target_date)


def _fetch_scores_espn(target_date: date) -> List[Dict]:
    """Fetch NCAAB scores from ESPN scoreboard API."""
    import requests
    dt_str = target_date.strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={dt_str}&limit=200"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"ESPN NCAAB scores failed: {e}")
        return []
    
    results = []
    for event in data.get('events', []):
        comp = event.get('competitions', [{}])[0]
        status = comp.get('status', {}).get('type', {}).get('name', '')
        if status != 'STATUS_FINAL':
            continue
        
        competitors = comp.get('competitors', [])
        if len(competitors) < 2:
            continue
        
        home_data = away_data = None
        for c in competitors:
            if c.get('homeAway') == 'home':
                home_data = c
            else:
                away_data = c
        
        if not home_data or not away_data:
            continue
        
        home_name = home_data['team'].get('displayName', '') or home_data['team'].get('shortDisplayName', '')
        away_name = away_data['team'].get('displayName', '') or away_data['team'].get('shortDisplayName', '')
        home_score = int(home_data.get('score', 0))
        away_score = int(away_data.get('score', 0))
        
        winner = home_name if home_score > away_score else away_name
        results.append({
            'game_id': event.get('id', ''),
            'home_team': home_name,
            'away_team': away_name,
            'home_score': home_score,
            'away_score': away_score,
            'winner': winner,
            'margin': abs(home_score - away_score),
        })
    
    logger.info(f"ESPN: {len(results)} completed NCAAB games for {target_date}")
    return results


def _fetch_scores_odds_api(target_date: date) -> List[Dict]:
    """Fallback: Fetch NCAAB scores from Odds API."""
    import requests
    from datetime import timedelta
    
    today = date.today()
    days_back = (today - target_date).days
    
    url = f"https://api.the-odds-api.com/v4/sports/basketball_ncaab/scores"
    params = {
        'apiKey': ODDS_API_KEY,
        'daysFrom': max(1, min(days_back + 1, 3)),
        'dateFormat': 'iso',
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch scores: {e}")
        return []

    results = []
    target_str = target_date.isoformat()
    for ev in events:
        if not ev.get('completed', False):
            continue
        # Handle UTC → EST date matching (games at 00:00-05:00 UTC = previous day EST)
        commence = ev.get('commence_time', '')
        if commence:
            from datetime import datetime as dt2, timezone
            try:
                utc_dt = dt2.fromisoformat(commence.replace('Z', '+00:00'))
                est_dt = utc_dt + timedelta(hours=-5)
                game_date_str = est_dt.date().isoformat()
            except:
                game_date_str = commence[:10]
        else:
            game_date_str = ''
        
        if game_date_str != target_str:
            continue

        scores = ev.get('scores', [])
        if not scores or len(scores) < 2:
            continue

        home_team = ev.get('home_team', '')
        away_team = ev.get('away_team', '')
        home_score, away_score = None, None
        for s in scores:
            if s['name'] == home_team:
                home_score = int(s['score'])
            elif s['name'] == away_team:
                away_score = int(s['score'])

        if home_score is not None and away_score is not None:
            winner = home_team if home_score > away_score else away_team
            results.append({
                'game_id': ev.get('id', ''),
                'home_team': home_team,
                'away_team': away_team,
                'home_score': home_score,
                'away_score': away_score,
                'winner': winner,
                'margin': abs(home_score - away_score),
            })

    logger.info(f"Odds API: {len(results)} completed NCAAB games for {target_date}")
    return results


def backtest_date(engine, target_date: date, scores: List[Dict]) -> Dict:
    """Run engine for a date and score against actual results.
    Since the Odds API only has upcoming games, for backtesting we build
    'fake' game dicts from ESPN scores and run the engine's analysis on them.
    """
    from ncaab_engine import NCAABEngine

    # For past dates, construct game list from the scores themselves
    # (since Odds API won't have historical odds)
    if scores:
        # Build games from scores and run engine analysis on each
        rankings = engine.fetcher.fetch_espn_rankings()
        rank_map = {r['team'].lower(): r['rank'] for r in rankings}
        
        analyzed = []
        for s in scores:
            # Build a minimal game dict the engine can analyze
            game = {
                'home_team': s['home_team'],
                'away_team': s['away_team'],
                'game_id': s.get('game_id', ''),
                'commence_time': target_date.isoformat(),
                'h2h_home': None,
                'h2h_away': None,
                'spread_home': None,
                'spread_value': None,
                'total': None,
            }
            try:
                pred = engine._analyze_game(game, rank_map, None)
                if pred:
                    analyzed.append(pred)
            except Exception as e:
                logger.debug(f"Could not analyze {s['away_team']}@{s['home_team']}: {e}")
    else:
        # Try live odds for today/future
        analyzed = engine.predict_games(target_date=target_date)

    if not analyzed:
        return {'date': target_date.isoformat(), 'games': 0, 'skipped': True}

    # Build score lookup
    score_map = {}
    for s in scores:
        score_map[s['home_team'].lower()] = s
        score_map[s['away_team'].lower()] = s
        score_map[s['game_id']] = s

    # Score picks
    results = {
        'date': target_date.isoformat(),
        'games': len(analyzed),
        'ml_correct': 0, 'ml_total': 0,
        'spread_correct': 0, 'spread_total': 0,
        'by_label': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'by_confidence': defaultdict(lambda: {'correct': 0, 'total': 0}),
        'picks': [],
    }

    for game in analyzed:
        # Find actual result
        actual = (score_map.get(game['game_id']) or
                  score_map.get(game['home_team'].lower()) or
                  score_map.get(game['away_team'].lower()))

        if not actual:
            continue

        # Moneyline
        predicted = game['predicted_winner']
        actual_winner = actual['winner']
        ml_correct = predicted.lower() in actual_winner.lower() or actual_winner.lower() in predicted.lower()

        results['ml_total'] += 1
        if ml_correct:
            results['ml_correct'] += 1

        # By label (determine based on confidence since NCAAB doesn't have explicit labels)
        conf = game['confidence']
        if conf >= 0.75:
            label = 'LOCK'
        elif conf >= 0.65:
            label = 'VALUE'  
        elif conf >= 0.58:
            label = 'UPSET'
        else:
            label = 'LEAN'
        results['by_label'][label]['total'] += 1
        if ml_correct:
            results['by_label'][label]['correct'] += 1

        # By confidence bucket (using already defined conf variable)
        if conf >= 0.70:
            bucket = '70%+'
        elif conf >= 0.60:
            bucket = '60-70%'
        elif conf >= 0.55:
            bucket = '55-60%'
        else:
            bucket = '<55%'
        results['by_confidence'][bucket]['total'] += 1
        if ml_correct:
            results['by_confidence'][bucket]['correct'] += 1

        # Spread
        if game.get('spread_pick'):
            margin = actual['home_score'] - actual['away_score']
            
            # Determine if our spread pick was on home or away
            home_in_pick = game['home_team'].lower() in game['spread_pick'].lower()
            
            # Extract spread value from the pick (format: "Team Name +3.5" or "Team Name -3.5")
            try:
                spread_str = game['spread_pick'].split()[-1]  # Get the last part (e.g., "+3.5")
                spread = float(spread_str)
                
                if home_in_pick:
                    # Home team spread pick: home covers if actual margin + spread > 0
                    spread_correct = margin + spread > 0
                else:
                    # Away team spread pick: away covers if actual margin - spread < 0
                    spread_correct = margin - abs(spread) < 0
                
                results['spread_total'] += 1
                if spread_correct:
                    results['spread_correct'] += 1
            except (ValueError, IndexError):
                # Skip if we can't parse the spread
                pass

        results['picks'].append({
            'home': game['home_team'],
            'away': game['away_team'],
            'pick': predicted,
            'actual': actual_winner,
            'correct': ml_correct,
            'confidence': game['confidence'],
            'label': label,
        })

    return results


def run_backtest(start_date: date, end_date: date):
    """Run backtest over date range."""
    from ncaab_engine import NCAABEngine

    logger.info(f"=== NCAAB Backtest: {start_date} to {end_date} ===")

    engine = NCAABEngine()
    all_results = []
    total_ml_correct, total_ml = 0, 0
    total_sp_correct, total_sp = 0, 0
    label_agg = defaultdict(lambda: {'correct': 0, 'total': 0})
    conf_agg = defaultdict(lambda: {'correct': 0, 'total': 0})

    current = start_date
    while current <= end_date:
        logger.info(f"Processing {current}...")

        # Fetch scores
        scores = fetch_ncaab_scores(current)
        if not scores:
            logger.info(f"  No scores available for {current}")
            current += timedelta(days=1)
            time.sleep(1)
            continue

        # Run engine + score
        result = backtest_date(engine, current, scores)
        if result.get('skipped'):
            current += timedelta(days=1)
            time.sleep(1)
            continue

        all_results.append(result)
        total_ml_correct += result['ml_correct']
        total_ml += result['ml_total']
        total_sp_correct += result['spread_correct']
        total_sp += result['spread_total']

        for label, data in result['by_label'].items():
            label_agg[label]['correct'] += data['correct']
            label_agg[label]['total'] += data['total']
        for bucket, data in result['by_confidence'].items():
            conf_agg[bucket]['correct'] += data['correct']
            conf_agg[bucket]['total'] += data['total']

        ml_pct = result['ml_correct'] / result['ml_total'] * 100 if result['ml_total'] else 0
        logger.info(f"  {current}: ML {result['ml_correct']}/{result['ml_total']} ({ml_pct:.0f}%) | "
                     f"ATS {result['spread_correct']}/{result['spread_total']}")

        current += timedelta(days=1)
        time.sleep(2)  # Rate limit

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"NCAAB BACKTEST RESULTS: {start_date} → {end_date}")
    print(f"{'='*60}")

    ml_pct = total_ml_correct / total_ml * 100 if total_ml else 0
    sp_pct = total_sp_correct / total_sp * 100 if total_sp else 0
    print(f"\nMoneyline: {total_ml_correct}/{total_ml} ({ml_pct:.1f}%)")
    print(f"Spread:    {total_sp_correct}/{total_sp} ({sp_pct:.1f}%)")
    print(f"Days with games: {len(all_results)}")

    print(f"\nBy Pick Label:")
    for label in ['LOCK', 'VALUE', 'UPSET', 'LEAN']:
        data = label_agg.get(label, {'correct': 0, 'total': 0})
        pct = data['correct'] / data['total'] * 100 if data['total'] else 0
        print(f"  {label:8s}: {data['correct']}/{data['total']} ({pct:.1f}%)")

    print(f"\nBy Confidence:")
    for bucket in ['70%+', '60-70%', '55-60%', '<55%']:
        data = conf_agg.get(bucket, {'correct': 0, 'total': 0})
        pct = data['correct'] / data['total'] * 100 if data['total'] else 0
        print(f"  {bucket:8s}: {data['correct']}/{data['total']} ({pct:.1f}%)")

    # Save results
    output = {
        'backtest_range': f"{start_date} to {end_date}",
        'moneyline_accuracy': round(ml_pct, 2),
        'spread_accuracy': round(sp_pct, 2),
        'total_ml_picks': total_ml,
        'total_spread_picks': total_sp,
        'by_label': {k: dict(v) for k, v in label_agg.items()},
        'by_confidence': {k: dict(v) for k, v in conf_agg.items()},
        'daily_results': [{k: v for k, v in r.items() if k != 'picks'} for r in all_results],
    }

    out_path = os.path.join(ENGINE_DIR, 'ncaab_backtest_results.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=str)
    logger.info(f"Results saved to {out_path}")

    return output


def main():
    parser = argparse.ArgumentParser(description='NCAAB Engine Backtest')
    parser.add_argument('--days', type=int, default=7, help='Number of days to backtest')
    parser.add_argument('--start', type=str, default=None, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='End date (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=args.days - 1)

    run_backtest(start, end)


if __name__ == '__main__':
    main()
