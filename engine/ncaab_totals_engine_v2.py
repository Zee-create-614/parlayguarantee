"""
NCAAB Over/Under (Totals) Prediction Engine v2 for ParlayGuarantee
College basketball specific methodology with lower pace/scoring constants

Key differences from NBA model:
1. Lower average scoring (~140-150 vs ~225-235)
2. More variable pace between teams
3. Home court advantage more pronounced
4. Less efficient market (more opportunity for edges)
5. Tournament/rivalry game considerations
6. Different injury impact patterns

Usage:
  python ncaab_totals_engine_v2.py                    # Today's predictions
  python ncaab_totals_engine_v2.py --date 2026-02-21  # Specific date
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
import statistics

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "ncaab_totals_v2.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# NCAAB constants (different from NBA)
NCAAB_AVG_PPG = 70.5    # Much lower than NBA
NCAAB_AVG_PACE = 68.2   # Slower pace than NBA
NCAAB_HOME_ADV = 3.5    # Stronger home advantage than NBA


def init_db():
    """Initialize database for NCAAB predictions."""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ncaab_totals_predictions_v2 (
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
    c.execute('''CREATE TABLE IF NOT EXISTS ncaab_team_stats (
        team TEXT PRIMARY KEY,
        ppg REAL,
        papg REAL,
        pace REAL,
        off_eff REAL,
        def_eff REAL,
        home_ppg REAL,
        away_ppg REAL,
        conf_ppg REAL,
        adj_off REAL,
        adj_def REAL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()


class NCAABTotalsEngineV2:
    def __init__(self):
        init_db()
        self.team_stats = {}
        self.conferences = {}
        
    def fetch_ncaab_stats(self) -> Dict[str, Dict]:
        """Fetch NCAAB team stats from ESPN."""
        try:
            # ESPN NCAAB standings/stats
            url = "https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            stats = {}
            for group in data.get('children', []):
                conf_name = group.get('name', 'Unknown')
                
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    
                    # Clean team name
                    name = self._clean_team_name(name)
                    
                    s = {'conference': conf_name}
                    
                    # Parse stats
                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        
                        if sn == 'wins': s['wins'] = int(sv)
                        elif sn == 'losses': s['losses'] = int(sv)
                        elif sn == 'winPercent': s['win_pct'] = float(sv)
                        elif sn == 'avgPointsFor': s['ppg'] = float(sv)
                        elif sn == 'avgPointsAgainst': s['papg'] = float(sv)
                        elif sn == 'streak': 
                            s['streak'] = int(sv) if isinstance(sv, (int, float)) else 0
                        elif sn == 'pointDifferential': s['margin'] = float(sv)

                    # Calculate games played
                    gp = s.get('wins', 0) + s.get('losses', 0)
                    if gp == 0:
                        continue
                    s['games_played'] = gp
                    
                    # Defaults if missing
                    if 'ppg' not in s:
                        s['ppg'] = NCAAB_AVG_PPG
                    if 'papg' not in s:
                        s['papg'] = NCAAB_AVG_PPG

                    stats[name] = s

            logger.info(f"Fetched NCAAB stats for {len(stats)} teams")
            self.team_stats = stats
            return stats
            
        except Exception as e:
            logger.error(f"NCAAB stats fetch error: {e}")
            return {}

    def estimate_ncaab_pace(self) -> Dict[str, float]:
        """Estimate pace for NCAAB teams (no public API like NBA)."""
        pace_estimates = {}
        
        for team, stats in self.team_stats.items():
            ppg = stats.get('ppg', NCAAB_AVG_PPG)
            papg = stats.get('papg', NCAAB_AVG_PPG)
            
            # Estimate based on total points and efficiency
            total_scoring = ppg + papg
            
            # High scoring teams usually play faster pace
            pace_factor = total_scoring / (2 * NCAAB_AVG_PPG)
            
            # Apply some variance for college diversity
            if total_scoring > 150:  # High-scoring teams
                estimated_pace = NCAAB_AVG_PACE * 1.15
            elif total_scoring > 140:
                estimated_pace = NCAAB_AVG_PACE * 1.05  
            elif total_scoring < 130:  # Low-scoring defensive teams
                estimated_pace = NCAAB_AVG_PACE * 0.90
            else:
                estimated_pace = NCAAB_AVG_PACE
            
            pace_estimates[team] = round(estimated_pace, 1)
            
        return pace_estimates

    def get_conference_factors(self) -> Dict[str, float]:
        """Apply conference-specific scoring adjustments."""
        # Some conferences consistently play faster/slower
        conf_adjustments = {
            'Big 12': 1.08,      # Fast, high-scoring
            'Big Ten': 0.95,     # Slower, more defensive
            'ACC': 1.02,         # Slightly above average
            'SEC': 1.05,         # Good offense
            'Pac-12': 1.03,      # Balanced
            'Big East': 0.98,    # More defensive
        }
        
        team_conf_factors = {}
        for team, stats in self.team_stats.items():
            conf = stats.get('conference', 'Unknown')
            # Extract main conference name
            for conf_key in conf_adjustments:
                if conf_key in conf:
                    team_conf_factors[team] = conf_adjustments[conf_key]
                    break
            else:
                team_conf_factors[team] = 1.0  # Neutral
                
        return team_conf_factors

    def fetch_ncaab_games(self, target_date: date = None) -> List[Dict]:
        """Fetch NCAAB games with totals from Odds API."""
        if target_date is None:
            target_date = date.today()

        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'totals,spreads',
            'oddsFormat': 'american',
        }
        url = "https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds"
        
        try:
            resp = requests.get(url, params=params, timeout=30)
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"NCAAB Odds API requests remaining: {remaining}")
            
            if resp.status_code != 200:
                logger.error(f"NCAAB Odds API error: {resp.status_code}")
                return []

            games = []
            for g in resp.json():
                commence = g.get('commence_time', '')
                if commence:
                    from datetime import timezone
                    utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    est_offset = timedelta(hours=-5)
                    est_dt = utc_dt + est_offset
                    game_date = est_dt.date()
                else:
                    game_date = target_date

                # Only games on target date
                if game_date != target_date:
                    continue

                home = self._clean_team_name(g['home_team'])
                away = self._clean_team_name(g['away_team'])

                # Collect totals and spreads
                totals = []
                spreads_home = []
                for bookie in g.get('bookmakers', []):
                    for market in bookie.get('markets', []):
                        if market['key'] == 'totals':
                            for outcome in market['outcomes']:
                                if outcome['name'] == 'Over':
                                    totals.append(outcome.get('point', 0))
                        elif market['key'] == 'spreads':
                            for outcome in market['outcomes']:
                                if outcome['name'] == home:
                                    spreads_home.append(outcome.get('point', 0))

                if not totals:
                    continue

                posted_total = statistics.mean(totals)
                spread = statistics.mean(spreads_home) if spreads_home else 0

                games.append({
                    'home_team': home,
                    'away_team': away,
                    'posted_total': round(posted_total, 1),
                    'spread': round(spread, 1),
                    'commence_time': commence,
                    'game_date': game_date.isoformat(),
                })

            logger.info(f"Found {len(games)} NCAAB games with totals for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Error fetching NCAAB games: {e}")
            return []

    def predict_ncaab_total(self, home: str, away: str, posted_total: float,
                           spread: float = 0) -> Dict:
        """
        NCAAB-specific total prediction.
        
        Key differences from NBA:
        - Lower baseline scoring
        - Higher home court advantage  
        - More pace variance between teams
        - Conference style differences
        - Less market efficiency (more edges available)
        """
        h_stats = self.team_stats.get(home, {})
        a_stats = self.team_stats.get(away, {})

        # Defaults for missing teams
        h_ppg = h_stats.get('ppg', NCAAB_AVG_PPG)
        h_papg = h_stats.get('papg', NCAAB_AVG_PPG) 
        a_ppg = a_stats.get('ppg', NCAAB_AVG_PPG)
        a_papg = a_stats.get('papg', NCAAB_AVG_PPG)

        factors = {
            'home_team': home,
            'away_team': away,
            'posted_total': posted_total,
        }

        # === STEP 1: BASE PREDICTION ===
        # NCAAB efficiency calculation
        pace_estimates = self.estimate_ncaab_pace()
        h_pace = pace_estimates.get(home, NCAAB_AVG_PACE)
        a_pace = pace_estimates.get(away, NCAAB_AVG_PACE)
        game_pace = (h_pace + a_pace) / 2

        # Offensive/defensive efficiency (points per 100 possessions)
        h_off_eff = (h_ppg / h_pace) * 100
        h_def_eff = (h_papg / h_pace) * 100
        a_off_eff = (a_ppg / a_pace) * 100  
        a_def_eff = (a_papg / a_pace) * 100

        # Expected scoring
        possessions = game_pace
        home_expected = ((h_off_eff + a_def_eff) / 200) * possessions
        away_expected = ((a_off_eff + h_def_eff) / 200) * possessions
        
        base_total = home_expected + away_expected

        factors.update({
            'game_pace': round(game_pace, 1),
            'home_expected': round(home_expected, 1),
            'away_expected': round(away_expected, 1),
            'base_total': round(base_total, 1),
        })

        predicted_total = base_total

        # === STEP 2: HOME COURT ADVANTAGE ===
        # Stronger in college than NBA
        home_advantage = NCAAB_HOME_ADV
        predicted_total += home_advantage
        factors['home_advantage'] = home_advantage

        # === STEP 3: CONFERENCE STYLE ===
        conf_factors = self.get_conference_factors()
        h_conf_factor = conf_factors.get(home, 1.0)
        a_conf_factor = conf_factors.get(away, 1.0)
        conf_adjustment = ((h_conf_factor + a_conf_factor) / 2 - 1.0) * base_total * 0.05
        
        predicted_total += conf_adjustment
        factors['conference_adj'] = round(conf_adjustment, 1)

        # === STEP 4: RECENT FORM ===
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        
        # College teams are streakier
        streak_impact = (h_streak + a_streak) * 0.15
        streak_impact = max(-2.0, min(2.0, streak_impact))
        
        predicted_total += streak_impact
        factors['streak_impact'] = round(streak_impact, 1)

        # === STEP 5: SPREAD IMPACT ===
        spread_abs = abs(spread)
        if spread_abs >= 15:  # Big blowouts
            # In college, big spreads often mean pace slows in 2nd half
            blowout_adj = -2.0
        elif spread_abs >= 10:
            blowout_adj = -1.0
        elif spread_abs <= 3:  # Close games
            # Tend to be higher scoring, more possessions
            blowout_adj = 1.0
        else:
            blowout_adj = 0

        predicted_total += blowout_adj
        factors['blowout_adj'] = blowout_adj

        # === STEP 6: RIVALRY/TOURNAMENT GAMES ===
        # Check if this could be a big game (same conference)
        h_conf = h_stats.get('conference', '')
        a_conf = a_stats.get('conference', '')
        
        rivalry_adj = 0
        if h_conf == a_conf and h_conf:  # Conference game
            # Conference games tend to be more intense, defensive
            rivalry_adj = -0.5
        
        predicted_total += rivalry_adj
        factors['rivalry_adj'] = rivalry_adj

        # === STEP 7: MARKET EFFICIENCY ===
        # NCAAB market less efficient than NBA - allow bigger edges
        raw_edge = predicted_total - posted_total
        if abs(raw_edge) > 12:  # Very large disagreement
            # Pull back some, but not as much as NBA
            excess = abs(raw_edge) - 12
            pullback = excess * 0.4  # Less pullback than NBA
            if raw_edge > 0:
                predicted_total -= pullback
            else:
                predicted_total += pullback

        predicted_total = round(predicted_total, 1)
        factors['final_predicted'] = predicted_total

        # === DECISION MAKING ===
        edge = predicted_total - posted_total
        edge_abs = abs(edge)

        # NCAAB allows for bigger edges due to less efficient market
        MIN_EDGE = 2.0  # Slightly higher threshold than NBA
        
        if edge_abs < MIN_EDGE:
            pick = "PASS"
            confidence = 0.50
            tier = "⚖️ NO EDGE"
        else:
            pick = "OVER" if edge > 0 else "UNDER"
            
            if edge_abs >= 6:
                confidence = 0.78
                tier = "🔒 STRONG"
            elif edge_abs >= 4:
                confidence = 0.68
                tier = "📊 VALUE"  
            elif edge_abs >= 3:
                confidence = 0.60
                tier = "📈 LEAN"
            else:
                confidence = 0.55
                tier = "🤔 MILD"

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
        """Generate NCAAB predictions."""
        if target_date is None:
            target_date = date.today()

        logger.info(f"Running NCAAB predictions for {target_date}")

        # Load data
        self.fetch_ncaab_stats()
        games = self.fetch_ncaab_games(target_date)
        
        if not games:
            logger.warning(f"No NCAAB games found for {target_date}")
            return []

        predictions = []
        for g in games:
            pred = self.predict_ncaab_total(
                g['home_team'], g['away_team'],
                g['posted_total'], g['spread']
            )
            pred['game_date'] = g['game_date']
            pred['commence_time'] = g.get('commence_time', '')
            predictions.append(pred)

            # Store in database
            self._store_prediction(pred)

        # Filter actionable picks
        actionable = [p for p in predictions if p['pick'] != 'PASS']
        actionable.sort(key=lambda x: abs(x['edge']), reverse=True)
        
        logger.info(f"Generated {len(actionable)} actionable NCAAB predictions from {len(games)} games")
        return actionable

    def _store_prediction(self, pred: Dict):
        """Store prediction in database."""
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO ncaab_totals_predictions_v2
            (game_date, home_team, away_team, predicted_total, posted_total,
             pick, confidence, edge, factors)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (pred.get('game_date'), pred['home_team'], pred['away_team'],
             pred['predicted_total'], pred['posted_total'],
             pred['pick'], pred['confidence'], pred['edge'],
             json.dumps(pred['factors'])))
        conn.commit()
        conn.close()

    def _clean_team_name(self, name: str) -> str:
        """Clean and normalize NCAAB team names."""
        # Remove common suffixes that cause mismatches
        name = name.replace(' Wildcats', '').replace(' Tigers', '').replace(' Eagles', '')
        name = name.replace(' Cardinals', '').replace(' Bulldogs', '').replace(' Bears', '')
        
        # Handle some common variations
        mapping = {
            'North Carolina': 'UNC',
            'Duke': 'Duke',
            'Kentucky': 'Kentucky', 
            'Kansas': 'Kansas',
            'Michigan St': 'Michigan State',
            'UConn': 'Connecticut',
            'St. John\'s': 'St. John\'s',
        }
        return mapping.get(name, name)

    def display_predictions(self, predictions: List[Dict]):
        """Display NCAAB predictions."""
        if not predictions:
            print("No actionable NCAAB predictions.")
            return

        print(f"\n{'='*80}")
        print(f"  NCAAB OVER/UNDER PREDICTIONS V2 - {predictions[0].get('game_date', 'Today')}")
        print(f"{'='*80}")

        overs = unders = 0
        for p in predictions:
            if p['pick'] == 'OVER':
                overs += 1
            elif p['pick'] == 'UNDER':
                unders += 1

            home = p['home_team']
            away = p['away_team']
            pick = p['pick']
            edge = p['edge']
            tier = p['tier']
            posted = p['posted_total']
            predicted = p['predicted_total']
            factors = p['factors']

            arrow = "UP" if pick == "OVER" else "DOWN"
            
            print(f"\n  {away} @ {home}")
            print(f"    Posted: {posted}  |  Predicted: {predicted}  |  Edge: {edge:+.1f}")
            print(f"    {arrow} {pick} {posted}  —  {tier}")
            
            # Show key factors
            pace = factors.get('game_pace', 0)
            home_exp = factors.get('home_expected', 0)
            away_exp = factors.get('away_expected', 0)
            conf_adj = factors.get('conference_adj', 0)
            
            print(f"    Pace: {pace} | Expected: {home_exp}-{away_exp}")
            if conf_adj != 0:
                print(f"    Conference adj: {conf_adj:+.1f}")

        # Summary
        if predictions:
            avg_edge = statistics.mean(abs(p['edge']) for p in predictions)
            strong_plays = [p for p in predictions if '🔒' in p['tier']]

            print(f"\n{'='*80}")
            print(f"  SUMMARY: {len(predictions)} picks ({overs} OVER, {unders} UNDER)")
            print(f"  Average edge: {avg_edge:.1f} points")
            if strong_plays:
                print(f"  🔒 STRONG PLAYS: {len(strong_plays)}")
                for sp in strong_plays:
                    print(f"    {sp['pick']} {sp['posted_total']} ({sp['away_team']} @ {sp['home_team']})")
            print(f"{'='*80}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    engine = NCAABTotalsEngineV2()
    
    # Parse arguments
    target_date = date.today()
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target_date = date.fromisoformat(sys.argv[idx + 1])
    
    # Run predictions
    predictions = engine.run_predictions(target_date)
    engine.display_predictions(predictions)
    
    # Save results
    out_path = Path(__file__).parent / f"ncaab_totals_picks_v2_{target_date}.json"
    with open(out_path, 'w') as f:
        json.dump(predictions, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()