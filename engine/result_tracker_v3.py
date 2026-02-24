"""
Result Tracker v3 — ParlayGuarantee
Scores ALL categories separately with full isolation.

Categories:
  NBA: ML, Spread, O/U (each separate)
  NCAAB: ML, Spread, O/U (each separate)
  Parlays: NBA spread, NCAAB spread, Mixed spread (by leg count)
  Parlays: NBA O/U, NCAAB O/U, Mixed O/U (by leg count)

Usage:
  python result_tracker_v3.py --date 2026-02-20
  python result_tracker_v3.py  # Scores yesterday
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import logging
import sqlite3
import requests
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent


class ResultTrackerV3:
    def __init__(self):
        self.nba_scores = {}  # "Away @ Home" -> {home_score, away_score, total}
        self.ncaab_scores = {}

    def fetch_scores(self, target_date: date, sport: str = 'nba'):
        """Fetch final scores from ESPN."""
        league = 'nba' if sport == 'nba' else 'mens-college-basketball'
        dt_str = target_date.strftime('%Y%m%d')
        # groups=50&limit=500 ensures we get ALL D1 games, not just featured
        extra = '&groups=50&limit=500' if sport == 'ncaab' else ''
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard?dates={dt_str}{extra}"

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            scores = {}
            for event in data.get('events', []):
                status = event.get('status', {}).get('type', {}).get('name', '')
                if status != 'STATUS_FINAL':
                    continue
                comps = event.get('competitions', [{}])[0]
                competitors = comps.get('competitors', [])
                home_data = away_data = None
                for c in competitors:
                    if c.get('homeAway') == 'home':
                        home_data = c
                    else:
                        away_data = c
                if not home_data or not away_data:
                    continue

                home_name = home_data['team'].get('displayName', '')
                away_name = away_data['team'].get('displayName', '')
                home_score = int(home_data.get('score', 0))
                away_score = int(away_data.get('score', 0))

                key = f"{away_name} @ {home_name}"
                scores[key] = {
                    'home_team': home_name,
                    'away_team': away_name,
                    'home_score': home_score,
                    'away_score': away_score,
                    'total': home_score + away_score,
                    'winner': home_name if home_score > away_score else away_name,
                }

            logger.info(f"ESPN {sport.upper()}: {len(scores)} final games for {target_date}")

            if sport == 'nba':
                self.nba_scores = scores
            else:
                self.ncaab_scores = scores
            return scores
        except Exception as e:
            logger.error(f"ESPN {sport} scores error: {e}")
            return {}

    def score_spread_picks(self, picks: List[Dict], scores: Dict, sport: str) -> Dict:
        """Score spread/ML picks against actual results."""
        ml_correct = ml_total = 0
        spread_correct = spread_total = 0
        results = []

        for pick in picks:
            home = pick.get('home_team', '')
            away = pick.get('away_team', '')
            predicted = pick.get('predicted_winner', '')
            confidence = pick.get('confidence', 0)

            # Find matching score (fuzzy on team names)
            actual = self._find_score(home, away, scores)
            if not actual:
                results.append({'matchup': f"{away} @ {home}", 'status': 'no_result'})
                continue

            # ML
            ml_total += 1
            ml_hit = predicted == actual['winner'] or self._fuzzy_eq(predicted, actual['winner'])
            if ml_hit:
                ml_correct += 1

            # Spread
            spread_pick = pick.get('spread_pick', '')
            if spread_pick:
                spread_total += 1
                margin = actual['home_score'] - actual['away_score']
                spread_val = pick.get('spread', 0)
                # Home team + spread > 0 means home covered
                if spread_pick == home:
                    covered = (margin + spread_val) > 0
                else:
                    covered = (-margin - spread_val) > 0
                if covered:
                    spread_correct += 1

            results.append({
                'matchup': f"{away} @ {home}",
                'predicted': predicted,
                'actual_winner': actual['winner'],
                'score': f"{actual['away_score']}-{actual['home_score']}",
                'ml_hit': ml_hit,
                'confidence': confidence,
            })

        return {
            'sport': sport,
            'ml': {'correct': ml_correct, 'total': ml_total,
                   'pct': round(ml_correct / ml_total * 100, 1) if ml_total > 0 else 0},
            'spread': {'correct': spread_correct, 'total': spread_total,
                       'pct': round(spread_correct / spread_total * 100, 1) if spread_total > 0 else 0},
            'results': results,
        }

    def score_ou_picks(self, picks: List[Dict], scores: Dict, sport: str) -> Dict:
        """Score O/U picks against actual results."""
        correct = total = 0
        results = []

        for pick in picks:
            if pick.get('pick', 'PASS') == 'PASS':
                continue

            home = pick.get('home_team', '')
            away = pick.get('away_team', '')
            posted = pick.get('posted_total', 0)
            ou_pick = pick.get('pick', '')
            edge = pick.get('edge', 0)

            actual = self._find_score(home, away, scores)
            if not actual:
                results.append({'matchup': f"{away} @ {home}", 'status': 'no_result'})
                continue

            actual_total = actual['total']
            actual_result = 'OVER' if actual_total > posted else 'UNDER'
            hit = ou_pick == actual_result

            total += 1
            if hit:
                correct += 1

            results.append({
                'matchup': f"{away} @ {home}",
                'pick': f"{ou_pick} {posted}",
                'actual_total': actual_total,
                'actual_result': actual_result,
                'edge': edge,
                'hit': hit,
            })

        return {
            'sport': sport,
            'correct': correct,
            'total': total,
            'pct': round(correct / total * 100, 1) if total > 0 else 0,
            'results': results,
        }

    def score_parlays(self, parlays: List[Dict], scores: Dict, pick_type: str) -> Dict:
        """Score parlays by leg count."""
        by_legs = defaultdict(lambda: {'hit': 0, 'total': 0})

        for parlay in parlays:
            legs = parlay.get('legs', [])
            num_legs = parlay.get('num_legs', len(legs))
            all_hit = True

            for leg in legs:
                matchup = leg.get('matchup', '')
                # Parse "Away @ Home"
                parts = matchup.split(' @ ')
                if len(parts) != 2:
                    all_hit = False
                    continue

                away_name, home_name = parts[0].strip(), parts[1].strip()
                actual = self._find_score(home_name, away_name, scores)
                if not actual:
                    all_hit = False
                    continue

                if pick_type == 'ou':
                    pick_str = leg.get('pick', '')
                    # Parse "OVER 220.5" or "UNDER 220.5"
                    pick_parts = pick_str.split()
                    if len(pick_parts) < 2:
                        all_hit = False
                        continue
                    ou_pick = pick_parts[0]
                    try:
                        posted = float(pick_parts[1])
                    except:
                        all_hit = False
                        continue
                    actual_result = 'OVER' if actual['total'] > posted else 'UNDER'
                    if ou_pick != actual_result:
                        all_hit = False
                else:
                    predicted = leg.get('pick', '')
                    if not self._fuzzy_eq(predicted, actual['winner']):
                        all_hit = False

            by_legs[num_legs]['total'] += 1
            if all_hit:
                by_legs[num_legs]['hit'] += 1

        result = {}
        for legs, data in sorted(by_legs.items()):
            pct = round(data['hit'] / data['total'] * 100, 1) if data['total'] > 0 else 0
            result[f"{legs}-leg"] = {'hit': data['hit'], 'total': data['total'], 'pct': pct}
        return result

    def _find_score(self, home: str, away: str, scores: Dict) -> Optional[Dict]:
        """Find score with fuzzy matching."""
        # Exact match
        key = f"{away} @ {home}"
        if key in scores:
            return scores[key]

        # Fuzzy: try partial matching
        for k, v in scores.items():
            if (self._fuzzy_eq(home, v['home_team']) and
                self._fuzzy_eq(away, v['away_team'])):
                return v
        return None

    def _fuzzy_eq(self, a: str, b: str) -> bool:
        """Fuzzy string comparison for team names."""
        if a == b:
            return True
        a_l, b_l = a.lower(), b.lower()
        if a_l == b_l:
            return True
        # Check if one contains the other
        if a_l in b_l or b_l in a_l:
            return True
        # First word match
        if a_l.split()[0] == b_l.split()[0] and a_l.split()[-1] == b_l.split()[-1]:
            return True
        return False


def run(target_date: date):
    """Score all picks for a date."""
    tracker = ResultTrackerV3()

    # Fetch scores
    tracker.fetch_scores(target_date, 'nba')
    tracker.fetch_scores(target_date, 'ncaab')

    picks_dir = ENGINE_DIR / f"picks_{target_date}"

    print(f"\n{'='*60}")
    print(f"  RESULT TRACKER v3 — {target_date}")
    print(f"{'='*60}")

    # ─── NBA Spread/ML ───
    nba_spread_file = picks_dir / "nba_spreads.json"
    if nba_spread_file.exists():
        nba_spread = json.load(open(nba_spread_file))
        result = tracker.score_spread_picks(nba_spread, tracker.nba_scores, 'nba')
        print(f"\n  NBA Moneyline: {result['ml']['correct']}/{result['ml']['total']} ({result['ml']['pct']}%)")
        print(f"  NBA Spread:    {result['spread']['correct']}/{result['spread']['total']} ({result['spread']['pct']}%)")
        for r in result['results']:
            if r.get('status') == 'no_result':
                continue
            emoji = 'HIT' if r['ml_hit'] else 'MISS'
            print(f"    {emoji} {r['matchup']}: picked {r['predicted']} → winner {r['actual_winner']} ({r['score']})")

    # ─── NCAAB Spread/ML ───
    ncaab_spread_file = picks_dir / "ncaab_spreads.json"
    if ncaab_spread_file.exists():
        ncaab_spread = json.load(open(ncaab_spread_file))
        result = tracker.score_spread_picks(ncaab_spread, tracker.ncaab_scores, 'ncaab')
        print(f"\n  NCAAB Moneyline: {result['ml']['correct']}/{result['ml']['total']} ({result['ml']['pct']}%)")
        print(f"  NCAAB Spread:    {result['spread']['correct']}/{result['spread']['total']} ({result['spread']['pct']}%)")

    # ─── NBA O/U (ISOLATED) ───
    nba_ou_file = picks_dir / "nba_totals.json"
    if nba_ou_file.exists():
        nba_ou = json.load(open(nba_ou_file))
        result = tracker.score_ou_picks(nba_ou, tracker.nba_scores, 'nba')
        print(f"\n  NBA O/U: {result['correct']}/{result['total']} ({result['pct']}%) [ISOLATED]")
        for r in result['results']:
            if r.get('status') == 'no_result':
                continue
            emoji = 'HIT' if r['hit'] else 'MISS'
            print(f"    {emoji} {r['matchup']}: {r['pick']} → actual {r['actual_total']} ({r['actual_result']}) edge {r['edge']:+.1f}")

    # ─── NCAAB O/U (ISOLATED) ───
    ncaab_ou_file = picks_dir / "ncaab_totals.json"
    if ncaab_ou_file.exists():
        ncaab_ou = json.load(open(ncaab_ou_file))
        result = tracker.score_ou_picks(ncaab_ou, tracker.ncaab_scores, 'ncaab')
        print(f"\n  NCAAB O/U: {result['correct']}/{result['total']} ({result['pct']}%) [ISOLATED]")

    # ─── Parlays ───
    parlay_categories = [
        ('parlays_nba_spread.json', tracker.nba_scores, 'spread', 'NBA Spread Parlays'),
        ('parlays_ncaab_spread.json', tracker.ncaab_scores, 'spread', 'NCAAB Spread Parlays'),
        ('parlays_mixed_spread.json', {**tracker.nba_scores, **tracker.ncaab_scores}, 'spread', 'Mixed Spread Parlays'),
        ('parlays_nba_ou.json', tracker.nba_scores, 'ou', 'NBA O/U Parlays [ISOLATED]'),
        ('parlays_ncaab_ou.json', tracker.ncaab_scores, 'ou', 'NCAAB O/U Parlays [ISOLATED]'),
        ('parlays_mixed_ou.json', {**tracker.nba_scores, **tracker.ncaab_scores}, 'ou', 'Mixed O/U Parlays [ISOLATED]'),
    ]

    for filename, scores, ptype, label in parlay_categories:
        pfile = picks_dir / filename
        if pfile.exists():
            parlays = json.load(open(pfile))
            if parlays:
                result = tracker.score_parlays(parlays, scores, ptype)
                if result:
                    print(f"\n  {label}:")
                    for legs, data in result.items():
                        print(f"    {legs}: {data['hit']}/{data['total']} ({data['pct']}%)")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    target = date.today() - timedelta(days=1)  # Default to yesterday
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target = date.fromisoformat(sys.argv[idx + 1])
    run(target)
