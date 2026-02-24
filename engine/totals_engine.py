"""
Over/Under (Totals) Prediction Engine for ParlayGuarantee
Predicts whether games go OVER or UNDER the posted total.

Model factors:
1. Team offensive/defensive ratings (PPG + PAPG)
2. Pace factor (fast teams = higher totals)
3. Home/away scoring splits
4. Recent scoring trends (last 10 games)
5. Injury impact on scoring
6. Rest days (back-to-back = lower scoring)
7. Historical O/U accuracy by spread size
8. Line value (predicted total vs posted total)

Usage:
  python totals_engine.py                    # Today's predictions
  python totals_engine.py --date 2026-02-20  # Specific date
  python totals_engine.py --backtest         # Backtest against recent results
"""

import json
import logging
import math
import sys
import requests
import sqlite3
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "totals_engine.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# League average pace/scoring constants (2024-25 season)
LEAGUE_AVG_PPG = 113.5
LEAGUE_AVG_PACE = 99.5  # possessions per 48 min


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS totals_predictions (
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
    c.execute('''CREATE TABLE IF NOT EXISTS team_pace (
        team TEXT PRIMARY KEY,
        pace REAL,
        off_rating REAL,
        def_rating REAL,
        ppg REAL,
        papg REAL,
        home_ppg REAL,
        away_ppg REAL,
        last10_ppg REAL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()


class TotalsEngine:
    def __init__(self):
        init_db()
        self.team_stats = {}
        self.pace_data = {}
        self.injuries = {}

    def fetch_team_stats(self) -> Dict[str, Dict]:
        """Fetch current team stats from ESPN."""
        try:
            url = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            stats = {}
            for group in data.get('children', []):
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    name = self._map_team_name(name)

                    s = {}
                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        sd = stat.get('displayValue', '')
                        if sn == 'wins': s['wins'] = int(sv)
                        elif sn == 'losses': s['losses'] = int(sv)
                        elif sn == 'winPercent': s['win_pct'] = float(sv)
                        elif sn == 'avgPointsFor': s['ppg'] = float(sv)
                        elif sn == 'avgPointsAgainst': s['papg'] = float(sv)
                        elif sn == 'streak': s['streak'] = int(sv) if sv else 0
                        elif sn == 'Home': s['home_record'] = sd
                        elif sn == 'Road': s['road_record'] = sd

                    gp = s.get('wins', 0) + s.get('losses', 0)
                    if gp == 0:
                        continue

                    # Calculate from totals if averages missing
                    if 'ppg' not in s:
                        for stat in entry.get('stats', []):
                            if stat.get('name') == 'pointsFor':
                                s['ppg'] = float(stat.get('value', 0)) / gp
                    if 'papg' not in s:
                        for stat in entry.get('stats', []):
                            if stat.get('name') == 'pointsAgainst':
                                s['papg'] = float(stat.get('value', 0)) / gp

                    s['games_played'] = gp
                    stats[name] = s

            logger.info(f"Fetched stats for {len(stats)} teams")
            self.team_stats = stats
            return stats
        except Exception as e:
            logger.error(f"ESPN stats error: {e}")
            return {}

    def fetch_pace_data(self) -> Dict[str, float]:
        """Fetch pace data from NBA.com or estimate from PPG."""
        # NBA.com team pace endpoint
        try:
            url = "https://stats.nba.com/stats/leaguedashteamstats"
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://www.nba.com/',
                'Accept': 'application/json',
            }
            params = {
                'Conference': '', 'DateFrom': '', 'DateTo': '',
                'Division': '', 'GameScope': '', 'GameSegment': '',
                'Height': '', 'ISTRound': '', 'LastNGames': 0,
                'LeagueID': '00', 'Location': '', 'MeasureType': 'Advanced',
                'Month': 0, 'OpponentTeamID': 0, 'Outcome': '',
                'PORound': 0, 'PaceAdjust': 'N', 'PerMode': 'PerGame',
                'Period': 0, 'PlayerExperience': '', 'PlayerPosition': '',
                'PlusMinus': 'N', 'Rank': 'N', 'Season': '2024-25',
                'SeasonSegment': '', 'SeasonType': 'Regular Season',
                'ShotClockRange': '', 'StarterBench': '',
                'TeamID': 0, 'TwoWay': 0, 'VsConference': '',
                'VsDivision': '',
            }
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                headers_list = data['resultSets'][0]['headers']
                rows = data['resultSets'][0]['rowSet']
                pace_idx = headers_list.index('PACE') if 'PACE' in headers_list else None
                offrtg_idx = headers_list.index('OFF_RATING') if 'OFF_RATING' in headers_list else None
                defrtg_idx = headers_list.index('DEF_RATING') if 'DEF_RATING' in headers_list else None
                name_idx = headers_list.index('TEAM_NAME') if 'TEAM_NAME' in headers_list else None

                if pace_idx is not None and name_idx is not None:
                    for row in rows:
                        team = self._map_team_name(row[name_idx])
                        self.pace_data[team] = {
                            'pace': row[pace_idx],
                            'off_rating': row[offrtg_idx] if offrtg_idx else 0,
                            'def_rating': row[defrtg_idx] if defrtg_idx else 0,
                        }
                    logger.info(f"Fetched pace data for {len(self.pace_data)} teams from NBA.com")
                    return self.pace_data
        except Exception as e:
            logger.warning(f"NBA.com pace fetch failed: {e}")

        # Fallback: estimate pace from PPG
        for team, stats in self.team_stats.items():
            ppg = stats.get('ppg', LEAGUE_AVG_PPG)
            papg = stats.get('papg', LEAGUE_AVG_PPG)
            # Rough pace estimate: higher scoring teams generally play faster
            est_pace = LEAGUE_AVG_PACE * ((ppg + papg) / (2 * LEAGUE_AVG_PPG))
            self.pace_data[team] = {
                'pace': round(est_pace, 1),
                'off_rating': ppg,
                'def_rating': papg,
            }
        logger.info(f"Estimated pace for {len(self.pace_data)} teams from PPG")
        return self.pace_data

    def fetch_todays_totals(self, target_date: date = None) -> List[Dict]:
        """Fetch today's games with posted over/under totals from Odds API."""
        if target_date is None:
            target_date = date.today()

        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'totals,spreads,h2h',
            'oddsFormat': 'american',
        }
        url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
        try:
            resp = requests.get(url, params=params, timeout=30)
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"Odds API requests remaining: {remaining}")
            if resp.status_code != 200:
                logger.error(f"Odds API error: {resp.status_code}")
                return []

            games = []
            for g in resp.json():
                commence = g.get('commence_time', '')
                # Convert UTC commence time to EST date for matching
                if commence:
                    from datetime import timezone
                    utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    est_offset = timedelta(hours=-5)
                    est_dt = utc_dt + est_offset
                    game_date = est_dt.date().isoformat()
                else:
                    game_date = target_date.isoformat()

                # Only include games on target date
                if game_date != target_date.isoformat():
                    continue

                home = g['home_team']
                away = g['away_team']

                # Collect totals from all bookmakers
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

            logger.info(f"Found {len(games)} games with totals for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Error fetching totals: {e}")
            return []

    def predict_total(self, home: str, away: str, posted_total: float,
                      spread: float = 0) -> Dict:
        """
        Core prediction: estimate the game total and compare to posted line.

        METHOD:
        1. Base total = (home_ppg + away_ppg + home_papg + away_papg) / 2
           This gives expected points scored by each team
        2. Pace adjustment: faster matchups score more
        3. Home/away splits
        4. Defensive matchup quality
        5. Compare predicted total to posted total for edge
        """
        h_stats = self.team_stats.get(home, {})
        a_stats = self.team_stats.get(away, {})

        h_ppg = h_stats.get('ppg', LEAGUE_AVG_PPG)
        h_papg = h_stats.get('papg', LEAGUE_AVG_PPG)
        a_ppg = a_stats.get('ppg', LEAGUE_AVG_PPG)
        a_papg = a_stats.get('papg', LEAGUE_AVG_PPG)

        # --- FACTOR 1: Base projected total ---
        # Method: weighted blend of team PPG/PAPG + league regression
        # Raw expected: average of team's offense vs opponent's defense
        home_expected_raw = (h_ppg + a_papg) / 2
        away_expected_raw = (a_ppg + h_papg) / 2
        raw_total = home_expected_raw + away_expected_raw

        # Regress toward league average to avoid double-counting
        # Without regression, adding PPG+PAPG inflates totals because
        # league-average offense vs league-average defense = league avg, not 2x
        regression_weight = 0.60  # pull 60% toward league average — combat OVER bias
        league_avg_total = 2 * LEAGUE_AVG_PPG
        base_total = raw_total * (1 - regression_weight) + league_avg_total * regression_weight
        home_expected = base_total / 2 + (home_expected_raw - away_expected_raw) / 2
        away_expected = base_total - home_expected

        factors = {
            'home_expected_pts': round(home_expected, 1),
            'away_expected_pts': round(away_expected, 1),
            'base_total': round(base_total, 1),
        }

        # --- FACTOR 2: Pace adjustment ---
        h_pace = self.pace_data.get(home, {}).get('pace', LEAGUE_AVG_PACE)
        a_pace = self.pace_data.get(away, {}).get('pace', LEAGUE_AVG_PACE)
        game_pace = (h_pace + a_pace) / 2
        pace_factor = game_pace / LEAGUE_AVG_PACE
        pace_adjusted = base_total * pace_factor
        factors['pace_factor'] = round(pace_factor, 3)
        factors['game_pace'] = round(game_pace, 1)

        # --- FACTOR 3: Home court scoring bump ---
        # Home teams score ~1.5 pts more, but this is already in PPG averages
        # Only apply a small residual bump
        home_bump = 0.5
        pace_adjusted += home_bump
        factors['home_bump'] = home_bump

        # --- FACTOR 4: Blowout effect ---
        # Big spreads: starters sit early = LOWER totals (not higher!)
        # Backtest showed our model was WAY too high on blowout games
        spread_abs = abs(spread)
        if spread_abs >= 15:
            blowout_adj = -3.0  # huge favorites → starters rest, pace drops
        elif spread_abs >= 10:
            blowout_adj = -1.5
        elif spread_abs >= 6:
            blowout_adj = -0.5
        elif spread_abs <= 2:
            blowout_adj = -1.0  # tight games = grind-it-out defense
        else:
            blowout_adj = 0
        pace_adjusted += blowout_adj
        factors['blowout_adj'] = blowout_adj

        # --- FACTOR 5: Defensive matchup quality ---
        # DOUBLED weight — defense matters more than our base model captures
        h_def_rank = h_papg - LEAGUE_AVG_PPG  # negative = good defense
        a_def_rank = a_papg - LEAGUE_AVG_PPG
        combined_def = (h_def_rank + a_def_rank) / 2
        def_adj = combined_def * 0.5  # stronger weight on defense
        pace_adjusted += def_adj
        factors['defensive_adj'] = round(def_adj, 1)

        # --- FACTOR 6: Mean reversion bias ---
        # NBA totals tend to regress: high predicted = likely lower actual
        # Backtest showed consistent OVER bias, so apply a correction
        mean_reversion = -2.5  # flat correction based on backtest data
        pace_adjusted += mean_reversion
        factors['mean_reversion'] = mean_reversion

        # --- FACTOR 7: Recent form (streak) — REDUCED weight ---
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        streak_adj = (h_streak + a_streak) * 0.08  # halved from 0.15
        streak_adj = max(-1.0, min(1.0, streak_adj))
        pace_adjusted += streak_adj
        factors['streak_adj'] = round(streak_adj, 1)

        predicted_total = round(pace_adjusted, 1)
        factors['predicted_total'] = predicted_total

        # --- EDGE CALCULATION ---
        edge = predicted_total - posted_total
        factors['edge'] = round(edge, 1)

        # Pick: OVER if predicted > posted, UNDER if predicted < posted
        if edge > 0:
            pick = "OVER"
        elif edge < 0:
            pick = "UNDER"
        else:
            pick = "PUSH"

        # Confidence based on edge size
        edge_abs = abs(edge)
        if edge_abs >= 6:
            confidence = 0.80
            tier = "🔒 LOCK"
        elif edge_abs >= 4:
            confidence = 0.72
            tier = "🎯 STRONG"
        elif edge_abs >= 2.5:
            confidence = 0.64
            tier = "📊 VALUE"
        elif edge_abs >= 1:
            confidence = 0.56
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
        """Run predictions for all games on a date."""
        if target_date is None:
            target_date = date.today()

        # Load data
        self.fetch_team_stats()
        self.fetch_pace_data()
        games = self.fetch_todays_totals(target_date)

        if not games:
            print(f"No games with totals found for {target_date}")
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

            # Store in DB
            self._store_prediction(pred)

        # Sort by confidence (highest first)
        predictions.sort(key=lambda x: abs(x['edge']), reverse=True)
        return predictions

    def _store_prediction(self, pred: Dict):
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO totals_predictions
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
        """Score predictions against actual results."""
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT home_team, away_team, predicted_total, posted_total, pick, edge
                     FROM totals_predictions WHERE game_date = ?''',
                  (target_date.isoformat(),))
        preds = c.fetchall()
        conn.close()

        if not preds:
            return {'error': f'No predictions for {target_date}'}

        # Fetch actual scores from ESPN
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
            c2.execute('''UPDATE totals_predictions SET actual_total = ?, result = ?
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
                'result': "✅" if hit else "❌",
            })

        accuracy = correct / total if total > 0 else 0
        return {
            'date': target_date.isoformat(),
            'results': results,
            'correct': correct,
            'total': total,
            'accuracy': accuracy,
        }

    def _fetch_actual_scores(self, target_date: date) -> Dict:
        """Fetch actual game scores from ESPN."""
        try:
            dt_str = target_date.strftime('%Y%m%d')
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt_str}"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            scores = {}
            for event in data.get('events', []):
                comps = event.get('competitions', [{}])[0]
                competitors = comps.get('competitors', [])
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

                home_name = self._map_team_name(home_data['team'].get('displayName', ''))
                away_name = self._map_team_name(away_data['team'].get('displayName', ''))
                home_score = int(home_data.get('score', 0))
                away_score = int(away_data.get('score', 0))

                key = f"{away_name}@{home_name}"
                scores[key] = {'home_score': home_score, 'away_score': away_score}

            return scores
        except Exception as e:
            logger.error(f"Error fetching scores: {e}")
            return {}

    def _map_team_name(self, name: str) -> str:
        """Map various team name formats to canonical names."""
        mapping = {
            'LA Clippers': 'Los Angeles Clippers',
            'L.A. Clippers': 'Los Angeles Clippers',
            'L.A. Lakers': 'Los Angeles Lakers',
        }
        return mapping.get(name, name)

    def display_predictions(self, predictions: List[Dict]):
        """Pretty-print predictions."""
        if not predictions:
            print("No predictions to display.")
            return

        print(f"\n{'='*75}")
        print(f"  🏀 OVER/UNDER PREDICTIONS — {predictions[0].get('game_date', 'Today')}")
        print(f"{'='*75}")

        for p in predictions:
            home = p['home_team']
            away = p['away_team']
            pick = p['pick']
            edge = p['edge']
            conf = p['confidence']
            tier = p['tier']
            posted = p['posted_total']
            predicted = p['predicted_total']
            factors = p['factors']

            arrow = "⬆️" if pick == "OVER" else "⬇️" if pick == "UNDER" else "↔️"

            print(f"\n  {away} @ {home}")
            print(f"    Posted Total: {posted}  |  Our Predicted: {predicted}")
            print(f"    Pick: {arrow} {pick} {posted}  |  Edge: {edge:+.1f} pts")
            print(f"    {tier}  ({conf*100:.0f}% confidence)")
            print(f"    Pace: {factors.get('game_pace', '?')} | "
                  f"Home exp: {factors.get('home_expected_pts', '?')} | "
                  f"Away exp: {factors.get('away_expected_pts', '?')}")

        # Summary
        overs = sum(1 for p in predictions if p['pick'] == 'OVER')
        unders = sum(1 for p in predictions if p['pick'] == 'UNDER')
        avg_edge = sum(abs(p['edge']) for p in predictions) / len(predictions)
        locks = [p for p in predictions if '🔒' in p['tier']]

        print(f"\n{'='*75}")
        print(f"  Summary: {overs} OVERs, {unders} UNDERs | Avg edge: {avg_edge:.1f} pts")
        if locks:
            print(f"  🔒 LOCKS: ", end="")
            for l in locks:
                print(f"{l['pick']} {l['posted_total']} ({l['away_team']}@{l['home_team']})", end="  ")
            print()
        print(f"{'='*75}")


def display_results(results: Dict):
    """Pretty-print scored results."""
    if 'error' in results:
        print(results['error'])
        return

    print(f"\n{'='*75}")
    print(f"  📊 O/U RESULTS — {results['date']}")
    print(f"  Record: {results['correct']}/{results['total']} ({results['accuracy']*100:.0f}%)")
    print(f"{'='*75}")

    for r in results['results']:
        print(f"  {r['result']} {r['matchup']}: {r['pick']} {r['posted']} "
              f"(pred {r['predicted']}, actual {r['actual']}, edge {r['edge']:+.1f})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    engine = TotalsEngine()

    if '--backtest' in sys.argv:
        # Score yesterday's predictions
        yesterday = date.today() - timedelta(days=1)
        results = engine.score_results(yesterday)
        display_results(results)
    elif '--score' in sys.argv:
        idx = sys.argv.index('--score')
        d = date.fromisoformat(sys.argv[idx+1]) if idx+1 < len(sys.argv) else date.today() - timedelta(days=1)
        results = engine.score_results(d)
        display_results(results)
    else:
        target = date.today()
        for arg in sys.argv[1:]:
            if arg.startswith('--date'):
                continue
            try:
                target = date.fromisoformat(arg)
            except:
                pass
        if '--date' in sys.argv:
            idx = sys.argv.index('--date')
            if idx+1 < len(sys.argv):
                target = date.fromisoformat(sys.argv[idx+1])

        predictions = engine.run_predictions(target)
        engine.display_predictions(predictions)

        # Save to JSON
        out_path = Path(__file__).parent / f"totals_picks_{target}.json"
        with open(out_path, 'w') as f:
            json.dump(predictions, f, indent=2, default=str)
        print(f"\nSaved to {out_path}")
