# -*- coding: utf-8 -*-
"""
ParlayGuarantee Soccer Engine — 27-factor prediction model
Supports 3-way outcomes (Home / Draw / Away) across 7 leagues.

Output format matches ParlayGuarantee standard:
  home_team, away_team, predicted_winner, confidence, spread_pick,
  over_under_pick, value_score, pick_type, league, draw_probability
"""

import sys
import json
import math
import logging
import sqlite3
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from soccer_data_fetcher import SoccerDataFetcher, LEAGUES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('soccer_engine.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'soccer_engine.db')

# ─── Factor weights (27 factors) ─────────────────────────────

DEFAULT_WEIGHTS = {
    # Team quality (22%)
    'league_position':       0.06,
    'goal_difference':       0.05,
    'win_pct':               0.05,
    'points_per_game':       0.06,

    # Scoring (14%)
    'goals_scored_pg':       0.04,
    'goals_conceded_pg':     0.04,
    'xg_estimate':           0.03,
    'shots_on_target':       0.03,

    # Form (14%)
    'recent_form_l5':        0.06,
    'home_away_form':        0.05,
    'head_to_head':          0.03,

    # Defensive (10%)
    'clean_sheets':          0.03,
    'defensive_solidity':    0.04,
    'set_piece_strength':    0.03,

    # Possession / style (8%)
    'possession_pct':        0.03,
    'pass_accuracy':         0.03,
    'corner_differential':   0.02,

    # Situational (14%)
    'home_advantage':        0.05,
    'fixture_congestion':    0.03,
    'travel_distance':       0.02,
    'derby_rivalry':         0.02,
    'manager_tenure':        0.02,

    # Draw tendency (8%)
    'draw_tendency':         0.04,
    'match_importance':      0.02,
    'league_draw_rate':      0.02,

    # Market (10%)
    'implied_prob':          0.05,
    'spread_signal':         0.03,
    'line_value':            0.02,
}

# Average draw rates by league (historical)
LEAGUE_DRAW_RATES = {
    'soccer_epl': 0.24,
    'soccer_spain_la_liga': 0.24,
    'soccer_germany_bundesliga': 0.23,
    'soccer_italy_serie_a': 0.26,
    'soccer_france_ligue_one': 0.25,
    'soccer_usa_mls': 0.21,
    'soccer_uefa_champs_league': 0.22,
}

# Average goals per game by league
LEAGUE_AVG_GOALS = {
    'soccer_epl': 2.75,
    'soccer_spain_la_liga': 2.60,
    'soccer_germany_bundesliga': 3.05,
    'soccer_italy_serie_a': 2.65,
    'soccer_france_ligue_one': 2.55,
    'soccer_usa_mls': 2.95,
    'soccer_uefa_champs_league': 2.90,
}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


class SoccerEngine:
    """27-factor soccer prediction engine with 3-way outcome support."""

    def __init__(self):
        self.fetcher = SoccerDataFetcher()
        self.weights = dict(DEFAULT_WEIGHTS)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                game_id TEXT PRIMARY KEY,
                game_date TEXT, league TEXT,
                home_team TEXT, away_team TEXT,
                predicted_winner TEXT, confidence REAL,
                home_prob REAL, draw_prob REAL, away_prob REAL,
                spread_pick TEXT, ou_pick TEXT,
                value_score REAL,
                factors_json TEXT,
                actual_result TEXT, correct INT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    # ─── Main entry point ─────────────────────────────────────

    def generate_picks(self, target_date: Optional[date] = None,
                       leagues: Optional[List[str]] = None) -> List[Dict]:
        """
        Generate soccer picks across leagues.
        If leagues is None, fetch all supported leagues.
        """
        target = target_date or date.today()
        logger.info(f"Soccer Engine: generating picks for {target}")

        all_games = self.fetcher.fetch_all_games(target, leagues)
        if not all_games:
            logger.warning("No soccer games found")
            return []

        # Fetch standings for each league
        standings_map = {}
        for lk in all_games:
            standings_map[lk] = self.fetcher.get_standings(lk)

        predictions = []
        for league_key, games in all_games.items():
            standings = standings_map.get(league_key, [])
            stand_by_name = self._index_standings(standings)

            for game in games:
                try:
                    pred = self._analyze_game(game, stand_by_name, league_key)
                    if pred:
                        predictions.append(pred)
                        self._store_prediction(pred)
                except Exception as e:
                    logger.error(f"Error analyzing {game.get('home_team')} vs "
                                 f"{game.get('away_team')}: {e}")

        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        logger.info(f"Generated {len(predictions)} soccer predictions")
        return predictions

    # ─── Game analysis ────────────────────────────────────────

    def _analyze_game(self, game: Dict, standings: Dict, league_key: str) -> Optional[Dict]:
        home = game['home_team']
        away = game['away_team']
        espn_slug = LEAGUES[league_key][0]

        home_stand = standings.get(home.lower(), self._default_standing(home))
        away_stand = standings.get(away.lower(), self._default_standing(away))

        factors = {}
        home_score = 0.0
        away_score = 0.0
        draw_score = 0.0

        # Helper to add factor
        def add_factor(name, diff, draw_boost=0.0):
            nonlocal home_score, away_score, draw_score
            factors[name] = diff
            w = self.weights.get(name, 0)
            home_score += max(0, diff) * w
            away_score += max(0, -diff) * w
            draw_score += draw_boost * w

        # ── 1. League position ──
        h_pos = home_stand.get('position', 10)
        a_pos = away_stand.get('position', 10)
        pos_diff = (a_pos - h_pos) / 20  # positive = home better
        # Close positions -> draw more likely
        pos_closeness = 1 - abs(h_pos - a_pos) / 20
        add_factor('league_position', pos_diff, pos_closeness * 0.3)

        # ── 2. Goal difference ──
        h_gd = home_stand.get('goal_diff', 0)
        a_gd = away_stand.get('goal_diff', 0)
        gp_h = max(home_stand.get('games_played', 1), 1)
        gp_a = max(away_stand.get('games_played', 1), 1)
        gd_diff = (h_gd / gp_h - a_gd / gp_a) / 2
        add_factor('goal_difference', gd_diff)

        # ── 3. Win percentage ──
        h_wp = home_stand.get('wins', 0) / gp_h
        a_wp = away_stand.get('wins', 0) / gp_a
        add_factor('win_pct', (h_wp - a_wp) * 2)

        # ── 4. Points per game ──
        h_ppg = home_stand.get('points', 0) / gp_h
        a_ppg = away_stand.get('points', 0) / gp_a
        ppg_diff = (h_ppg - a_ppg) / 3  # max PPG ~3
        add_factor('points_per_game', ppg_diff, (1 - abs(ppg_diff)) * 0.2)

        # ── 5-6. Goals scored/conceded per game ──
        h_gf_pg = home_stand.get('goals_for', 0) / gp_h
        a_gf_pg = away_stand.get('goals_for', 0) / gp_a
        h_ga_pg = home_stand.get('goals_against', 0) / gp_h
        a_ga_pg = away_stand.get('goals_against', 0) / gp_a
        add_factor('goals_scored_pg', (h_gf_pg - a_gf_pg) / 2)
        add_factor('goals_conceded_pg', (a_ga_pg - h_ga_pg) / 2)  # lower = better

        # ── 7. xG estimate (approximation from goals + shots) ──
        # Use goals scored as proxy weighted by league average
        avg_goals = LEAGUE_AVG_GOALS.get(league_key, 2.75)
        h_xg = h_gf_pg * 0.85 + avg_goals / 2 * 0.15
        a_xg = a_gf_pg * 0.85 + avg_goals / 2 * 0.15
        add_factor('xg_estimate', (h_xg - a_xg) / 2)

        # ── 8. Shots on target (from game stats if available) ──
        h_sot = float(game.get('stats', {}).get('home_shotsOnTarget', 0) or 0)
        a_sot = float(game.get('stats', {}).get('away_shotsOnTarget', 0) or 0)
        if h_sot + a_sot > 0:
            sot_diff = (h_sot - a_sot) / max(h_sot + a_sot, 1)
        else:
            sot_diff = (h_gf_pg - a_gf_pg) * 0.3  # proxy
        add_factor('shots_on_target', sot_diff)

        # ── 9. Recent form L5 ──
        h_form_pts = self._form_points(home_stand)
        a_form_pts = self._form_points(away_stand)
        form_diff = (h_form_pts - a_form_pts) / 15  # max 15 pts in 5 games
        add_factor('recent_form_l5', form_diff, (1 - abs(form_diff)) * 0.3)

        # ── 10. Home/Away form ──
        h_home_wp = home_stand.get('wins', 0) / max(gp_h / 2, 1) * 0.6  # rough home bias
        a_away_wp = away_stand.get('wins', 0) / max(gp_a / 2, 1) * 0.4
        add_factor('home_away_form', (h_home_wp - a_away_wp))

        # ── 11. Head to head ──
        # Would need historical H2H data; default to neutral
        add_factor('head_to_head', 0.0, 0.1)

        # ── 12. Clean sheets ──
        h_cs_rate = 0.3  # default
        a_cs_rate = 0.3
        # If we have goals_against, compute
        if h_ga_pg > 0:
            h_cs_rate = max(0, 1 - h_ga_pg)  # rough approximation
        if a_ga_pg > 0:
            a_cs_rate = max(0, 1 - a_ga_pg)
        add_factor('clean_sheets', (h_cs_rate - a_cs_rate))

        # ── 13. Defensive solidity ──
        # Lower goals conceded = better
        def_diff = (a_ga_pg - h_ga_pg) / 2
        add_factor('defensive_solidity', def_diff)

        # ── 14. Set piece strength ──
        # Proxy: corners + free kick goals (limited data)
        add_factor('set_piece_strength', 0.0)

        # ── 15-16. Possession & pass accuracy ──
        h_poss = float(game.get('stats', {}).get('home_possessionPct', 50) or 50)
        a_poss = float(game.get('stats', {}).get('away_possessionPct', 50) or 50)
        add_factor('possession_pct', (h_poss - a_poss) / 50)
        add_factor('pass_accuracy', 0.0)  # limited data

        # ── 17. Corner differential ──
        h_corners = float(game.get('stats', {}).get('home_wonCorners', 0) or 0)
        a_corners = float(game.get('stats', {}).get('away_wonCorners', 0) or 0)
        if h_corners + a_corners > 0:
            add_factor('corner_differential', (h_corners - a_corners) / max(h_corners + a_corners, 1))
        else:
            add_factor('corner_differential', 0.0)

        # ── 18. Home advantage ──
        # Soccer home advantage ~45% win, 27% draw, 28% away
        factors['home_advantage'] = 0.55
        home_score += 0.55 * self.weights['home_advantage']
        draw_score += 0.15 * self.weights['home_advantage']

        # ── 19. Fixture congestion ──
        # Placeholder — would need schedule analysis
        add_factor('fixture_congestion', 0.0)

        # ── 20. Travel distance ──
        add_factor('travel_distance', 0.0)

        # ── 21. Derby/Rivalry ──
        is_derby = self.fetcher.is_rivalry(home, away)
        if is_derby:
            factors['derby_rivalry'] = 1.0
            draw_score += 0.5 * self.weights['derby_rivalry']  # Derbies draw more
        else:
            factors['derby_rivalry'] = 0.0

        # ── 22. Manager tenure ──
        add_factor('manager_tenure', 0.0)

        # ── 23-25. Draw tendency / match importance / league draw rate ──
        league_dr = LEAGUE_DRAW_RATES.get(league_key, 0.24)
        h_draw_rate = home_stand.get('draws', 0) / gp_h
        a_draw_rate = away_stand.get('draws', 0) / gp_a
        avg_draw_rate = (h_draw_rate + a_draw_rate) / 2
        factors['draw_tendency'] = avg_draw_rate
        draw_score += avg_draw_rate * self.weights['draw_tendency'] * 3

        factors['match_importance'] = 0.0
        factors['league_draw_rate'] = league_dr
        draw_score += league_dr * self.weights['league_draw_rate'] * 2

        # ── 26-28. Market signals ──
        h_imp = game.get('home_implied_prob', 0.33)
        d_imp = game.get('draw_implied_prob', 0.33)
        a_imp = game.get('away_implied_prob', 0.33)

        factors['implied_prob'] = h_imp - a_imp
        home_score += max(0, h_imp - 0.33) * self.weights['implied_prob']
        away_score += max(0, a_imp - 0.33) * self.weights['implied_prob']
        draw_score += max(0, d_imp - 0.25) * self.weights['implied_prob']

        spread = game.get('spread')
        if spread is not None:
            spread_signal = -spread / 3  # normalize for soccer (smaller scores)
            factors['spread_signal'] = spread_signal
            home_score += max(0, spread_signal) * self.weights['spread_signal']
            away_score += max(0, -spread_signal) * self.weights['spread_signal']
        else:
            factors['spread_signal'] = 0

        factors['line_value'] = 0

        # ─── Compute 3-way probabilities ──────────────────────

        # Raw scores -> probabilities via softmax-style
        raw_total = home_score + draw_score + away_score
        if raw_total > 0:
            home_raw = home_score / raw_total
            draw_raw = draw_score / raw_total
            away_raw = away_score / raw_total
        else:
            home_raw, draw_raw, away_raw = 0.40, 0.25, 0.35

        # Blend with market probabilities (50/50 model/market)
        model_w, market_w = 0.50, 0.50
        home_prob = model_w * home_raw + market_w * h_imp
        draw_prob = model_w * draw_raw + market_w * d_imp
        away_prob = model_w * away_raw + market_w * a_imp

        # Normalize
        prob_total = home_prob + draw_prob + away_prob
        if prob_total > 0:
            home_prob /= prob_total
            draw_prob /= prob_total
            away_prob /= prob_total

        # Clamp draw to reasonable range
        draw_prob = _clamp(draw_prob, 0.10, 0.45)
        # Re-normalize
        side_total = home_prob + away_prob
        remaining = 1.0 - draw_prob
        if side_total > 0:
            home_prob = home_prob / side_total * remaining
            away_prob = away_prob / side_total * remaining

        # Determine predicted winner
        probs = {'Home': home_prob, 'Draw': draw_prob, 'Away': away_prob}
        best_outcome = max(probs, key=probs.get)
        if best_outcome == 'Home':
            predicted_winner = home
            confidence = home_prob
        elif best_outcome == 'Away':
            predicted_winner = away
            confidence = away_prob
        else:
            predicted_winner = 'Draw'
            confidence = draw_prob

        # Spread pick
        spread_pick = None
        if spread is not None:
            pred_margin = (home_prob - away_prob) * 2  # rough goals margin
            cover = pred_margin + spread
            if cover > 0:
                spread_pick = f"{home} {spread:+.1f}"
            else:
                spread_pick = f"{away} {-spread:+.1f}"

        # Over/Under (delegated to totals engine, but basic version here)
        total = game.get('total')
        ou_pick = None
        if total:
            est_goals = h_gf_pg + a_gf_pg
            if est_goals > total + 0.3:
                ou_pick = f"Over {total}"
            elif est_goals < total - 0.3:
                ou_pick = f"Under {total}"

        # Value score: how much our model diverges from market
        value_score = 0.0
        if best_outcome == 'Home':
            value_score = (home_prob - h_imp) * 100
        elif best_outcome == 'Away':
            value_score = (away_prob - a_imp) * 100
        else:
            value_score = (draw_prob - d_imp) * 100

        return {
            'game_id': game.get('game_id', ''),
            'game_date': game.get('game_date', ''),
            'game_time': game.get('game_time', ''),
            'sport': 'Soccer',
            'league': league_key,
            'league_name': game.get('league_name', ''),
            'home_team': home,
            'away_team': away,
            'predicted_winner': predicted_winner,
            'confidence': round(confidence, 4),
            'home_win_prob': round(home_prob, 4),
            'draw_probability': round(draw_prob, 4),
            'away_win_prob': round(away_prob, 4),
            'spread_pick': spread_pick,
            'over_under_pick': ou_pick,
            'total': total,
            'value_score': round(value_score, 2),
            'pick_type': 'moneyline',
            'factors': factors,
            'home_position': h_pos,
            'away_position': a_pos,
            'home_record': f"{home_stand.get('wins',0)}W-{home_stand.get('draws',0)}D-{home_stand.get('losses',0)}L",
            'away_record': f"{away_stand.get('wins',0)}W-{away_stand.get('draws',0)}D-{away_stand.get('losses',0)}L",
            'market_home_prob': round(h_imp, 4),
            'market_draw_prob': round(d_imp, 4),
            'market_away_prob': round(a_imp, 4),
        }

    # ─── Helpers ──────────────────────────────────────────────

    def _index_standings(self, standings: List[Dict]) -> Dict:
        idx = {}
        for s in standings:
            idx[s['team'].lower()] = s
        return idx

    def _default_standing(self, team: str) -> Dict:
        return {
            'team': team, 'position': 10, 'games_played': 10,
            'wins': 3, 'draws': 3, 'losses': 4,
            'goals_for': 12, 'goals_against': 14,
            'goal_diff': -2, 'points': 12,
        }

    def _form_points(self, standing: Dict) -> float:
        """Estimate form points from last 5 (3 pts/win, 1 pt/draw)."""
        gp = max(standing.get('games_played', 1), 1)
        ppg = standing.get('points', 0) / gp
        return ppg * 5  # extrapolate to 5-game form

    def _store_prediction(self, pred: Dict):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO predictions
                (game_id, game_date, league, home_team, away_team,
                 predicted_winner, confidence, home_prob, draw_prob, away_prob,
                 spread_pick, ou_pick, value_score, factors_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pred['game_id'], pred['game_date'], pred['league'],
                pred['home_team'], pred['away_team'],
                pred['predicted_winner'], pred['confidence'],
                pred['home_win_prob'], pred['draw_probability'], pred['away_win_prob'],
                pred.get('spread_pick'), pred.get('over_under_pick'),
                pred.get('value_score', 0),
                json.dumps(pred.get('factors', {})),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store prediction: {e}")

    # ─── Accuracy tracking ────────────────────────────────────

    def score_results(self, results: List[Dict]) -> Dict:
        """Score predictions against actual results."""
        conn = sqlite3.connect(DB_PATH)
        correct, total = 0, 0
        for r in results:
            row = conn.execute(
                "SELECT predicted_winner FROM predictions WHERE game_id = ?",
                (r['game_id'],)
            ).fetchone()
            if row:
                is_correct = 1 if row[0] == r['actual_result'] else 0
                conn.execute(
                    "UPDATE predictions SET actual_result = ?, correct = ? WHERE game_id = ?",
                    (r['actual_result'], is_correct, r['game_id'])
                )
                correct += is_correct
                total += 1
        conn.commit()
        conn.close()
        return {'correct': correct, 'total': total,
                'accuracy': correct / total if total > 0 else 0}


# ─── CLI ──────────────────────────────────────────────────────

def run_predictions(target_date: str = None, league_filter: str = None,
                    output_file: str = None):
    engine = SoccerEngine()
    td = date.fromisoformat(target_date) if target_date else date.today()
    leagues = [league_filter] if league_filter else None

    predictions = engine.generate_picks(td, leagues)
    if not predictions:
        print("No games found.")
        return

    print(f"\n{'='*70}")
    print(f"  SOCCER PREDICTIONS \u2014 {td.strftime('%A %B %d, %Y')}")
    print(f"{'='*70}\n")

    for i, p in enumerate(predictions, 1):
        winner = p['predicted_winner']
        conf = p['confidence']
        league = p.get('league_name', p['league'])
        conf_bar = '\u2588' * int(conf * 20) + '\u2591' * (20 - int(conf * 20))

        print(f"  {i:2d}. [{league}] {p['home_team']} vs {p['away_team']}")
        print(f"      Pick: {winner} [{conf_bar}] {conf:.1%}")
        print(f"      Probs: H {p['home_win_prob']:.1%} | D {p['draw_probability']:.1%} | A {p['away_win_prob']:.1%}")
        if p.get('spread_pick'):
            print(f"      Spread: {p['spread_pick']}")
        if p.get('over_under_pick'):
            print(f"      O/U: {p['over_under_pick']}")
        if p.get('value_score', 0) > 2:
            print(f"      \U0001f4b0 VALUE: +{p['value_score']:.1f}%")
        print()

    out = output_file or f"soccer_picks_{td.isoformat()}.json"
    clean = [{k: v for k, v in p.items() if k != 'factors'} for p in predictions]
    with open(os.path.join(os.path.dirname(__file__), out), 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(predictions)} predictions to {out}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Soccer Prediction Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--league', type=str, help='League key filter')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_predictions(args.date, args.league, args.output)
