"""
ParlayGuarantee NHL Engine — 25+ Factor NHL Prediction Model
Output format matches NBA/NCAAB engines for seamless integration.
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

from nhl_data_fetcher import NHLDataFetcher, DIVISION_STRENGTH, CONFERENCE_STRENGTH

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('nhl_engine.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'nhl_engine.db')

# NHL league averages (2024-25)
NHL_AVG_GPG = 3.10       # goals per game per team
NHL_AVG_SPG = 30.0       # shots per game
NHL_AVG_PP = 0.215       # power play %
NHL_AVG_PK = 0.795       # penalty kill %
NHL_AVG_SV = 0.905       # save %
NHL_AVG_SHOOT = 0.103    # shooting %
NHL_HOME_ADV = 0.545     # historical home win %

# ─── Factor Weights (25+ factors, sum ≈ 1.0) ───────────────────

DEFAULT_WEIGHTS = {
    # Team quality (30%)
    'points_pct':           0.07,
    'win_pct':              0.05,
    'goal_diff':            0.08,
    'record_strength':      0.05,
    'conference_strength':  0.03,
    'divisional_adj':       0.02,

    # Offense & Defense (20%)
    'goals_for':            0.04,
    'goals_against':        0.04,
    'shots_for':            0.03,
    'shots_against':        0.03,
    'shooting_pct':         0.02,
    'save_pct':             0.04,

    # Special teams (10%)
    'power_play':           0.05,
    'penalty_kill':         0.05,

    # Advanced estimates (8%)
    'corsi_estimate':       0.04,
    'fenwick_estimate':     0.04,

    # Form & momentum (12%)
    'last10_record':        0.05,
    'streak':               0.03,
    'recent_scoring':       0.02,
    'momentum':             0.02,

    # Situational (12%)
    'home_ice':             0.05,
    'back_to_back':         0.03,
    'rest_days':            0.02,
    'injury_impact':        0.02,

    # Market signals (8%)
    'implied_prob':         0.04,
    'line_movement':        0.02,
    'line_value':           0.02,
}


class NHLEngine:
    """25+ factor NHL prediction engine with standard ParlayGuarantee output."""

    def __init__(self):
        self.fetcher = NHLDataFetcher()
        self.weights = dict(DEFAULT_WEIGHTS)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS predictions (
            game_id TEXT PRIMARY KEY,
            game_date TEXT,
            home_team TEXT, away_team TEXT,
            predicted_winner TEXT, confidence REAL,
            spread_pick TEXT, over_under_pick TEXT,
            value_score REAL, pick_type TEXT,
            factors_json TEXT,
            actual_winner TEXT, correct INT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS weight_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, weights_json TEXT,
            accuracy REAL, sample_size INT
        )""")
        conn.commit()
        conn.close()

    # ─── Main Entry Point ───────────────────────────────────────

    def generate_picks(self, target_date: Optional[date] = None) -> List[Dict]:
        """
        Generate NHL picks for a date.
        Returns list of dicts in standard ParlayGuarantee format.
        """
        target = target_date if isinstance(target_date, date) else date.today()
        if isinstance(target_date, str):
            target = date.fromisoformat(target_date)

        logger.info(f"NHL Engine: generating picks for {target}")

        # 1. Fetch standings (team stats)
        self.fetcher.fetch_standings()

        # 2. Fetch games from Odds API
        games = self.fetcher.fetch_games_from_odds(target)
        if not games:
            # Fallback: try ESPN scoreboard
            espn_games = self.fetcher.fetch_scoreboard(target)
            if espn_games:
                games = [{
                    'game_id': g['game_id'],
                    'game_date': g['game_date'],
                    'game_time': '',
                    'home_team': g['home_team'],
                    'away_team': g['away_team'],
                    'home_odds': None, 'away_odds': None,
                    'home_implied_prob': 0.5, 'away_implied_prob': 0.5,
                    'spread': None, 'total': None,
                    'game_status': g.get('status', 'Scheduled'),
                } for g in espn_games]

        if not games:
            logger.warning("No NHL games found for this date")
            return []

        logger.info(f"Found {len(games)} NHL games")

        # 3. Analyze each game
        predictions = []
        for game in games:
            try:
                pred = self._analyze_game(game, target)
                if pred:
                    predictions.append(pred)
                    self._store_prediction(pred)
            except Exception as e:
                logger.error(f"Error analyzing {game['away_team']} @ {game['home_team']}: {e}")

        # 4. Sort by confidence
        predictions.sort(key=lambda x: x['confidence'], reverse=True)

        logger.info(f"Generated {len(predictions)} NHL predictions")
        return predictions

    # ─── Core Analysis ──────────────────────────────────────────

    def _analyze_game(self, game: Dict, target: date) -> Optional[Dict]:
        """Analyze a single NHL game across 25+ factors."""
        home = game['home_team']
        away = game['away_team']

        home_stats = self.fetcher.get_team_stats(home)
        away_stats = self.fetcher.get_team_stats(away)

        if not home_stats:
            home_stats = self._default_stats(home)
        if not away_stats:
            away_stats = self._default_stats(away)

        factors = {}
        home_score = 0.0
        away_score = 0.0

        def add_factor(name, diff):
            """Helper: positive diff = home advantage."""
            factors[name] = round(diff, 4)
            w = self.weights.get(name, 0)
            if diff > 0:
                home_score_add = min(abs(diff), 1.0) * w
                return home_score_add, 0
            else:
                away_score_add = min(abs(diff), 1.0) * w
                return 0, away_score_add

        # ── Factor 1: Points Percentage ──
        h_ppct = home_stats.get('points_pct', 0.5)
        a_ppct = away_stats.get('points_pct', 0.5)
        h, a = add_factor('points_pct', (h_ppct - a_ppct) * 2)
        home_score += h; away_score += a

        # ── Factor 2: Win Percentage ──
        h_wp = home_stats.get('win_pct', 0.5)
        a_wp = away_stats.get('win_pct', 0.5)
        h, a = add_factor('win_pct', (h_wp - a_wp) * 2)
        home_score += h; away_score += a

        # ── Factor 3: Goal Differential ──
        h_gd = home_stats.get('goals_per_game', NHL_AVG_GPG) - home_stats.get('goals_against_per_game', NHL_AVG_GPG)
        a_gd = away_stats.get('goals_per_game', NHL_AVG_GPG) - away_stats.get('goals_against_per_game', NHL_AVG_GPG)
        h, a = add_factor('goal_diff', (h_gd - a_gd) / 3)
        home_score += h; away_score += a

        # ── Factor 4: Record Strength (W-L adjusted for OTL) ──
        h_gp = max(home_stats.get('games_played', 1), 1)
        a_gp = max(away_stats.get('games_played', 1), 1)
        h_pts_rate = home_stats.get('points', 0) / (h_gp * 2)
        a_pts_rate = away_stats.get('points', 0) / (a_gp * 2)
        h, a = add_factor('record_strength', (h_pts_rate - a_pts_rate) * 2)
        home_score += h; away_score += a

        # ── Factor 5: Conference Strength ──
        h_conf = CONFERENCE_STRENGTH.get(home_stats.get('conference', ''), 0.80)
        a_conf = CONFERENCE_STRENGTH.get(away_stats.get('conference', ''), 0.80)
        h, a = add_factor('conference_strength', (h_conf - a_conf))
        home_score += h; away_score += a

        # ── Factor 6: Divisional Game Adjustment ──
        is_div = self.fetcher.is_divisional_game(home, away)
        div_adj = 0.3 if is_div else 0.0  # Divisional games are more competitive / home ice matters more
        factors['divisional_adj'] = div_adj
        if is_div:
            home_score += 0.15 * self.weights['divisional_adj']  # slight home boost in division

        # ── Factor 7-8: Goals For / Against ──
        h_gf = home_stats.get('goals_per_game', NHL_AVG_GPG)
        a_gf = away_stats.get('goals_per_game', NHL_AVG_GPG)
        h, a = add_factor('goals_for', (h_gf - a_gf) / 2)
        home_score += h; away_score += a

        h_ga = home_stats.get('goals_against_per_game', NHL_AVG_GPG)
        a_ga = away_stats.get('goals_against_per_game', NHL_AVG_GPG)
        h, a = add_factor('goals_against', (a_ga - h_ga) / 2)  # lower GA = better
        home_score += h; away_score += a

        # ── Factor 9-10: Shots For / Against ──
        h_sf = home_stats.get('shots_per_game', NHL_AVG_SPG)
        a_sf = away_stats.get('shots_per_game', NHL_AVG_SPG)
        h, a = add_factor('shots_for', (h_sf - a_sf) / 15)
        home_score += h; away_score += a

        h_sa = home_stats.get('shots_against_per_game', NHL_AVG_SPG)
        a_sa = away_stats.get('shots_against_per_game', NHL_AVG_SPG)
        h, a = add_factor('shots_against', (a_sa - h_sa) / 15)
        home_score += h; away_score += a

        # ── Factor 11: Shooting Percentage ──
        h_shoot = home_stats.get('shooting_pct', NHL_AVG_SHOOT)
        a_shoot = away_stats.get('shooting_pct', NHL_AVG_SHOOT)
        h, a = add_factor('shooting_pct', (h_shoot - a_shoot) * 10)
        home_score += h; away_score += a

        # ── Factor 12: Save Percentage ──
        h_sv = home_stats.get('save_pct', NHL_AVG_SV)
        a_sv = away_stats.get('save_pct', NHL_AVG_SV)
        h, a = add_factor('save_pct', (h_sv - a_sv) * 15)
        home_score += h; away_score += a

        # ── Factor 13: Power Play ──
        h_pp = home_stats.get('pp_pct', NHL_AVG_PP)
        a_pp = away_stats.get('pp_pct', NHL_AVG_PP)
        h, a = add_factor('power_play', (h_pp - a_pp) * 3)
        home_score += h; away_score += a

        # ── Factor 14: Penalty Kill ──
        h_pk = home_stats.get('pk_pct', NHL_AVG_PK)
        a_pk = away_stats.get('pk_pct', NHL_AVG_PK)
        h, a = add_factor('penalty_kill', (h_pk - a_pk) * 3)
        home_score += h; away_score += a

        # ── Factor 15: Corsi Estimate (shot attempts differential proxy) ──
        # Corsi ≈ shots + missed shots + blocked shots. We estimate from shots + goals context.
        h_corsi = h_sf * 1.6 - h_sa * 0.6  # rough proxy
        a_corsi = a_sf * 1.6 - a_sa * 0.6
        h, a = add_factor('corsi_estimate', (h_corsi - a_corsi) / 30)
        home_score += h; away_score += a

        # ── Factor 16: Fenwick Estimate (unblocked shot attempts) ──
        h_fenwick = h_sf * 1.3 - h_sa * 0.3
        a_fenwick = a_sf * 1.3 - a_sa * 0.3
        h, a = add_factor('fenwick_estimate', (h_fenwick - a_fenwick) / 30)
        home_score += h; away_score += a

        # ── Factor 17: Last 10 Record ──
        h_l10w = home_stats.get('last10_wins', 5)
        a_l10w = away_stats.get('last10_wins', 5)
        h_l10_pct = h_l10w / 10
        a_l10_pct = a_l10w / 10
        h, a = add_factor('last10_record', (h_l10_pct - a_l10_pct) * 2)
        home_score += h; away_score += a

        # ── Factor 18: Streak ──
        h_streak = home_stats.get('streak_count', 0)
        a_streak = away_stats.get('streak_count', 0)
        # Positive streak = winning, check streak text
        h_streak_val = h_streak if 'W' in str(home_stats.get('streak', '')) else -h_streak
        a_streak_val = a_streak if 'W' in str(away_stats.get('streak', '')) else -a_streak
        h, a = add_factor('streak', (h_streak_val - a_streak_val) / 10)
        home_score += h; away_score += a

        # ── Factor 19: Recent Scoring Trend ──
        # Use goals per game as proxy
        h, a = add_factor('recent_scoring', (h_gf - a_gf) / 4)
        home_score += h; away_score += a

        # ── Factor 20: Momentum (combined streak + L10) ──
        h_momentum = h_l10_pct * 0.6 + (max(0, h_streak_val) / 10) * 0.4
        a_momentum = a_l10_pct * 0.6 + (max(0, a_streak_val) / 10) * 0.4
        h, a = add_factor('momentum', (h_momentum - a_momentum))
        home_score += h; away_score += a

        # ── Factor 21: Home Ice Advantage ──
        h_home_w = home_stats.get('home_wins', 0)
        h_home_l = home_stats.get('home_losses', 0) + home_stats.get('home_otl', 0)
        h_home_pct = h_home_w / max(h_home_w + h_home_l, 1)

        a_away_w = away_stats.get('away_wins', 0)
        a_away_l = away_stats.get('away_losses', 0) + away_stats.get('away_otl', 0)
        a_away_pct = a_away_w / max(a_away_w + a_away_l, 1)

        home_ice_adj = (h_home_pct - a_away_pct + (NHL_HOME_ADV - 0.5)) / 2
        factors['home_ice'] = round(home_ice_adj, 4)
        home_score += max(0, home_ice_adj) * self.weights['home_ice']
        away_score += max(0, -home_ice_adj) * self.weights['home_ice']

        # ── Factor 22: Back-to-Back Detection ──
        h_b2b = self.fetcher.detect_back_to_back(home, target)
        a_b2b = self.fetcher.detect_back_to_back(away, target)
        b2b_diff = 0
        if h_b2b and not a_b2b:
            b2b_diff = -0.6  # home disadvantage
        elif a_b2b and not h_b2b:
            b2b_diff = 0.6   # home advantage
        elif h_b2b and a_b2b:
            b2b_diff = 0.1   # both tired, slight home edge
        factors['back_to_back'] = round(b2b_diff, 4)
        factors['home_b2b'] = h_b2b
        factors['away_b2b'] = a_b2b
        home_score += max(0, b2b_diff) * self.weights['back_to_back']
        away_score += max(0, -b2b_diff) * self.weights['back_to_back']

        # ── Factor 23: Rest Days ──
        h_rest = self.fetcher.get_rest_days(home, target)
        a_rest = self.fetcher.get_rest_days(away, target)
        rest_diff = (h_rest - a_rest) / 4  # normalize
        rest_diff = max(-1, min(1, rest_diff))
        factors['rest_days'] = round(rest_diff, 4)
        factors['home_rest'] = h_rest
        factors['away_rest'] = a_rest
        home_score += max(0, rest_diff) * self.weights['rest_days']
        away_score += max(0, -rest_diff) * self.weights['rest_days']

        # ── Factor 24: Injury Impact ──
        h_inj = self.fetcher.get_team_injury_impact(home)
        a_inj = self.fetcher.get_team_injury_impact(away)
        inj_diff = a_inj - h_inj  # positive = away more hurt = home advantage
        h, a = add_factor('injury_impact', inj_diff * 3)
        home_score += h; away_score += a

        # ── Factor 25: Implied Probability (market) ──
        home_imp = game.get('home_implied_prob', 0.5)
        away_imp = game.get('away_implied_prob', 0.5)
        imp_diff = (home_imp - away_imp)
        h, a = add_factor('implied_prob', imp_diff)
        home_score += h; away_score += a

        # ── Factor 26: Line Movement ──
        movement = self.fetcher.get_line_movement(home, away, game.get('game_date', ''))
        move_val = movement.get('movement', 0) / 50  # normalize
        factors['line_movement'] = round(move_val, 4)
        factors['sharp_action'] = movement.get('sharp', False)
        home_score += max(0, move_val) * self.weights['line_movement']
        away_score += max(0, -move_val) * self.weights['line_movement']

        # ── Factor 27: Line Value (model vs market) ──
        # Computed after blending

        # ─── Blend & Compute Final Probability ───
        total_score = home_score + away_score
        if total_score == 0:
            model_home_prob = 0.5
        else:
            model_home_prob = home_score / total_score

        # Blend model with market (60/40)
        blended_home = model_home_prob * 0.60 + home_imp * 0.40
        blended_away = 1 - blended_home

        # Line value: difference between our prob and market
        line_value = blended_home - home_imp
        factors['line_value'] = round(line_value, 4)

        # Determine winner
        if blended_home >= blended_away:
            predicted_winner = home
            win_prob = blended_home
        else:
            predicted_winner = away
            win_prob = blended_away

        # Confidence (0-100 scale)
        confidence = round(self._prob_to_confidence(win_prob), 1)

        # Value score (how much edge we see vs market)
        value_score = round(abs(line_value) * 100, 1)

        # Pick type classification
        pick_type = self._classify_pick(confidence, value_score, line_value, blended_home, home_imp)

        # Spread pick
        spread = game.get('spread')
        spread_pick = None
        if spread is not None:
            pred_margin = (blended_home - 0.5) * 4  # NHL margins are small
            cover_margin = pred_margin + spread
            if cover_margin > 0:
                spread_pick = f"{home} {spread:+.1f}"
            else:
                spread_pick = f"{away} {-spread:+.1f}"

        # Over/Under pick
        total = game.get('total')
        over_under_pick = None
        if total:
            est_total = h_gf + a_gf  # simple estimate
            # Adjust for pace matchup
            pace_adj = ((h_sf + a_sf) / 2 - NHL_AVG_SPG) * 0.05
            est_total += pace_adj
            # Defense adjustment
            def_adj = ((NHL_AVG_GPG - h_ga) + (NHL_AVG_GPG - a_ga)) / 2
            est_total -= def_adj * 0.3

            if est_total > total + 0.3:
                over_under_pick = f"Over {total}"
            elif est_total < total - 0.3:
                over_under_pick = f"Under {total}"

        return {
            'game_id': game.get('game_id', ''),
            'game_date': game.get('game_date', ''),
            'game_time': game.get('game_time', ''),
            'sport': 'NHL',
            'home_team': home,
            'away_team': away,
            'predicted_winner': predicted_winner,
            'confidence': confidence,
            'win_probability': round(win_prob, 4),
            'spread_pick': spread_pick,
            'spread': spread,
            'over_under_pick': over_under_pick,
            'total': total,
            'value_score': value_score,
            'pick_type': pick_type,
            'home_win_prob': round(blended_home, 4),
            'away_win_prob': round(blended_away, 4),
            'market_home_prob': round(home_imp, 4),
            'market_away_prob': round(away_imp, 4),
            'home_odds': game.get('home_odds'),
            'away_odds': game.get('away_odds'),
            'factors': factors,
            'home_record': f"{home_stats.get('wins',0)}-{home_stats.get('losses',0)}-{home_stats.get('otl',0)}",
            'away_record': f"{away_stats.get('wins',0)}-{away_stats.get('losses',0)}-{away_stats.get('otl',0)}",
            'home_division': home_stats.get('division', ''),
            'away_division': away_stats.get('division', ''),
        }

    def _prob_to_confidence(self, prob: float) -> float:
        """Convert win probability to 0-100 confidence score."""
        # prob of 0.5 = 50 confidence (coin flip)
        # prob of 0.7 = ~72 confidence
        # prob of 0.85+ = 85+ confidence
        edge = abs(prob - 0.5) * 2  # 0 to 1
        # Logarithmic scaling — harder to get very high confidence
        confidence = 50 + edge * 40 + (edge ** 2) * 10
        return min(95, max(50, confidence))

    def _classify_pick(self, confidence: float, value_score: float,
                       line_value: float, model_prob: float, market_prob: float) -> str:
        """Classify pick as LOCK/VALUE/UPSET/LEAN."""
        if confidence >= 72 and value_score >= 5:
            return 'LOCK'
        elif value_score >= 8:
            return 'VALUE'
        elif (model_prob < 0.5 and market_prob > 0.55) or (model_prob > 0.5 and market_prob < 0.45):
            # We disagree with market on who wins
            return 'UPSET'
        elif confidence >= 60:
            return 'LEAN'
        else:
            return 'LEAN'

    def _default_stats(self, team_name: str) -> Dict:
        """Default stats for unknown teams."""
        return {
            'team_name': team_name,
            'wins': 20, 'losses': 20, 'otl': 5,
            'points': 45, 'points_pct': 0.500,
            'games_played': 45,
            'goals_for': 135, 'goals_against': 135,
            'goals_per_game': NHL_AVG_GPG, 'goals_against_per_game': NHL_AVG_GPG,
            'pp_pct': NHL_AVG_PP, 'pk_pct': NHL_AVG_PK,
            'shots_per_game': NHL_AVG_SPG, 'shots_against_per_game': NHL_AVG_SPG,
            'save_pct': NHL_AVG_SV, 'shooting_pct': NHL_AVG_SHOOT,
            'faceoff_pct': 0.500,
            'home_wins': 12, 'home_losses': 8, 'home_otl': 2,
            'away_wins': 8, 'away_losses': 12, 'away_otl': 3,
            'last10_wins': 5, 'last10_losses': 4, 'last10_otl': 1,
            'streak': 'W1', 'streak_count': 1,
            'win_pct': 0.500,
            'division': '', 'conference': '',
        }

    def _store_prediction(self, pred: Dict):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""INSERT OR REPLACE INTO predictions
                (game_id, game_date, home_team, away_team,
                 predicted_winner, confidence, spread_pick, over_under_pick,
                 value_score, pick_type, factors_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pred['game_id'], pred['game_date'],
                 pred['home_team'], pred['away_team'],
                 pred['predicted_winner'], pred['confidence'],
                 pred.get('spread_pick'), pred.get('over_under_pick'),
                 pred.get('value_score', 0), pred.get('pick_type', ''),
                 json.dumps(pred.get('factors', {}))))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store prediction: {e}")

    # ─── Scoring & Learning ─────────────────────────────────────

    def score_results(self, target_date: Optional[date] = None) -> Dict:
        """Score past predictions against actual results."""
        td = target_date or (date.today() - timedelta(days=1))
        games = self.fetcher.fetch_scoreboard(td)

        conn = sqlite3.connect(DB_PATH)
        correct = total = 0
        for g in games:
            if g.get('status') != 'STATUS_FINAL':
                continue
            actual_winner = g['home_team'] if g['home_score'] > g['away_score'] else g['away_team']
            row = conn.execute(
                "SELECT predicted_winner FROM predictions WHERE game_date = ? AND home_team = ?",
                (td.isoformat(), g['home_team'])).fetchone()
            if row:
                is_correct = 1 if row[0] == actual_winner else 0
                conn.execute(
                    "UPDATE predictions SET actual_winner = ?, correct = ? WHERE game_date = ? AND home_team = ?",
                    (actual_winner, is_correct, td.isoformat(), g['home_team']))
                correct += is_correct
                total += 1
        conn.commit()
        conn.close()

        accuracy = correct / total if total > 0 else 0
        logger.info(f"NHL Results {td}: {correct}/{total} = {accuracy:.1%}")
        return {'correct': correct, 'total': total, 'accuracy': accuracy}

    def get_accuracy_stats(self) -> Dict:
        """Get overall prediction accuracy."""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT correct, COUNT(*) FROM predictions WHERE correct IS NOT NULL GROUP BY correct"
        ).fetchall()
        conn.close()
        stats = {str(r[0]): r[1] for r in rows}
        c = stats.get('1', 0)
        w = stats.get('0', 0)
        t = c + w
        return {'correct': c, 'wrong': w, 'total': t, 'accuracy': c / t if t > 0 else 0}


# ─── CLI ────────────────────────────────────────────────────────

def run_predictions(target_date: Optional[str] = None, output_file: Optional[str] = None):
    engine = NHLEngine()
    td = date.fromisoformat(target_date) if target_date else date.today()
    predictions = engine.generate_picks(td)

    if not predictions:
        print("No NHL games found.")
        return

    print(f"\n{'='*70}")
    print(f"  🏒 NHL PREDICTIONS — {td.strftime('%A %B %d, %Y')}")
    print(f"{'='*70}\n")

    for i, p in enumerate(predictions, 1):
        winner = p['predicted_winner']
        loser = p['away_team'] if winner == p['home_team'] else p['home_team']
        conf = p['confidence']
        pick_type = p['pick_type']

        type_emoji = {'LOCK': '🔒', 'VALUE': '💰', 'UPSET': '🔥', 'LEAN': '📊'}.get(pick_type, '📊')

        print(f"  {i:2d}. {type_emoji} {pick_type}: {winner} over {loser}")
        print(f"      Confidence: {conf:.0f}%  |  Value: {p['value_score']:.1f}")
        if p.get('spread_pick'):
            print(f"      Spread: {p['spread_pick']}")
        if p.get('over_under_pick'):
            print(f"      O/U: {p['over_under_pick']}")
        print(f"      {p['home_team']} ({p['home_record']}) vs {p['away_team']} ({p['away_record']})")
        print()

    out = output_file or f"nhl_picks_{td.isoformat()}.json"
    clean = [{k: v for k, v in p.items() if k != 'factors'} for p in predictions]
    with open(os.path.join(os.path.dirname(__file__), out), 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(predictions)} predictions to {out}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='NHL Prediction Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_predictions(args.date, args.output)
