"""
MLB Over/Under (Totals) Prediction Engine for ParlayGuarantee
Predicts whether games go OVER or UNDER the posted total.

Model factors:
1. Team runs scored / runs allowed averages
2. Starting pitcher ERA matchup
3. Park factor (Coors vs Oracle Park = huge diff)
4. Bullpen quality
5. Weather (wind, temperature for outdoor parks)
6. Day/night splits
7. Home/away scoring splits
8. Recent scoring trends (L10)
9. Pythagorean expected runs
10. Line value (predicted total vs posted total)
"""

import sys
import json
import logging
import sqlite3
import math
import os
import requests
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mlb_data_fetcher import (
    MLBDataFetcher, PARK_FACTORS, OUTDOOR_STADIUMS,
    ODDS_API_KEY, ODDS_API_BASE, _safe_float,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('mlb_totals_engine.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "mlb_totals_engine.db"

# League averages
LEAGUE_AVG_RPG = 4.4  # runs per game per team (2024 baseline)
LEAGUE_AVG_TOTAL = 8.8


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
    conn.commit()
    conn.close()


class MLBTotalsEngine:
    """MLB over/under prediction engine."""

    def __init__(self):
        init_db()
        self.fetcher = MLBDataFetcher()
        self.team_stats: Dict[str, Dict] = {}

    def generate_picks(self, target_date=None) -> List[Dict]:
        """Generate O/U picks for a date."""
        target = target_date or date.today()
        if isinstance(target, str):
            target = date.fromisoformat(target)
        logger.info(f"MLB Totals Engine: generating picks for {target}")

        # Fetch team stats
        self.team_stats = self.fetcher.fetch_team_stats()

        # Fetch games with totals from Odds API
        games = self._fetch_games_with_totals(target)
        if not games:
            logger.info("No MLB games with totals found")
            return []

        predictions = []
        for game in games:
            try:
                pred = self.predict_total(
                    game['home_team'], game['away_team'],
                    game['posted_total'],
                    game.get('spread', 0),
                    game.get('venue', ''),
                )
                if pred:
                    pred['game_date'] = target.isoformat()
                    predictions.append(pred)
                    self._store_prediction(pred)
            except Exception as e:
                logger.error(f"Error predicting total for {game['away_team']} @ {game['home_team']}: {e}")

        predictions.sort(key=lambda x: abs(x.get('edge', 0)), reverse=True)
        logger.info(f"Generated {len(predictions)} totals predictions")
        return predictions

    def predict_total(self, home: str, away: str, posted_total: float,
                      spread: float = 0, venue: str = '') -> Optional[Dict]:
        """Core prediction: estimate game total and compare to posted line."""
        h_stats = self._get_stats(home)
        a_stats = self._get_stats(away)

        h_rpg = h_stats.get('runs_scored', LEAGUE_AVG_RPG)
        h_rapg = h_stats.get('runs_allowed', LEAGUE_AVG_RPG)
        a_rpg = a_stats.get('runs_scored', LEAGUE_AVG_RPG)
        a_rapg = a_stats.get('runs_allowed', LEAGUE_AVG_RPG)

        factors = {}

        # ── Factor 1: Base projected total ──
        # Home expected = avg(home_offense, away_defense_allowed)
        home_expected = (h_rpg + a_rapg) / 2
        away_expected = (a_rpg + h_rapg) / 2
        raw_total = home_expected + away_expected

        # Regress toward league average (avoid double-counting)
        regression = 0.40
        base_total = raw_total * (1 - regression) + LEAGUE_AVG_TOTAL * regression
        factors['base_total'] = round(base_total, 1)
        factors['home_expected'] = round(home_expected, 1)
        factors['away_expected'] = round(away_expected, 1)

        # ── Factor 2: Starting pitcher ERA adjustment ──
        h_era = h_stats.get('era', 4.10)
        a_era = a_stats.get('era', 4.10)
        # Lower ERA pitchers suppress runs
        era_adj = ((h_era - 4.10) + (a_era - 4.10)) * 0.15
        base_total += era_adj
        factors['era_adj'] = round(era_adj, 2)

        # ── Factor 3: Park factor ──
        pf = MLBDataFetcher.get_park_factor(venue) if venue else 1.0
        park_adj = base_total * (pf - 1.0)
        base_total += park_adj
        factors['park_factor'] = pf
        factors['park_adj'] = round(park_adj, 2)

        # ── Factor 4: Bullpen quality ──
        # Proxy: team ERA vs league avg (better bullpen = fewer late runs)
        bullpen_adj = ((h_era - 4.10) + (a_era - 4.10)) * 0.08
        base_total += bullpen_adj
        factors['bullpen_adj'] = round(bullpen_adj, 2)

        # ── Factor 5: Weather placeholder ──
        # Wind blowing out + warm = more runs; cold/wind in = fewer
        factors['weather_adj'] = 0  # Would need weather API integration

        # ── Factor 6: Day/Night ──
        factors['day_night_adj'] = 0  # Day games slightly lower scoring historically

        # ── Factor 7: Home scoring bump ──
        home_bump = 0.15  # MLB home teams score slightly more
        base_total += home_bump
        factors['home_bump'] = home_bump

        # ── Factor 8: Recent form (L10 scoring) ──
        # Proxy: if teams are hot/cold
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        streak_adj = (h_streak + a_streak) * 0.03
        streak_adj = max(-0.5, min(0.5, streak_adj))
        base_total += streak_adj
        factors['streak_adj'] = round(streak_adj, 2)

        # ── Factor 9: Blowout effect ──
        spread_abs = abs(spread) if spread else 0
        if spread_abs >= 2.5:
            blowout_adj = -0.3  # big favorites may coast
        elif spread_abs <= 0.5:
            blowout_adj = -0.2  # tight games = more strategic pitching
        else:
            blowout_adj = 0
        base_total += blowout_adj
        factors['blowout_adj'] = blowout_adj

        # ── Factor 10: Mean reversion ──
        mean_reversion = -0.3  # slight correction
        base_total += mean_reversion
        factors['mean_reversion'] = mean_reversion

        predicted_total = round(base_total, 1)
        factors['predicted_total'] = predicted_total

        # ─── Edge & Pick ────────────────────────────────────────
        edge = predicted_total - posted_total
        factors['edge'] = round(edge, 1)

        if edge > 0.3:
            pick = "OVER"
        elif edge < -0.3:
            pick = "UNDER"
        else:
            pick = "PUSH"

        edge_abs = abs(edge)
        if edge_abs >= 2.0:
            confidence = 0.78
            tier = "LOCK"
        elif edge_abs >= 1.5:
            confidence = 0.70
            tier = "STRONG"
        elif edge_abs >= 1.0:
            confidence = 0.62
            tier = "VALUE"
        elif edge_abs >= 0.5:
            confidence = 0.55
            tier = "LEAN"
        else:
            confidence = 0.50
            tier = "SKIP"

        return {
            'home_team': home,
            'away_team': away,
            'predicted_total': predicted_total,
            'posted_total': posted_total,
            'pick': pick,
            'confidence': round(confidence, 4),
            'edge': round(edge, 1),
            'tier': tier,
            'factors': factors,
            'pick_type': tier,
            'over_under_pick': f"{pick} {posted_total}" if pick != "PUSH" else None,
        }

    # ─── Helpers ────────────────────────────────────────────────

    def _get_stats(self, team_name: str) -> Dict:
        if team_name in self.team_stats:
            return self.team_stats[team_name]
        for name, stats in self.team_stats.items():
            if team_name.lower() in name.lower() or name.lower() in team_name.lower():
                return stats
        return {
            'runs_scored': LEAGUE_AVG_RPG, 'runs_allowed': LEAGUE_AVG_RPG,
            'era': 4.10, 'whip': 1.28, 'streak': 0,
        }

    def _fetch_games_with_totals(self, target_date: date) -> List[Dict]:
        """Fetch games with posted totals from Odds API."""
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'totals,spreads,h2h',
            'oddsFormat': 'american',
        }
        url = f"{ODDS_API_BASE}/sports/baseball_mlb/odds"
        try:
            resp = requests.get(url, params=params, timeout=30)
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"Odds API requests remaining: {remaining}")
            if resp.status_code != 200:
                logger.error(f"Odds API error: {resp.status_code}")
                return []

            games = []
            target_str = target_date.isoformat()

            for g in resp.json():
                commence = g.get('commence_time', '')
                if commence:
                    try:
                        utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                        est_dt = utc_dt - timedelta(hours=5)
                        game_date = est_dt.date().isoformat()
                    except Exception:
                        game_date = commence[:10]
                else:
                    game_date = target_str

                if game_date != target_str:
                    continue

                home = g['home_team']
                away = g['away_team']

                totals = []
                spreads = []
                for bookie in g.get('bookmakers', []):
                    for mkt in bookie.get('markets', []):
                        if mkt['key'] == 'totals':
                            for o in mkt['outcomes']:
                                if o['name'] == 'Over':
                                    totals.append(o.get('point', 0))
                        elif mkt['key'] == 'spreads':
                            for o in mkt['outcomes']:
                                if o['name'] == home:
                                    spreads.append(o.get('point', 0))

                if not totals:
                    continue

                posted_total = sum(totals) / len(totals)
                spread = sum(spreads) / len(spreads) if spreads else 0

                games.append({
                    'home_team': home,
                    'away_team': away,
                    'posted_total': round(posted_total, 1),
                    'spread': round(spread, 1),
                    'commence_time': commence,
                    'game_date': game_date,
                })

            logger.info(f"Found {len(games)} MLB games with totals for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Error fetching totals: {e}")
            return []

    def _store_prediction(self, pred: Dict):
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""
                INSERT OR REPLACE INTO totals_predictions
                (game_date, home_team, away_team, predicted_total, posted_total,
                 pick, confidence, edge, factors)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                pred.get('game_date', ''),
                pred['home_team'], pred['away_team'],
                pred['predicted_total'], pred['posted_total'],
                pred['pick'], pred['confidence'], pred['edge'],
                json.dumps(pred['factors']),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store prediction: {e}")


# ─── CLI ────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='MLB Totals Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    args = parser.parse_args()

    engine = MLBTotalsEngine()
    target = date.fromisoformat(args.date) if args.date else None
    picks = engine.generate_picks(target)

    print(f"\n{'='*60}")
    print(f"MLB TOTALS PICKS \u2014 {target or date.today()}")
    print(f"{'='*60}")

    if not picks:
        print("No games with totals found.")
    else:
        for p in picks:
            emoji = {'LOCK': '\U0001f512', 'STRONG': '\U0001f3af', 'VALUE': '\U0001f4ca', 'LEAN': '\U0001f4c8', 'SKIP': '\u26a0\ufe0f'}.get(p['tier'], '')
            print(f"\n{emoji} {p['away_team']} @ {p['home_team']}")
            print(f"   Posted: {p['posted_total']}  |  Predicted: {p['predicted_total']}")
            print(f"   Pick: {p['pick']} ({p['confidence']:.1%})  |  Edge: {p['edge']:+.1f}")
            print(f"   Tier: {p['tier']}")
