"""
ParlayGuarantee NCAAB Engine — College Basketball Prediction Engine
30+ factor model with March Madness tournament-specific logic

Architecture matches engine_v2.py (NBA) output format:
  home_team, away_team, predicted_winner, confidence, spread_pick, etc.
"""

import sys
import json
import logging
import sqlite3
import math
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from ncaab_data_fetcher import NCAABDataFetcher, CONFERENCE_STRENGTH, SEED_UPSET_HISTORY

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('ncaab_engine.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'ncaab_engine.db')

# ─── Factor Weights (30 factors, sum ~1.0) ─────────────────────

DEFAULT_WEIGHTS = {
    # Team quality (35%)
    'net_ranking':          0.08,
    'win_pct':              0.05,
    'conf_strength':        0.05,
    'off_efficiency':       0.06,
    'def_efficiency':       0.06,
    'sos':                  0.05,

    # Shooting & efficiency (15%)
    'fg_pct':               0.04,
    'three_pct':            0.04,
    'ft_pct':               0.02,
    'turnovers':            0.03,
    'assists':              0.02,

    # Pace & style (8%)
    'tempo':                0.04,
    'rebounding':           0.04,

    # Form & momentum (12%)
    'last10_record':        0.06,
    'streak':               0.03,
    'momentum_trend':       0.03,

    # Situational (15%)
    'home_court':           0.06,
    'rest_days':            0.03,
    'travel':               0.02,
    'rivalry':              0.02,
    'time_of_season':       0.02,

    # Market signals (10%)
    'implied_prob':         0.05,
    'spread_signal':        0.03,
    'line_value':           0.02,

    # Tournament-specific (5% — activated only during March Madness)
    'seed_matchup':         0.02,
    'tourney_experience':   0.01,
    'neutral_court':        0.01,
    'single_elim_pressure': 0.01,
}

# Conferences that are "blue blood" — teams with deep tournament experience
BLUE_BLOODS = {
    'Kansas', 'Duke', 'North Carolina', 'Kentucky', 'UCLA', 'Indiana',
    'UConn', 'Louisville', 'Michigan State', 'Villanova', 'Gonzaga',
}


class NCAABEngine:
    """
    30-factor NCAAB prediction engine.
    Outputs match NBA engine format for seamless UI integration.
    """

    def __init__(self, tournament_mode: bool = False):
        self.fetcher = NCAABDataFetcher()
        self.weights = dict(DEFAULT_WEIGHTS)
        self.tournament_mode = tournament_mode
        self._init_db()

        # In tournament mode, boost tournament factors
        if tournament_mode:
            self.weights['seed_matchup'] = 0.05
            self.weights['tourney_experience'] = 0.03
            self.weights['neutral_court'] = 0.03
            self.weights['single_elim_pressure'] = 0.02
            self.weights['home_court'] = 0.01  # most tourney games are neutral
            # Re-normalize
            total = sum(self.weights.values())
            self.weights = {k: v / total for k, v in self.weights.items()}

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

    # ─── Main Prediction Pipeline ───────────────────────────────

    def predict_games(self, target_date: Optional[date] = None,
                      seeds: Optional[Dict[str, int]] = None) -> List[Dict]:
        """
        Run full prediction pipeline for a date.
        seeds: optional dict of {team_name: seed_number} for tournament mode.
        Returns list of predictions in standard ParlayGuarantee format.
        """
        target = target_date or date.today()
        logger.info(f"NCAAB Engine: predicting games for {target}")

        # 1. Fetch games — try consensus (DK+FD+OddsAPI) first, fall back to Odds API only
        try:
            from consensus_fetcher import fetch_consensus_games
            games = fetch_consensus_games(target_date=target, sport="ncaab", use_playwright=True)
            if games:
                logger.info(f"Using CONSENSUS data: {len(games)} games from multiple books")
            else:
                raise ValueError("Consensus returned 0 games")
        except Exception as e:
            logger.warning(f"Consensus fetch failed ({e}), falling back to Odds API")
            games = self.fetcher.fetch_games_from_odds(target)

        if not games:
            logger.warning("No NCAAB games found for this date")
            return []

        logger.info(f"Found {len(games)} NCAAB games")

        # 2. Fetch rankings
        rankings = self.fetcher.fetch_espn_rankings()
        rank_map = {r['team'].lower(): r['rank'] for r in rankings}

        # 3. Analyze each game
        predictions = []
        for game in games:
            try:
                pred = self._analyze_game(game, rank_map, seeds)
                if pred:
                    predictions.append(pred)
                    self._store_prediction(pred)
            except Exception as e:
                logger.error(f"Error analyzing {game['away_team']} @ {game['home_team']}: {e}")

        # 4. Sort by confidence
        predictions.sort(key=lambda x: x['confidence'], reverse=True)

        # 5. Assign upset composite
        for pred in predictions:
            pred['upset_composite'] = self._compute_upset_composite(pred)

        logger.info(f"Generated {len(predictions)} predictions")
        return predictions

    def _analyze_game(self, game: Dict, rank_map: Dict,
                      seeds: Optional[Dict] = None) -> Optional[Dict]:
        """Analyze a single game across all 30 factors."""
        home = game['home_team']
        away = game['away_team']

        # Fetch team stats
        home_stats = self.fetcher.fetch_espn_team_stats(home)
        away_stats = self.fetcher.fetch_espn_team_stats(away)

        # Use defaults if stats unavailable
        if not home_stats:
            home_stats = self._default_stats(home)
        if not away_stats:
            away_stats = self._default_stats(away)

        factors = {}
        home_score = 0.0
        away_score = 0.0

        # ── Factor 1: NET/AP Ranking ──
        home_rank = rank_map.get(home.lower(), 150)
        away_rank = rank_map.get(away.lower(), 150)
        # Lower rank = better. Normalize to 0-1 advantage
        rank_diff = (away_rank - home_rank) / 300  # positive = home better
        rank_diff = max(-1, min(1, rank_diff))
        factors['net_ranking'] = rank_diff
        home_score += max(0, rank_diff) * self.weights['net_ranking']
        away_score += max(0, -rank_diff) * self.weights['net_ranking']

        # ── Factor 2: Win Percentage ──
        home_wp = home_stats['wins'] / max(home_stats['wins'] + home_stats['losses'], 1)
        away_wp = away_stats['wins'] / max(away_stats['wins'] + away_stats['losses'], 1)
        wp_diff = home_wp - away_wp
        factors['win_pct'] = wp_diff
        home_score += max(0, wp_diff) * self.weights['win_pct']
        away_score += max(0, -wp_diff) * self.weights['win_pct']

        # ── Factor 3: Conference Strength ──
        home_conf = self.fetcher.get_conference_strength(home_stats.get('conference', ''))
        away_conf = self.fetcher.get_conference_strength(away_stats.get('conference', ''))
        conf_diff = home_conf - away_conf
        factors['conf_strength'] = conf_diff
        home_score += max(0, conf_diff) * self.weights['conf_strength']
        away_score += max(0, -conf_diff) * self.weights['conf_strength']

        # ── Factor 4-5: Offensive & Defensive Efficiency ──
        off_diff = home_stats['off_efficiency'] - away_stats['off_efficiency']
        def_diff = away_stats['def_efficiency'] - home_stats['def_efficiency']  # lower def_eff = better
        factors['off_efficiency'] = off_diff / 20  # normalize
        factors['def_efficiency'] = def_diff / 20
        home_score += max(0, off_diff / 20) * self.weights['off_efficiency']
        away_score += max(0, -off_diff / 20) * self.weights['off_efficiency']
        home_score += max(0, def_diff / 20) * self.weights['def_efficiency']
        away_score += max(0, -def_diff / 20) * self.weights['def_efficiency']

        # ── Factor 6: Strength of Schedule ──
        home_sos = home_stats.get('sos', 0.5)
        away_sos = away_stats.get('sos', 0.5)
        # Team with harder SOS + good record = more impressive
        home_adj_sos = home_sos * home_wp
        away_adj_sos = away_sos * away_wp
        sos_diff = home_adj_sos - away_adj_sos
        factors['sos'] = sos_diff
        home_score += max(0, sos_diff) * self.weights['sos']
        away_score += max(0, -sos_diff) * self.weights['sos']

        # ── Factors 7-11: Shooting & Ball Control ──
        for stat_key, weight_key in [
            ('fg_pct', 'fg_pct'), ('three_pct', 'three_pct'),
            ('ft_pct', 'ft_pct'), ('assists', 'assists')
        ]:
            h_val = home_stats.get(stat_key, 0)
            a_val = away_stats.get(stat_key, 0)
            diff = (h_val - a_val) / max(abs(h_val) + abs(a_val), 0.01)
            factors[weight_key] = diff
            home_score += max(0, diff) * self.weights[weight_key]
            away_score += max(0, -diff) * self.weights[weight_key]

        # Turnovers (lower = better)
        h_to = home_stats.get('turnovers', 13)
        a_to = away_stats.get('turnovers', 13)
        to_diff = (a_to - h_to) / 10  # positive = home better
        factors['turnovers'] = to_diff
        home_score += max(0, to_diff) * self.weights['turnovers']
        away_score += max(0, -to_diff) * self.weights['turnovers']

        # ── Factors 12-13: Tempo & Rebounding ──
        h_reb = home_stats.get('rebounds', 35)
        a_reb = away_stats.get('rebounds', 35)
        reb_diff = (h_reb - a_reb) / 15
        factors['rebounding'] = reb_diff
        home_score += max(0, reb_diff) * self.weights['rebounding']
        away_score += max(0, -reb_diff) * self.weights['rebounding']

        h_tempo = home_stats.get('tempo', 67)
        a_tempo = away_stats.get('tempo', 67)
        factors['tempo'] = (h_tempo - a_tempo) / 20
        # Tempo is neutral — doesn't directly favor either team
        # But faster team at home with crowd = slight edge
        if h_tempo > a_tempo:
            home_score += 0.005 * self.weights['tempo']
        else:
            away_score += 0.005 * self.weights['tempo']

        # ── Factors 14-16: Form & Momentum ──
        # Use ATS trends as proxy for recent form
        home_ats = self.fetcher.get_ats_trends(home)
        away_ats = self.fetcher.get_ats_trends(away)
        form_diff = home_ats['ats_pct'] - away_ats['ats_pct']
        factors['last10_record'] = form_diff
        home_score += max(0, form_diff) * self.weights['last10_record']
        away_score += max(0, -form_diff) * self.weights['last10_record']

        factors['streak'] = 0  # TODO: fetch from schedule
        factors['momentum_trend'] = 0

        # ── Factors 17-21: Situational ──
        # Home court (huge in college — worth 3-4 points)
        if not self.tournament_mode:
            factors['home_court'] = 0.65  # home wins ~65% in CBB
            home_score += 0.65 * self.weights['home_court']
        else:
            factors['home_court'] = 0.0  # neutral court in tourney

        factors['rest_days'] = 0  # TODO
        factors['travel'] = 0
        factors['rivalry'] = 0
        factors['time_of_season'] = self._time_of_season_factor()

        # ── Factors 22-24: Market Signals ──
        home_imp = game.get('home_implied_prob', 0.5)
        away_imp = game.get('away_implied_prob', 0.5)
        # Remove vig
        total_imp = home_imp + away_imp
        if total_imp > 0:
            home_imp /= total_imp
            away_imp /= total_imp

        factors['implied_prob'] = home_imp - away_imp
        home_score += max(0, home_imp - 0.5) * self.weights['implied_prob']
        away_score += max(0, away_imp - 0.5) * self.weights['implied_prob']

        spread = game.get('spread')
        if spread is not None:
            # Negative spread = home favored
            spread_signal = -spread / 20  # normalize, positive = home favored
            factors['spread_signal'] = spread_signal
            home_score += max(0, spread_signal) * self.weights['spread_signal']
            away_score += max(0, -spread_signal) * self.weights['spread_signal']

            # Line value: our model vs market
            model_edge = (home_score - away_score)
            market_lean = spread_signal
            factors['line_value'] = model_edge - market_lean
        else:
            factors['spread_signal'] = 0
            factors['line_value'] = 0

        # ── Factors 25-28: Tournament-Specific ──
        if self.tournament_mode and seeds:
            home_seed = seeds.get(home, 16)
            away_seed = seeds.get(away, 16)
            upset_rate = self.fetcher.get_seed_upset_rate(
                min(home_seed, away_seed), max(home_seed, away_seed))

            # Seed matchup: lower seed (better) gets bonus
            if home_seed < away_seed:
                seed_adv = (1 - upset_rate) * 0.5
                factors['seed_matchup'] = seed_adv
                home_score += seed_adv * self.weights['seed_matchup']
            else:
                seed_adv = (1 - upset_rate) * 0.5
                factors['seed_matchup'] = -seed_adv
                away_score += seed_adv * self.weights['seed_matchup']

            # Tournament experience
            home_exp = 1.0 if home in BLUE_BLOODS else 0.3
            away_exp = 1.0 if away in BLUE_BLOODS else 0.3
            exp_diff = home_exp - away_exp
            factors['tourney_experience'] = exp_diff
            home_score += max(0, exp_diff) * self.weights['tourney_experience']
            away_score += max(0, -exp_diff) * self.weights['tourney_experience']

            factors['neutral_court'] = 0  # already handled by zeroing home_court
            factors['single_elim_pressure'] = 0  # slight edge to experienced teams
        else:
            factors['seed_matchup'] = 0
            factors['tourney_experience'] = 0
            factors['neutral_court'] = 0
            factors['single_elim_pressure'] = 0

        # ─── Compute Final Prediction ───────────────────────────

        total_score = home_score + away_score
        if total_score == 0:
            home_prob = 0.5
        else:
            home_prob = home_score / total_score

        # Apply Log5 blend with market implied probability
        if home_imp > 0 and away_imp > 0:
            model_weight = 0.55  # trust our model slightly more
            market_weight = 0.45
            blended_home = model_weight * home_prob + market_weight * home_imp
        else:
            blended_home = home_prob

        # Clamp
        blended_home = max(0.15, min(0.85, blended_home))
        blended_away = 1 - blended_home

        predicted_winner = home if blended_home >= 0.5 else away
        confidence = max(blended_home, blended_away)

        # Spread pick
        spread_pick = None
        spread_confidence = 0
        if spread is not None:
            # Our predicted margin
            pred_margin = (blended_home - 0.5) * 20  # rough conversion to points
            # Spread is from home perspective (negative = home favored)
            cover_margin = pred_margin + spread  # positive = home covers
            if cover_margin > 0:
                spread_pick = f"{home} {spread:+.1f}"
                spread_confidence = min(0.85, 0.5 + abs(cover_margin) / 20)
            else:
                spread_pick = f"{away} {-spread:+.1f}"
                spread_confidence = min(0.85, 0.5 + abs(cover_margin) / 20)

        # Over/Under
        ou_pick = None
        total = game.get('total')
        if total and h_tempo and a_tempo:
            # Estimate total based on tempo and efficiency
            avg_tempo = (h_tempo + a_tempo) / 2
            est_total = (home_stats['off_efficiency'] + away_stats['off_efficiency']) / 100 * avg_tempo
            if est_total > total + 2:
                ou_pick = f"Over {total}"
            elif est_total < total - 2:
                ou_pick = f"Under {total}"

        return {
            # Standard ParlayGuarantee format
            'game_id': game.get('game_id', ''),
            'game_date': game.get('game_date', ''),
            'game_time': game.get('game_time', ''),
            'sport': 'NCAAB',
            'home_team': home,
            'away_team': away,
            'predicted_winner': predicted_winner,
            'confidence': round(confidence, 4),
            'win_probability': round(blended_home if predicted_winner == home else blended_away, 4),
            'spread_pick': spread_pick,
            'spread_confidence': round(spread_confidence, 4),
            'ou_pick': ou_pick,
            'spread': spread,
            'total': total,
            'home_odds': game.get('home_odds'),
            'away_odds': game.get('away_odds'),
            'home_win_prob': round(blended_home, 4),
            'away_win_prob': round(blended_away, 4),
            'market_home_prob': round(home_imp, 4),
            'market_away_prob': round(away_imp, 4),
            'upset_composite': 0,  # computed after all games
            'factors': factors,
            'home_rank': home_rank,
            'away_rank': away_rank,
            'home_record': f"{home_stats['wins']}-{home_stats['losses']}",
            'away_record': f"{away_stats['wins']}-{away_stats['losses']}",
            'home_conference': home_stats.get('conference', ''),
            'away_conference': away_stats.get('conference', ''),
            'available_books': game.get('available_books', []),
        }

    def _default_stats(self, team_name: str) -> Dict:
        """Return default stats for unknown teams."""
        return {
            'team_name': team_name, 'season': '2025-26',
            'wins': 10, 'losses': 10,
            'off_efficiency': 100, 'def_efficiency': 100, 'tempo': 67,
            'fg_pct': 0.44, 'three_pct': 0.33, 'ft_pct': 0.70,
            'rebounds': 35, 'turnovers': 13, 'assists': 13,
            'sos': 0.5, 'conference': '', 'net_ranking': 150,
            'ppg': 70, 'opp_ppg': 70,
        }

    def _time_of_season_factor(self) -> float:
        """Late season games matter more — teams are more defined."""
        today = date.today()
        # CBB season: Nov 1 - April 10
        season_start = date(today.year if today.month >= 9 else today.year - 1, 11, 1)
        days_in = (today - season_start).days
        return min(1.0, days_in / 160)  # 1.0 by late March

    def _compute_upset_composite(self, pred: Dict) -> float:
        """
        Separate upset detection score.
        High value = model sees upset potential despite market favoring the other side.
        CRITICAL: Only non-zero when model picks the UNDERDOG (disagrees with market direction).
        If model picks the favorite, composite = 0 — that's not an upset.
        """
        factors = pred.get('factors', {})
        home_prob = pred.get('home_win_prob', 0.5)
        market_home = pred.get('market_home_prob', 0.5)

        # Determine if model picks the dog
        model_picks_home = home_prob > 0.5
        market_favors_home = market_home > 0.5

        # If model agrees with market on who wins, this is NOT an upset
        if model_picks_home == market_favors_home:
            return 0.0

        # Model disagrees with market — this IS an upset pick
        disagree = abs(home_prob - market_home)

        # Conference mismatch (mid-major vs power = upset territory)
        conf_mismatch = abs(factors.get('conf_strength', 0))

        # Recent form divergence
        form_diff = abs(factors.get('last10_record', 0))

        # High line value = market is wrong
        line_value = abs(factors.get('line_value', 0))

        composite = (disagree * 0.35 + conf_mismatch * 0.20 +
                     form_diff * 0.20 + line_value * 0.25)

        return round(min(1.0, composite * 3), 3)  # scale to 0-1

    def _store_prediction(self, pred: Dict):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO predictions
                (game_id, game_date, home_team, away_team,
                 predicted_winner, confidence, spread_pick, spread_confidence,
                 ou_pick, total, factors_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pred['game_id'], pred['game_date'],
                pred['home_team'], pred['away_team'],
                pred['predicted_winner'], pred['confidence'],
                pred.get('spread_pick'), pred.get('spread_confidence'),
                pred.get('ou_pick'), pred.get('total'),
                json.dumps(pred.get('factors', {})),
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store prediction: {e}")

    # ─── Self-Learning ──────────────────────────────────────────

    def score_results(self, results: List[Dict]):
        """
        Score past predictions against actual results.
        results: [{game_id, actual_winner, home_score, away_score}]
        """
        conn = sqlite3.connect(DB_PATH)
        correct, total = 0, 0
        for r in results:
            row = conn.execute(
                "SELECT predicted_winner FROM predictions WHERE game_id = ?",
                (r['game_id'],)
            ).fetchone()
            if row:
                is_correct = 1 if row[0] == r['actual_winner'] else 0
                conn.execute(
                    "UPDATE predictions SET actual_winner = ?, correct = ? WHERE game_id = ?",
                    (r['actual_winner'], is_correct, r['game_id'])
                )
                correct += is_correct
                total += 1
        conn.commit()
        conn.close()

        if total > 0:
            accuracy = correct / total
            logger.info(f"NCAAB Results: {correct}/{total} = {accuracy:.1%}")
            # Store weight snapshot
            self._save_weight_history(accuracy, total)
        return {'correct': correct, 'total': total}

    def _save_weight_history(self, accuracy: float, sample_size: int):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO weight_history (date, weights_json, accuracy, sample_size) VALUES (?, ?, ?, ?)",
            (date.today().isoformat(), json.dumps(self.weights), accuracy, sample_size)
        )
        conn.commit()
        conn.close()

    def get_accuracy_stats(self) -> Dict:
        """Get historical prediction accuracy."""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT correct, COUNT(*) FROM predictions WHERE correct IS NOT NULL GROUP BY correct"
        ).fetchall()
        conn.close()
        stats = {str(r[0]): r[1] for r in rows}
        correct = stats.get('1', 0)
        wrong = stats.get('0', 0)
        total = correct + wrong
        return {
            'correct': correct, 'wrong': wrong, 'total': total,
            'accuracy': correct / total if total > 0 else 0,
        }


def run_predictions(target_date: Optional[str] = None, tournament: bool = False,
                    seeds_file: Optional[str] = None, output_file: Optional[str] = None):
    """CLI entry point."""
    engine = NCAABEngine(tournament_mode=tournament)

    td = date.fromisoformat(target_date) if target_date else date.today()

    seeds = None
    if seeds_file and os.path.exists(seeds_file):
        with open(seeds_file) as f:
            seeds = json.load(f)

    predictions = engine.predict_games(td, seeds)

    if not predictions:
        print("No games found.")
        return

    # Print summary
    print(f"\n{'='*70}")
    print(f"  NCAAB PREDICTIONS — {td.strftime('%A %B %d, %Y')}")
    print(f"  {'MARCH MADNESS MODE' if tournament else 'Regular Season'}")
    print(f"{'='*70}\n")

    for i, p in enumerate(predictions, 1):
        winner = p['predicted_winner']
        loser = p['away_team'] if winner == p['home_team'] else p['home_team']
        conf = p['confidence']
        upset = p['upset_composite']

        conf_bar = '█' * int(conf * 20) + '░' * (20 - int(conf * 20))
        upset_flag = ' 🔥 UPSET ALERT' if upset > 0.5 else ''

        print(f"  {i:2d}. {winner} over {loser}")
        print(f"      Confidence: [{conf_bar}] {conf:.1%}{upset_flag}")
        if p.get('spread_pick'):
            print(f"      Spread: {p['spread_pick']} ({p['spread_confidence']:.1%})")
        if p.get('ou_pick'):
            print(f"      O/U: {p['ou_pick']}")
        print(f"      {p['home_team']} ({p['home_record']}) vs {p['away_team']} ({p['away_record']})")
        print()

    # Save output
    out = output_file or f"ncaab_picks_{td.isoformat()}.json"
    # Convert for JSON (remove factors for clean output)
    clean = []
    for p in predictions:
        pc = dict(p)
        pc.pop('factors', None)
        clean.append(pc)

    with open(os.path.join(os.path.dirname(__file__), out), 'w') as f:
        json.dump(clean, f, indent=2)
    print(f"Saved {len(predictions)} predictions to {out}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='NCAAB Prediction Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--tournament', action='store_true', help='March Madness mode')
    parser.add_argument('--seeds', type=str, help='Path to seeds JSON file')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_predictions(args.date, args.tournament, args.seeds, args.output)
