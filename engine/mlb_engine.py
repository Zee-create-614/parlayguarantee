"""
ParlayGuarantee MLB Engine — 27-factor Baseball Prediction Model

Factors:
 1. Starting pitcher ERA         2. Starting pitcher WHIP
 3. Starting pitcher K/9         4. Pitcher recent form
 5. Bullpen ERA                  6. Bullpen WHIP
 7. Team batting average         8. Team OBP
 9. Team SLG                    10. Runs scored per game
11. Runs allowed per game       12. Home/away splits
13. Last 10 record              14. Win percentage
15. Pitcher handedness matchup  16. Park factor
17. Day/night splits            18. Rest days
19. Travel distance             20. Divisional rivalry adj
21. Lineup vs LHP/RHP           22. Stolen base differential
23. Defensive efficiency        24. Implied probability (odds)
25. Spread/line value           26. Streak momentum
27. Pythagorean expectation
"""

import sys
import json
import logging
import sqlite3
import math
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mlb_data_fetcher import MLBDataFetcher, PARK_FACTORS, TEAM_LOCATIONS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('mlb_engine.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'mlb_engine.db')

# ─── Factor Weights (27 factors, sum ~1.0) ─────────────────────

DEFAULT_WEIGHTS = {
    # Pitching (30%)
    'sp_era':               0.07,
    'sp_whip':              0.06,
    'sp_k9':                0.04,
    'sp_recent':            0.04,
    'bullpen_era':          0.05,
    'bullpen_whip':         0.04,

    # Batting (20%)
    'batting_avg':          0.04,
    'obp':                  0.05,
    'slg':                  0.04,
    'runs_scored':          0.04,
    'runs_allowed':         0.03,

    # Splits & form (15%)
    'home_away':            0.05,
    'last10':               0.04,
    'win_pct':              0.03,
    'streak':               0.03,

    # Matchup (15%)
    'pitcher_hand':         0.03,
    'lineup_vs_hand':       0.03,
    'park_factor':          0.03,
    'day_night':            0.02,
    'divisional':           0.02,
    'stolen_bases':         0.01,
    'defense':              0.01,

    # Situational (10%)
    'rest_days':            0.02,
    'travel':               0.02,
    'pythagorean':          0.04,
    'implied_prob':         0.02,

    # Market (5%)
    'line_value':           0.03,
    'spread_signal':        0.02,
}

# League averages (2024 season baseline)
LEAGUE_AVG = {
    'era': 4.10, 'whip': 1.28, 'k9': 8.5,
    'batting_avg': 0.248, 'obp': 0.312, 'slg': 0.400,
    'runs_per_game': 4.4,
}


class MLBEngine:
    """27-factor MLB prediction engine. Output matches ParlayGuarantee standard format."""

    def __init__(self):
        self.fetcher = MLBDataFetcher()
        self.weights = dict(DEFAULT_WEIGHTS)
        self.team_stats: Dict[str, Dict] = {}
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                game_id TEXT PRIMARY KEY,
                game_date TEXT,
                home_team TEXT, away_team TEXT,
                predicted_winner TEXT, confidence REAL,
                spread_pick TEXT, spread_confidence REAL,
                ou_pick TEXT, total REAL,
                factors_json TEXT,
                actual_winner TEXT, correct INT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS weight_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, weights_json TEXT,
                accuracy REAL, sample_size INT
            )
        """)
        conn.commit()
        conn.close()

    # ─── Main Entry Point ───────────────────────────────────────

    def generate_picks(self, target_date=None) -> List[Dict]:
        """Generate picks for a date. Returns standard format list."""
        target = target_date or date.today()
        if isinstance(target, str):
            target = date.fromisoformat(target)
        logger.info(f"MLB Engine: generating picks for {target}")

        # 1. Fetch team stats
        self.team_stats = self.fetcher.fetch_team_stats()
        if self.team_stats:
            self.fetcher.save_team_stats(self.team_stats)

        # 2. Fetch games from Odds API
        games = self.fetcher.fetch_games_from_odds(target)
        if not games:
            # Fallback: check ESPN scoreboard
            espn_games = self.fetcher.fetch_espn_scoreboard(target)
            if not espn_games:
                logger.info("No MLB games found for this date")
                return []
            # Convert ESPN format to our game format
            for eg in espn_games:
                games.append({
                    'game_id': eg['game_id'],
                    'game_date': eg['game_date'],
                    'game_time': '',
                    'home_team': eg['home_team'],
                    'away_team': eg['away_team'],
                    'home_odds': None, 'away_odds': None,
                    'home_implied_prob': 0.5, 'away_implied_prob': 0.5,
                    'spread': None, 'total': None,
                    'venue': eg.get('venue', ''),
                })

        logger.info(f"Found {len(games)} MLB games")

        # 3. Analyze each game
        predictions = []
        for game in games:
            try:
                pred = self._analyze_game(game)
                if pred:
                    predictions.append(pred)
                    self._store_prediction(pred)
            except Exception as e:
                logger.error(f"Error analyzing {game.get('away_team','')} @ {game.get('home_team','')}: {e}")

        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        logger.info(f"Generated {len(predictions)} MLB predictions")
        return predictions

    # ─── Core Analysis ──────────────────────────────────────────

    def _analyze_game(self, game: Dict) -> Optional[Dict]:
        """Run 27-factor analysis on a single game."""
        home = game['home_team']
        away = game['away_team']

        h_stats = self._get_team_stats(home)
        a_stats = self._get_team_stats(away)

        factors = {}
        home_score = 0.0
        away_score = 0.0

        # ── Factor 1: Starting Pitcher ERA ──
        h_sp_era = h_stats.get('era', LEAGUE_AVG['era'])
        a_sp_era = a_stats.get('era', LEAGUE_AVG['era'])
        # Lower ERA = better; flip so positive = home advantage
        era_diff = (a_sp_era - h_sp_era) / (2 * LEAGUE_AVG['era'])
        era_diff = max(-1, min(1, era_diff))
        factors['sp_era'] = era_diff
        home_score += max(0, era_diff) * self.weights['sp_era']
        away_score += max(0, -era_diff) * self.weights['sp_era']

        # ── Factor 2: Starting Pitcher WHIP ──
        h_sp_whip = h_stats.get('whip', LEAGUE_AVG['whip'])
        a_sp_whip = a_stats.get('whip', LEAGUE_AVG['whip'])
        whip_diff = (a_sp_whip - h_sp_whip) / (2 * LEAGUE_AVG['whip'])
        whip_diff = max(-1, min(1, whip_diff))
        factors['sp_whip'] = whip_diff
        home_score += max(0, whip_diff) * self.weights['sp_whip']
        away_score += max(0, -whip_diff) * self.weights['sp_whip']

        # ── Factor 3: K/9 ──
        h_k9 = h_stats.get('k9', LEAGUE_AVG['k9'])
        a_k9 = a_stats.get('k9', LEAGUE_AVG['k9'])
        k9_diff = (h_k9 - a_k9) / (2 * LEAGUE_AVG['k9'])
        factors['sp_k9'] = k9_diff
        home_score += max(0, k9_diff) * self.weights['sp_k9']
        away_score += max(0, -k9_diff) * self.weights['sp_k9']

        # ── Factor 4: Pitcher Recent Form (proxy: team L10) ──
        h_l10w = h_stats.get('l10_wins', 5)
        a_l10w = a_stats.get('l10_wins', 5)
        recent_diff = (h_l10w - a_l10w) / 10
        factors['sp_recent'] = recent_diff
        home_score += max(0, recent_diff) * self.weights['sp_recent']
        away_score += max(0, -recent_diff) * self.weights['sp_recent']

        # ── Factor 5-6: Bullpen ERA/WHIP (proxy: team-level for now) ──
        # Use team ERA as proxy; bullpen-specific data TBD
        bp_era_diff = era_diff * 0.7  # discount since it's team-level
        factors['bullpen_era'] = bp_era_diff
        home_score += max(0, bp_era_diff) * self.weights['bullpen_era']
        away_score += max(0, -bp_era_diff) * self.weights['bullpen_era']

        bp_whip_diff = whip_diff * 0.7
        factors['bullpen_whip'] = bp_whip_diff
        home_score += max(0, bp_whip_diff) * self.weights['bullpen_whip']
        away_score += max(0, -bp_whip_diff) * self.weights['bullpen_whip']

        # ── Factor 7: Batting Average ──
        h_ba = h_stats.get('batting_avg', LEAGUE_AVG['batting_avg'])
        a_ba = a_stats.get('batting_avg', LEAGUE_AVG['batting_avg'])
        ba_diff = (h_ba - a_ba) / 0.050  # normalize by ~2 std dev
        factors['batting_avg'] = ba_diff
        home_score += max(0, ba_diff) * self.weights['batting_avg']
        away_score += max(0, -ba_diff) * self.weights['batting_avg']

        # ── Factor 8: OBP ──
        h_obp = h_stats.get('obp', LEAGUE_AVG['obp'])
        a_obp = a_stats.get('obp', LEAGUE_AVG['obp'])
        obp_diff = (h_obp - a_obp) / 0.050
        factors['obp'] = obp_diff
        home_score += max(0, obp_diff) * self.weights['obp']
        away_score += max(0, -obp_diff) * self.weights['obp']

        # ── Factor 9: SLG ──
        h_slg = h_stats.get('slg', LEAGUE_AVG['slg'])
        a_slg = a_stats.get('slg', LEAGUE_AVG['slg'])
        slg_diff = (h_slg - a_slg) / 0.080
        factors['slg'] = slg_diff
        home_score += max(0, slg_diff) * self.weights['slg']
        away_score += max(0, -slg_diff) * self.weights['slg']

        # ── Factor 10: Runs Scored ──
        h_rs = h_stats.get('runs_scored', LEAGUE_AVG['runs_per_game'])
        a_rs = a_stats.get('runs_scored', LEAGUE_AVG['runs_per_game'])
        rs_diff = (h_rs - a_rs) / (2 * LEAGUE_AVG['runs_per_game'])
        factors['runs_scored'] = rs_diff
        home_score += max(0, rs_diff) * self.weights['runs_scored']
        away_score += max(0, -rs_diff) * self.weights['runs_scored']

        # ── Factor 11: Runs Allowed ──
        h_ra = h_stats.get('runs_allowed', LEAGUE_AVG['runs_per_game'])
        a_ra = a_stats.get('runs_allowed', LEAGUE_AVG['runs_per_game'])
        ra_diff = (a_ra - h_ra) / (2 * LEAGUE_AVG['runs_per_game'])  # lower = better
        factors['runs_allowed'] = ra_diff
        home_score += max(0, ra_diff) * self.weights['runs_allowed']
        away_score += max(0, -ra_diff) * self.weights['runs_allowed']

        # ── Factor 12: Home/Away Splits ──
        h_home_wp = self._home_win_pct(h_stats)
        a_away_wp = self._away_win_pct(a_stats)
        split_diff = h_home_wp - (1 - a_away_wp)  # home advantage vs away weakness
        factors['home_away'] = split_diff
        home_score += max(0, split_diff) * self.weights['home_away']
        away_score += max(0, -split_diff) * self.weights['home_away']

        # ── Factor 13: Last 10 Record ──
        l10_diff = (h_l10w - a_l10w) / 10
        factors['last10'] = l10_diff
        home_score += max(0, l10_diff) * self.weights['last10']
        away_score += max(0, -l10_diff) * self.weights['last10']

        # ── Factor 14: Overall Win Percentage ──
        h_wp = h_stats.get('win_pct', 0.5)
        a_wp = a_stats.get('win_pct', 0.5)
        wp_diff = h_wp - a_wp
        factors['win_pct'] = wp_diff
        home_score += max(0, wp_diff) * self.weights['win_pct']
        away_score += max(0, -wp_diff) * self.weights['win_pct']

        # ── Factor 15: Pitcher Handedness ──
        # Placeholder: neutral without specific pitcher data
        factors['pitcher_hand'] = 0
        # Will activate when pitcher-specific data is available

        # ── Factor 16: Park Factor ──
        venue = game.get('venue', '')
        pf = MLBDataFetcher.get_park_factor(venue)
        # Park factor benefits the home team (they selected for it)
        pf_edge = (pf - 1.0) * 0.5  # slight home edge from park
        factors['park_factor'] = pf_edge
        home_score += max(0, pf_edge) * self.weights['park_factor']
        away_score += max(0, -pf_edge) * self.weights['park_factor']

        # ── Factor 17: Day/Night ──
        factors['day_night'] = 0  # neutral without game time analysis

        # ── Factor 18: Rest Days ──
        factors['rest_days'] = 0  # neutral without schedule data

        # ── Factor 19: Travel Distance ──
        dist = MLBDataFetcher.calculate_travel_distance(away, home)
        travel_penalty = 0
        if dist > 2000:
            travel_penalty = -0.03  # coast-to-coast
        elif dist > 1000:
            travel_penalty = -0.015
        factors['travel'] = travel_penalty
        away_score += abs(travel_penalty) * self.weights['travel']  # away team penalized

        # ── Factor 20: Divisional Rivalry ──
        is_div = MLBDataFetcher.is_division_rival(home, away)
        div_adj = 0.01 if is_div else 0  # divisional games are tighter
        factors['divisional'] = div_adj

        # ── Factor 21: Lineup vs LHP/RHP ──
        factors['lineup_vs_hand'] = 0  # placeholder

        # ── Factor 22: Stolen Base Differential ──
        factors['stolen_bases'] = 0  # placeholder

        # ── Factor 23: Defensive Efficiency ──
        factors['defense'] = ra_diff * 0.3  # proxy from runs allowed

        # ── Factor 24: Implied Probability ──
        h_imp = game.get('home_implied_prob', 0.5)
        a_imp = game.get('away_implied_prob', 0.5)
        imp_diff = h_imp - a_imp
        factors['implied_prob'] = imp_diff
        home_score += max(0, imp_diff) * self.weights['implied_prob']
        away_score += max(0, -imp_diff) * self.weights['implied_prob']

        # ── Factor 25: Pythagorean Expectation ──
        h_pyth = self._pythagorean_wp(h_stats)
        a_pyth = self._pythagorean_wp(a_stats)
        pyth_diff = h_pyth - a_pyth
        factors['pythagorean'] = pyth_diff
        home_score += max(0, pyth_diff) * self.weights['pythagorean']
        away_score += max(0, -pyth_diff) * self.weights['pythagorean']

        # ── Factor 26: Streak Momentum ──
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        streak_diff = (h_streak - a_streak) / 10
        factors['streak'] = streak_diff
        home_score += max(0, streak_diff) * self.weights['streak']
        away_score += max(0, -streak_diff) * self.weights['streak']

        # ── Factor 27: Line Value ──
        spread = game.get('spread')
        if spread is not None:
            # Positive spread = home is underdog
            line_signal = -spread / 3.0  # normalize run line
            factors['line_value'] = line_signal
            factors['spread_signal'] = line_signal
            home_score += max(0, line_signal) * self.weights['line_value']
            away_score += max(0, -line_signal) * self.weights['line_value']
            home_score += max(0, line_signal) * self.weights['spread_signal']
            away_score += max(0, -line_signal) * self.weights['spread_signal']
        else:
            factors['line_value'] = 0
            factors['spread_signal'] = 0

        # ─── Compute Final Prediction ───────────────────────────
        total_score = home_score + away_score
        if total_score == 0:
            home_prob = 0.5
        else:
            home_prob = home_score / total_score

        # Blend with implied odds (30% market, 70% model)
        if h_imp and a_imp and (h_imp + a_imp) > 0:
            market_home = h_imp / (h_imp + a_imp)
            home_prob = 0.70 * home_prob + 0.30 * market_home

        # Clamp
        home_prob = max(0.20, min(0.80, home_prob))
        away_prob = 1 - home_prob

        predicted_winner = home if home_prob >= 0.5 else away
        confidence = max(home_prob, away_prob)

        # Spread pick (MLB run line is typically -1.5/+1.5)
        spread_val = game.get('spread')
        if spread_val is not None:
            if predicted_winner == home:
                spread_pick = f"{home} {spread_val:+.1f}" if spread_val else f"{home} -1.5"
            else:
                spread_pick = f"{away} {-spread_val:+.1f}" if spread_val else f"{away} +1.5"
        else:
            spread_pick = f"{predicted_winner} -1.5" if confidence > 0.60 else f"{predicted_winner} +1.5"

        # Over/Under pick (basic estimate)
        total_line = game.get('total')
        h_rpg = h_stats.get('runs_scored', LEAGUE_AVG['runs_per_game'])
        a_rpg = a_stats.get('runs_scored', LEAGUE_AVG['runs_per_game'])
        h_rapg = h_stats.get('runs_allowed', LEAGUE_AVG['runs_per_game'])
        a_rapg = a_stats.get('runs_allowed', LEAGUE_AVG['runs_per_game'])
        predicted_total = ((h_rpg + a_rapg) / 2) + ((a_rpg + h_rapg) / 2)
        predicted_total *= MLBDataFetcher.get_park_factor(game.get('venue', ''))

        ou_pick = None
        if total_line:
            edge = predicted_total - total_line
            if abs(edge) >= 0.5:
                ou_pick = f"{'OVER' if edge > 0 else 'UNDER'} {total_line}"

        # Value score: how much edge vs the market
        value_score = 0.0
        if h_imp and a_imp:
            if predicted_winner == home:
                value_score = home_prob - (h_imp / (h_imp + a_imp))
            else:
                value_score = away_prob - (a_imp / (h_imp + a_imp))

        # Pick type
        if confidence >= 0.70:
            pick_type = "LOCK"
        elif confidence >= 0.62:
            pick_type = "STRONG"
        elif confidence >= 0.55:
            pick_type = "LEAN"
        else:
            pick_type = "SKIP"

        return {
            'game_id': game.get('game_id', ''),
            'game_date': game.get('game_date', ''),
            'home_team': home,
            'away_team': away,
            'predicted_winner': predicted_winner,
            'confidence': round(confidence, 4),
            'home_win_prob': round(home_prob, 4),
            'away_win_prob': round(away_prob, 4),
            'spread_pick': spread_pick,
            'over_under_pick': ou_pick,
            'predicted_total': round(predicted_total, 1),
            'value_score': round(value_score, 4),
            'pick_type': pick_type,
            'factors': factors,
        }

    # ─── Helpers ────────────────────────────────────────────────

    def _get_team_stats(self, team_name: str) -> Dict:
        """Get stats for a team, with defaults."""
        # Try exact match
        if team_name in self.team_stats:
            return self.team_stats[team_name]
        # Try partial match
        for name, stats in self.team_stats.items():
            if team_name.lower() in name.lower() or name.lower() in team_name.lower():
                return stats
        return self._default_stats()

    def _default_stats(self) -> Dict:
        return {
            'wins': 0, 'losses': 0, 'win_pct': 0.5, 'games_played': 0,
            'runs_scored': LEAGUE_AVG['runs_per_game'],
            'runs_allowed': LEAGUE_AVG['runs_per_game'],
            'batting_avg': LEAGUE_AVG['batting_avg'],
            'obp': LEAGUE_AVG['obp'], 'slg': LEAGUE_AVG['slg'],
            'era': LEAGUE_AVG['era'], 'whip': LEAGUE_AVG['whip'],
            'k9': LEAGUE_AVG['k9'],
            'home_wins': 0, 'home_losses': 0,
            'away_wins': 0, 'away_losses': 0,
            'l10_wins': 5, 'l10_losses': 5, 'streak': 0,
        }

    def _home_win_pct(self, stats: Dict) -> float:
        hw = stats.get('home_wins', 0)
        hl = stats.get('home_losses', 0)
        if hw + hl == 0:
            return 0.54  # MLB home teams win ~54%
        return hw / (hw + hl)

    def _away_win_pct(self, stats: Dict) -> float:
        aw = stats.get('away_wins', 0)
        al = stats.get('away_losses', 0)
        if aw + al == 0:
            return 0.46
        return aw / (aw + al)

    def _pythagorean_wp(self, stats: Dict) -> float:
        """Baseball Pythagorean theorem (exponent ~1.83)."""
        rs = stats.get('runs_scored', LEAGUE_AVG['runs_per_game'])
        ra = stats.get('runs_allowed', LEAGUE_AVG['runs_per_game'])
        if rs + ra == 0:
            return 0.5
        exp = 1.83
        return (rs ** exp) / (rs ** exp + ra ** exp)

    def _store_prediction(self, pred: Dict):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO predictions
                (game_id, game_date, home_team, away_team, predicted_winner,
                 confidence, spread_pick, ou_pick, total, factors_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pred['game_id'], pred['game_date'],
                pred['home_team'], pred['away_team'],
                pred['predicted_winner'], pred['confidence'],
                pred['spread_pick'], pred.get('over_under_pick'),
                pred.get('predicted_total'),
                json.dumps(pred['factors']),
                datetime.now().isoformat()
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store prediction: {e}")


# ─── CLI ────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='MLB Prediction Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    args = parser.parse_args()

    engine = MLBEngine()
    target = date.fromisoformat(args.date) if args.date else None
    picks = engine.generate_picks(target)

    print(f"\n{'='*60}")
    print(f"MLB PICKS — {target or date.today()}")
    print(f"{'='*60}")

    if not picks:
        print("No games found for this date.")
    else:
        for p in picks:
            emoji = {'LOCK': '\U0001f512', 'STRONG': '\U0001f3af', 'LEAN': '\U0001f4ca', 'SKIP': '\u26a0\ufe0f'}.get(p['pick_type'], '')
            print(f"\n{emoji} {p['away_team']} @ {p['home_team']}")
            print(f"   Winner: {p['predicted_winner']} ({p['confidence']:.1%})")
            print(f"   Spread: {p['spread_pick']}")
            if p['over_under_pick']:
                print(f"   O/U: {p['over_under_pick']}")
            print(f"   Value: {p['value_score']:+.2%} | Type: {p['pick_type']}")
