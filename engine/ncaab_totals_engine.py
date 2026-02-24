"""
NCAAB Over/Under (Totals) Prediction Engine
Same methodology as NBA totals engine, adapted for college basketball.

College-specific factors:
- Wider pace variance (shot clock differences, coaching styles)
- More blowouts (bigger talent gaps)
- Stronger home court advantage
- Conference-level defensive tendencies

Usage:
  python ncaab_totals_engine.py                    # Today's predictions
  python ncaab_totals_engine.py --date 2026-02-20  # Specific date
  python ncaab_totals_engine.py --score 2026-02-20 # Score results
"""

import json
import logging
import math
import sys
import requests
import sqlite3
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "ncaab_totals.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# NCAAB averages (2024-25 season)
LEAGUE_AVG_PPG = 74.0
LEAGUE_AVG_PACE = 68.0  # possessions per 40 min (college = 40 min games)


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ncaab_totals_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date DATE,
        home_team TEXT,
        away_team TEXT,
        predicted_total REAL,
        posted_total REAL,
        pick TEXT,
        confidence REAL,
        edge REAL,
        factors TEXT,
        actual_total REAL,
        result TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(game_date, home_team, away_team)
    )''')
    conn.commit()
    conn.close()


class NCAABTotalsEngine:
    def __init__(self):
        init_db()
        self.team_stats = {}

    def fetch_team_stats_espn(self, team_name: str) -> Optional[Dict]:
        """Fetch a team's stats using the existing ncaab_data_fetcher (has caching)."""
        if team_name in self.team_stats:
            return self.team_stats[team_name]

        # Use the existing NCAAB data fetcher which has DB + memory caching
        try:
            from ncaab_data_fetcher import NCAABDataFetcher
            if not hasattr(self, '_fetcher'):
                self._fetcher = NCAABDataFetcher()
            stats = self._fetcher.fetch_espn_team_stats(team_name)
            if stats:
                # off_efficiency/def_efficiency are per 100 possessions
                # Convert to actual PPG using tempo: PPG = efficiency * tempo / 100
                tempo = stats.get('tempo', LEAGUE_AVG_PACE)
                off_eff = stats.get('off_efficiency', 100)
                def_eff = stats.get('def_efficiency', 100)
                ppg = off_eff * tempo / 100 if off_eff > 50 else LEAGUE_AVG_PPG
                papg = def_eff * tempo / 100 if def_eff > 50 else LEAGUE_AVG_PPG
                
                result = {
                    'ppg': round(ppg, 1),
                    'papg': round(papg, 1),
                    'wins': stats.get('wins', 10),
                    'losses': stats.get('losses', 10),
                    'pace': tempo,
                    'off_eff': off_eff,
                    'def_eff': def_eff,
                }
                self.team_stats[team_name] = result
                return result
        except Exception as e:
            logger.debug(f"NCAAB fetcher failed for {team_name}: {e}")

        # Fallback: default stats
        default = {
            'ppg': LEAGUE_AVG_PPG,
            'papg': LEAGUE_AVG_PPG,
            'wins': 10,
            'losses': 10,
            'pace': LEAGUE_AVG_PACE,
        }
        self.team_stats[team_name] = default
        return default

    def fetch_todays_games(self, target_date: date = None) -> List[Dict]:
        """Fetch today's NCAAB games with posted totals from Odds API."""
        if target_date is None:
            target_date = date.today()

        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'totals,spreads,h2h',
            'oddsFormat': 'american',
        }
        url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
        try:
            resp = requests.get(url, params=params, timeout=30)
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"Odds API remaining: {remaining}")
            if resp.status_code != 200:
                logger.error(f"Odds API error: {resp.status_code}")
                return []

            games = []
            for g in resp.json():
                commence = g.get('commence_time', '')
                if commence:
                    utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    est_dt = utc_dt + timedelta(hours=-5)
                    game_date = est_dt.date().isoformat()
                else:
                    game_date = target_date.isoformat()

                if game_date != target_date.isoformat():
                    continue

                home = g['home_team']
                away = g['away_team']

                totals = []
                spreads_home = []
                for bookie in g.get('bookmakers', []):
                    for mkt in bookie.get('markets', []):
                        if mkt['key'] == 'totals':
                            for o in mkt['outcomes']:
                                if o['name'] == 'Over':
                                    totals.append(o.get('point', 0))
                        elif mkt['key'] == 'spreads':
                            for o in mkt['outcomes']:
                                if o['name'] == home:
                                    spreads_home.append(o.get('point', 0))

                if not totals:
                    continue

                posted_total = sum(totals) / len(totals)
                spread = sum(spreads_home) / len(spreads_home) if spreads_home else 0

                games.append({
                    'home_team': home,
                    'away_team': away,
                    'posted_total': round(posted_total, 1),
                    'spread': round(spread, 1),
                    'commence_time': commence,
                    'game_date': game_date,
                })

            logger.info(f"Found {len(games)} NCAAB games with totals for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Error fetching games: {e}")
            return []

    def predict_total(self, home: str, away: str, posted_total: float,
                      spread: float = 0) -> Dict:
        """
        Predict game total for NCAAB.
        College-specific adjustments vs NBA model:
        - Stronger home court (college = ~3.5 pts vs NBA ~1.5)
        - Higher regression weight (more variance in college)
        - Bigger blowout adjustments
        """
        h_stats = self.fetch_team_stats_espn(home) or {}
        a_stats = self.fetch_team_stats_espn(away) or {}

        h_ppg = h_stats.get('ppg', LEAGUE_AVG_PPG)
        h_papg = h_stats.get('papg', LEAGUE_AVG_PPG)
        a_ppg = a_stats.get('ppg', LEAGUE_AVG_PPG)
        a_papg = a_stats.get('papg', LEAGUE_AVG_PPG)

        # --- Base projected total ---
        home_expected_raw = (h_ppg + a_papg) / 2
        away_expected_raw = (a_ppg + h_papg) / 2
        raw_total = home_expected_raw + away_expected_raw

        # Heavy regression for college (more variance, less predictable)
        regression_weight = 0.55
        league_avg_total = 2 * LEAGUE_AVG_PPG
        base_total = raw_total * (1 - regression_weight) + league_avg_total * regression_weight
        home_expected = base_total / 2 + (home_expected_raw - away_expected_raw) / 2
        away_expected = base_total - home_expected

        factors = {
            'home_expected_pts': round(home_expected, 1),
            'away_expected_pts': round(away_expected, 1),
            'base_total': round(base_total, 1),
        }

        pace_adjusted = base_total

        # --- Home court (stronger in college) ---
        home_bump = 1.0
        pace_adjusted += home_bump
        factors['home_bump'] = home_bump

        # --- Blowout/close game effect ---
        spread_abs = abs(spread)
        if spread_abs >= 18:
            blowout_adj = -4.0  # huge mismatch, starters pulled early
        elif spread_abs >= 12:
            blowout_adj = -2.0
        elif spread_abs >= 7:
            blowout_adj = -0.5
        elif spread_abs <= 2:
            blowout_adj = -1.0  # tight = slow, grind-it-out
        else:
            blowout_adj = 0
        pace_adjusted += blowout_adj
        factors['blowout_adj'] = blowout_adj

        # --- Defense adjustment ---
        h_def_rank = h_papg - LEAGUE_AVG_PPG
        a_def_rank = a_papg - LEAGUE_AVG_PPG
        combined_def = (h_def_rank + a_def_rank) / 2
        def_adj = combined_def * 0.4
        pace_adjusted += def_adj
        factors['defensive_adj'] = round(def_adj, 1)

        # --- Mean reversion (combat OVER bias seen in NBA model) ---
        mean_reversion = -2.0
        pace_adjusted += mean_reversion
        factors['mean_reversion'] = mean_reversion

        predicted_total = round(pace_adjusted, 1)
        factors['predicted_total'] = predicted_total

        # --- Edge & pick ---
        edge = predicted_total - posted_total
        factors['edge'] = round(edge, 1)

        if edge > 0:
            pick = "OVER"
        elif edge < 0:
            pick = "UNDER"
        else:
            pick = "PUSH"

        edge_abs = abs(edge)
        if edge_abs >= 5:
            confidence = 0.78
            tier = "🔒 LOCK"
        elif edge_abs >= 3.5:
            confidence = 0.70
            tier = "🎯 STRONG"
        elif edge_abs >= 2:
            confidence = 0.62
            tier = "📊 VALUE"
        elif edge_abs >= 1:
            confidence = 0.55
            tier = "📈 LEAN"
        else:
            confidence = 0.50
            tier = "⚖️ COIN FLIP"

        return {
            'home_team': home,
            'away_team': away,
            'predicted_total': predicted_total,
            'posted_total': posted_total,
            'pick': pick,
            'edge': round(edge, 1),
            'confidence': confidence,
            'tier': tier,
            'factors': factors,
            'spread': spread,
        }

    def run_predictions(self, target_date: date = None) -> List[Dict]:
        """Run predictions for all games."""
        if target_date is None:
            target_date = date.today()

        games = self.fetch_todays_games(target_date)
        if not games:
            print(f"No NCAAB games with totals for {target_date}")
            return []

        predictions = []
        for g in games:
            pred = self.predict_total(
                g['home_team'], g['away_team'],
                g['posted_total'], g['spread']
            )
            pred['game_date'] = g['game_date']
            pred['commence_time'] = g.get('commence_time', '')
            predictions.append(pred)
            self._store_prediction(pred)

        predictions.sort(key=lambda x: abs(x['edge']), reverse=True)
        return predictions

    def _store_prediction(self, pred: Dict):
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO ncaab_totals_predictions
            (game_date, home_team, away_team, predicted_total, posted_total,
             pick, confidence, edge, factors)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (pred.get('game_date'), pred['home_team'], pred['away_team'],
             pred['predicted_total'], pred['posted_total'],
             pred['pick'], pred['confidence'], pred['edge'],
             json.dumps(pred['factors'])))
        conn.commit()
        conn.close()

    def score_results(self, target_date: date) -> Dict:
        """Score predictions against actual results from ESPN."""
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT home_team, away_team, predicted_total, posted_total, pick, edge
                     FROM ncaab_totals_predictions WHERE game_date = ?''',
                  (target_date.isoformat(),))
        preds = c.fetchall()
        conn.close()

        if not preds:
            return {'error': f'No predictions for {target_date}'}

        scores = self._fetch_actual_scores(target_date)
        if not scores:
            return {'error': 'Could not fetch actual scores'}

        results = []
        correct = 0
        total = 0

        for home, away, pred_total, posted, pick, edge in preds:
            key = f"{away}@{home}"
            actual = scores.get(key)
            if actual is None:
                # Try fuzzy match
                for k, v in scores.items():
                    if home.lower() in k.lower() or away.lower() in k.lower():
                        actual = v
                        break
            if actual is None:
                continue

            actual_total = actual['home_score'] + actual['away_score']
            actual_result = "OVER" if actual_total > posted else ("UNDER" if actual_total < posted else "PUSH")
            hit = (pick == actual_result) or actual_result == "PUSH"

            if actual_result != "PUSH":
                total += 1
                if pick == actual_result:
                    correct += 1

            # Update DB
            conn2 = sqlite3.connect(str(DB_PATH))
            c2 = conn2.cursor()
            c2.execute('''UPDATE ncaab_totals_predictions SET actual_total = ?, result = ?
                         WHERE game_date = ? AND home_team = ? AND away_team = ?''',
                       (actual_total, "HIT" if hit else "MISS",
                        target_date.isoformat(), home, away))
            conn2.commit()
            conn2.close()

            results.append({
                'matchup': f"{away} @ {home}",
                'pick': pick,
                'edge': edge,
                'posted': posted,
                'predicted': pred_total,
                'actual': actual_total,
                'result': "HIT" if hit else "MISS",
            })

        accuracy = correct / total if total > 0 else 0
        return {
            'date': target_date.isoformat(),
            'sport': 'NCAAB',
            'results': results,
            'correct': correct,
            'total': total,
            'accuracy': accuracy,
        }

    def _fetch_actual_scores(self, target_date: date) -> Dict:
        """Fetch actual NCAAB scores from ESPN."""
        try:
            dt_str = target_date.strftime('%Y%m%d')
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={dt_str}&limit=200"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            scores = {}
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

                home_name = home_data['team'].get('displayName', '')
                away_name = away_data['team'].get('displayName', '')
                home_score = int(home_data.get('score', 0))
                away_score = int(away_data.get('score', 0))

                key = f"{away_name}@{home_name}"
                scores[key] = {'home_score': home_score, 'away_score': away_score}

            return scores
        except Exception as e:
            logger.error(f"Error fetching scores: {e}")
            return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    engine = NCAABTotalsEngine()

    if '--score' in sys.argv:
        idx = sys.argv.index('--score')
        d = date.fromisoformat(sys.argv[idx+1]) if idx+1 < len(sys.argv) else date.today() - timedelta(days=1)
        res = engine.score_results(d)
        if 'error' in res:
            print(res['error'])
        else:
            print(f"\n{'='*70}")
            print(f"  NCAAB O/U RESULTS -- {res['date']}")
            print(f"  Record: {res['correct']}/{res['total']} ({res['accuracy']*100:.0f}%)")
            print(f"{'='*70}")
            for r in res['results']:
                icon = "V" if r['result'] == 'HIT' else "X"
                print(f"  {icon} {r['matchup']}: {r['pick']} {r['posted']} "
                      f"(pred {r['predicted']}, actual {r['actual']}, edge {r['edge']:+.1f})")
    else:
        target = date.today()
        if '--date' in sys.argv:
            idx = sys.argv.index('--date')
            if idx+1 < len(sys.argv):
                target = date.fromisoformat(sys.argv[idx+1])

        predictions = engine.run_predictions(target)
        if predictions:
            print(f"\n{'='*70}")
            print(f"  NCAAB OVER/UNDER PREDICTIONS -- {target}")
            print(f"{'='*70}")
            for p in predictions:
                arrow = "UP" if p['pick'] == "OVER" else "DN" if p['pick'] == "UNDER" else "--"
                print(f"\n  {p['away_team']} @ {p['home_team']}")
                print(f"    Posted: {p['posted_total']}  |  Predicted: {p['predicted_total']}")
                print(f"    Pick: {arrow} {p['pick']} {p['posted_total']}  |  Edge: {p['edge']:+.1f}")
                print(f"    {p['tier']}  ({p['confidence']*100:.0f}% confidence)")

            overs = sum(1 for p in predictions if p['pick'] == 'OVER')
            unders = sum(1 for p in predictions if p['pick'] == 'UNDER')
            avg_edge = sum(abs(p['edge']) for p in predictions) / len(predictions)
            print(f"\n  Summary: {overs} OVERs, {unders} UNDERs | Avg edge: {avg_edge:.1f}")

        out_path = Path(__file__).parent / f"ncaab_totals_picks_{target}.json"
        with open(out_path, 'w') as f:
            json.dump(predictions, f, indent=2, default=str)
        print(f"\n  Saved to {out_path}")
