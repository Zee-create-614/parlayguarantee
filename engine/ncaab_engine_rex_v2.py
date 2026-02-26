"""
ParlayGuarantee NCAAB Challenger Engine — "REX" V2
====================================================
Major upgrade from Rex V1. Same base NCAABEngine inheritance, but adds
15 new advanced factors scraped from multiple sources.

Rex V1: OG engine + confidence floors (spread ≥55%, ML ≥58%)
Rex V2: OG engine + 15 advanced factors + reweighted composite + confidence floors

NEW FACTORS:
  1. Net Rating (ORtg/DRtg/NetRtg) from barttorvik
  2. Rest days / schedule density
  3. ATS trends (season, home/away, L10, conference)
  4. Player-level impact (top scorer, injuries)
  5. Travel/fatigue (distance + timezone)
  6. Referee tendencies (placeholder — data sparse for NCAAB)
  7. Pace matchup modeling
  8. Public betting %
  9. Motivation factors (bubble teams, conference seeding)
  10. Strength of schedule (advanced)
  11. Coaching experience
  12. Home court advantage magnitude (venue-specific)
  13. Conference vs non-conference performance
  14. Free throw shooting (FT% + FTA rate)
  15. Turnover differential (margin + context)

FROZEN: Do not modify Rex V1 or OG engine. This runs alongside both.
"""

import sys
import json
import logging
import os
from datetime import date, timedelta
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from adaptive_learner import AdaptiveLearner
from ncaab_engine import NCAABEngine, DEFAULT_WEIGHTS
from ncaab_advanced_stats import (
    fetch_barttorvik_stats,
    fetch_ats_trends,
    fetch_top_players,
    fetch_recent_schedule,
    compute_rest_and_density,
    get_travel_distance,
    fetch_public_betting,
    get_home_court_multiplier,
    get_coaching_score,
    is_rivalry,
    compute_motivation_score,
    compute_conf_vs_nonconf,
    normalize_to_edge,
    NCAAB_TEAM_LOCATIONS,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('ncaab_engine_rex_v2.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ─── Rex V2 Configuration ───────────────────────────────────
ENGINE_NAME = "Rex"
ENGINE_VERSION = "2.0"

SPREAD_CONFIDENCE_FLOOR = 0.62
ML_CONFIDENCE_FLOOR = 0.60

# ─── V2 Factor Weights (all 15 new + OG base → sum to 1.0) ──

V2_WEIGHTS = {
    # === OG Base Factors (reduced to make room, ~45%) ===
    'net_ranking':          0.04,
    'win_pct':              0.03,
    'conf_strength':        0.03,
    'off_efficiency':       0.04,
    'def_efficiency':       0.04,
    'sos_base':             0.02,
    'fg_pct':               0.02,
    'three_pct':            0.02,
    'ft_pct_base':          0.01,
    'turnovers_base':       0.01,
    'assists':              0.01,
    'tempo_base':           0.02,
    'rebounding':           0.02,
    'last10_record':        0.03,
    'streak':               0.01,
    'momentum_trend':       0.01,
    'home_court_base':      0.03,
    'rest_days_base':       0.02,
    'implied_prob':         0.04,
    'spread_signal':        0.02,
    'line_value':           0.02,

    # === NEW Rex V2 Factors (~55%) ===
    # 1. Advanced efficiency (barttorvik)
    'adv_net_rating':       0.06,
    'adv_barthag':          0.04,
    # 2. Rest / schedule density
    'schedule_density':     0.03,
    # 3. ATS trends
    'ats_season':           0.03,
    'ats_situational':      0.01,
    # 4. Player impact
    'player_impact':        0.04,
    # 5. Travel fatigue
    'travel_fatigue':       0.03,
    # 6. Referee tendencies (placeholder)
    'ref_tendency':         0.00,  # no reliable data yet
    # 7. Pace matchup
    'pace_matchup':         0.03,
    # 8. Public betting contrarian
    'public_fade':          0.02,
    # 9. Motivation
    'motivation':           0.03,
    # 10. Advanced SOS
    'adv_sos':              0.03,
    # 11. Coaching
    'coaching':             0.03,
    # 12. Home court magnitude
    'home_court_magnitude': 0.03,
    # 13. Conference vs non-conference
    'conf_vs_nonconf':      0.03,
    # 14. Free throw shooting
    'ft_clutch':            0.03,
    # 15. Turnover differential
    'turnover_diff':        0.01,
    # 16. Line movement
    'line_movement':        0.03,
}

# Verify weights sum to ~1.0
_weight_sum = sum(V2_WEIGHTS.values())
assert 0.98 <= _weight_sum <= 1.02, f"V2 weights sum to {_weight_sum}, expected ~1.0"


class NCAABEngineRexV2(NCAABEngine):
    """
    Rex V2: Full 45-factor NCAAB engine.
    Inherits OG base pipeline for game fetching, then completely overrides
    the analysis with advanced factor scoring.
    """

    def __init__(self, tournament_mode: bool = False):
        super().__init__(tournament_mode=tournament_mode)
        self.engine_name = ENGINE_NAME
        self.engine_version = ENGINE_VERSION
        # ─── Adaptive Learning: Load learned weights if available ───
        self.learner = AdaptiveLearner("rex")
        self.v2_weights = self.learner.get_weights(V2_WEIGHTS)
        logger.info(f"Rex V2 using weights (learned={self.learner.weights_file.exists()}): "
                    f"top 5 = {sorted(self.v2_weights.items(), key=lambda x: -x[1])[:5]}")
        self._barttorvik_data: Optional[Dict] = None

    def _load_barttorvik(self):
        """Lazy-load barttorvik data once per run."""
        if self._barttorvik_data is None:
            self._barttorvik_data = fetch_barttorvik_stats()
            logger.info(f"Loaded barttorvik data for {len(self._barttorvik_data)} teams")

    def predict_games(self, target_date: Optional[date] = None,
                      seeds: Optional[Dict[str, int]] = None) -> List[Dict]:
        """Run full V2 pipeline: OG fetch + V2 analysis + Rex filters."""
        target = target_date or date.today()
        logger.info(f"Rex V2 Engine: predicting for {target}")

        # Pre-load barttorvik data
        self._load_barttorvik()

        # Get base predictions from OG engine
        base_predictions = super().predict_games(target, seeds)

        if not base_predictions:
            return []

        # Re-analyze each game with V2 factors
        v2_predictions = []
        for pred in base_predictions:
            try:
                v2_pred = self._v2_analyze(pred, target, seeds)
                v2_predictions.append(v2_pred)
            except Exception as e:
                logger.error(f"V2 analysis failed for {pred['away_team']} @ {pred['home_team']}: {e}")
                # Fall back to OG prediction
                pred['engine'] = ENGINE_NAME
                pred['engine_version'] = ENGINE_VERSION
                pred['v2_factors'] = {}
                v2_predictions.append(pred)

        # Apply Rex confidence filters (same as V1)
        filtered = self._apply_rex_filters(v2_predictions)

        # Sort by confidence
        filtered.sort(key=lambda x: (
            x.get('spread_status') == 'PICK',
            x.get('spread_confidence', 0)
        ), reverse=True)

        logger.info(f"Rex V2: {len(filtered)} predictions generated")
        return filtered

    def _v2_analyze(self, pred: Dict, target: date,
                    seeds: Optional[Dict] = None) -> Dict:
        """
        Re-score a game with all V2 factors.
        Takes OG prediction as base, adds advanced factor scores,
        then recomputes composite probability.
        """
        home = pred['home_team']
        away = pred['away_team']
        og_factors = pred.get('factors', {})

        v2_factors = {}
        home_score = 0.0
        away_score = 0.0

        # ━━━ OG BASE FACTORS (pulled from existing analysis) ━━━

        og_mappings = {
            'net_ranking': 'net_ranking',
            'win_pct': 'win_pct',
            'conf_strength': 'conf_strength',
            'off_efficiency': 'off_efficiency',
            'def_efficiency': 'def_efficiency',
            'fg_pct': 'fg_pct',
            'three_pct': 'three_pct',
            'assists': 'assists',
            'rebounding': 'rebounding',
            'last10_record': 'last10_record',
            'streak': 'streak',
            'momentum_trend': 'momentum_trend',
            'implied_prob': 'implied_prob',
            'spread_signal': 'spread_signal',
            'line_value': 'line_value',
        }

        for v2_key, og_key in og_mappings.items():
            val = og_factors.get(og_key, 0)
            v2_factors[v2_key] = val
            # positive val = home advantage
            w = self.v2_weights.get(v2_key, 0)
            home_score += max(0, val) * w
            away_score += max(0, -val) * w

        # OG factors that map with different keys
        v2_factors['sos_base'] = og_factors.get('sos', 0)
        w = self.v2_weights['sos_base']
        home_score += max(0, v2_factors['sos_base']) * w
        away_score += max(0, -v2_factors['sos_base']) * w

        v2_factors['ft_pct_base'] = og_factors.get('ft_pct', 0)
        w = self.v2_weights['ft_pct_base']
        home_score += max(0, v2_factors['ft_pct_base']) * w
        away_score += max(0, -v2_factors['ft_pct_base']) * w

        v2_factors['turnovers_base'] = og_factors.get('turnovers', 0)
        w = self.v2_weights['turnovers_base']
        home_score += max(0, v2_factors['turnovers_base']) * w
        away_score += max(0, -v2_factors['turnovers_base']) * w

        v2_factors['tempo_base'] = og_factors.get('tempo', 0)
        w = self.v2_weights['tempo_base']
        home_score += max(0, v2_factors['tempo_base']) * w
        away_score += max(0, -v2_factors['tempo_base']) * w

        v2_factors['home_court_base'] = og_factors.get('home_court', 0)
        w = self.v2_weights['home_court_base']
        home_score += max(0, v2_factors['home_court_base']) * w

        v2_factors['rest_days_base'] = og_factors.get('rest_days', 0)
        w = self.v2_weights['rest_days_base']
        home_score += max(0, v2_factors['rest_days_base']) * w
        away_score += max(0, -v2_factors['rest_days_base']) * w

        # ━━━ NEW V2 FACTORS ━━━

        # --- 1. Advanced Net Rating (Barttorvik) ---
        bart = self._barttorvik_data or {}
        h_bart = self._find_bart(home, bart)
        a_bart = self._find_bart(away, bart)

        net_rtg_edge = normalize_to_edge(
            h_bart.get('net_rtg', 0), a_bart.get('net_rtg', 0), scale=20.0)
        v2_factors['adv_net_rating'] = net_rtg_edge - 0.5  # center on 0
        w = self.v2_weights['adv_net_rating']
        home_score += max(0, v2_factors['adv_net_rating']) * w
        away_score += max(0, -v2_factors['adv_net_rating']) * w

        barthag_edge = normalize_to_edge(
            h_bart.get('barthag', 0.5), a_bart.get('barthag', 0.5), scale=0.5)
        v2_factors['adv_barthag'] = barthag_edge - 0.5
        w = self.v2_weights['adv_barthag']
        home_score += max(0, v2_factors['adv_barthag']) * w
        away_score += max(0, -v2_factors['adv_barthag']) * w

        # --- 2. Rest / Schedule Density ---
        h_sched = fetch_recent_schedule(home)
        a_sched = fetch_recent_schedule(away)
        h_rest = compute_rest_and_density(h_sched, target)
        a_rest = compute_rest_and_density(a_sched, target)

        # More rest = better. B2B = bad. High density = bad.
        rest_edge = 0.0
        if h_rest['rest_days'] > a_rest['rest_days']:
            rest_edge = min(0.5, (h_rest['rest_days'] - a_rest['rest_days']) / 5)
        elif a_rest['rest_days'] > h_rest['rest_days']:
            rest_edge = -min(0.5, (a_rest['rest_days'] - h_rest['rest_days']) / 5)

        # Penalize heavy schedule
        density_penalty_h = max(0, h_rest['games_in_7'] - 2) * 0.1
        density_penalty_a = max(0, a_rest['games_in_7'] - 2) * 0.1
        rest_edge += (density_penalty_a - density_penalty_h)

        if h_rest['b2b'] and not a_rest['b2b']:
            rest_edge -= 0.2
        elif a_rest['b2b'] and not h_rest['b2b']:
            rest_edge += 0.2

        v2_factors['schedule_density'] = max(-1, min(1, rest_edge))
        w = self.v2_weights['schedule_density']
        home_score += max(0, v2_factors['schedule_density']) * w
        away_score += max(0, -v2_factors['schedule_density']) * w

        # --- 3. ATS Trends ---
        h_ats = fetch_ats_trends(home)
        a_ats = fetch_ats_trends(away)

        season_ats_edge = h_ats['season_ats'] - a_ats['season_ats']
        v2_factors['ats_season'] = season_ats_edge
        w = self.v2_weights['ats_season']
        home_score += max(0, season_ats_edge) * w
        away_score += max(0, -season_ats_edge) * w

        # Situational ATS: home team's home_ats vs away team's away_ats
        sit_ats_edge = h_ats.get('home_ats', 0.5) - a_ats.get('away_ats', 0.5)
        v2_factors['ats_situational'] = sit_ats_edge
        w = self.v2_weights['ats_situational']
        home_score += max(0, sit_ats_edge) * w
        away_score += max(0, -sit_ats_edge) * w

        # --- 4. Player Impact ---
        h_players = fetch_top_players(home)
        a_players = fetch_top_players(away)

        # Compare top scorer PPG as proxy for star power
        h_top_ppg = h_players[0]['ppg'] if h_players else 12.0
        a_top_ppg = a_players[0]['ppg'] if a_players else 12.0
        # Also consider depth: sum of top 3 vs top 3
        h_top3 = sum(p['ppg'] for p in h_players[:3]) if len(h_players) >= 3 else h_top_ppg * 2.5
        a_top3 = sum(p['ppg'] for p in a_players[:3]) if len(a_players) >= 3 else a_top_ppg * 2.5

        player_edge = normalize_to_edge(h_top3, a_top3, scale=30.0) - 0.5
        v2_factors['player_impact'] = player_edge
        w = self.v2_weights['player_impact']
        home_score += max(0, player_edge) * w
        away_score += max(0, -player_edge) * w

        # --- 5. Travel Fatigue ---
        # Away team travels to home team's location
        travel_dist = get_travel_distance(away, home)
        # Normalize: >1000 miles = significant, >2000 = major
        travel_penalty = 0.0
        if travel_dist > 500:
            travel_penalty = min(0.5, (travel_dist - 500) / 3000)

        v2_factors['travel_fatigue'] = travel_penalty  # positive = home advantage
        w = self.v2_weights['travel_fatigue']
        home_score += travel_penalty * w

        # --- 6. Referee Tendencies ---
        # Placeholder: no reliable free NCAAB ref data
        v2_factors['ref_tendency'] = 0.0

        # --- 7. Pace Matchup ---
        h_tempo = h_bart.get('tempo', 67.0)
        a_tempo = a_bart.get('tempo', 67.0)
        tempo_diff = abs(h_tempo - a_tempo)

        # If home team is faster and at home (crowd energy), slight edge
        pace_edge = 0.0
        if h_tempo > a_tempo and not self.tournament_mode:
            pace_edge = min(0.3, tempo_diff / 20)
        elif a_tempo > h_tempo and not self.tournament_mode:
            pace_edge = -min(0.2, tempo_diff / 30)  # away tempo less impactful

        # If one team is much faster, the slower team may struggle to keep up
        if tempo_diff > 8:
            # Faster team with better offense has edge
            h_ortg = h_bart.get('ortg', 100)
            a_ortg = a_bart.get('ortg', 100)
            if h_tempo > a_tempo and h_ortg > a_ortg:
                pace_edge += 0.1
            elif a_tempo > h_tempo and a_ortg > h_ortg:
                pace_edge -= 0.1

        v2_factors['pace_matchup'] = max(-0.5, min(0.5, pace_edge))
        w = self.v2_weights['pace_matchup']
        home_score += max(0, v2_factors['pace_matchup']) * w
        away_score += max(0, -v2_factors['pace_matchup']) * w

        # --- 8. Public Betting Contrarian ---
        pub = fetch_public_betting(home, away)
        # Fade the public: if public is heavy on one side, slight edge to other
        pub_diff = pub['home_pct'] - pub['away_pct']
        # If >65% public on one side, fade them slightly
        fade_edge = 0.0
        if pub['home_pct'] > 0.65:
            fade_edge = -0.1  # fade public home
        elif pub['away_pct'] > 0.65:
            fade_edge = 0.1  # fade public away
        v2_factors['public_fade'] = fade_edge
        w = self.v2_weights['public_fade']
        home_score += max(0, fade_edge) * w
        away_score += max(0, -fade_edge) * w

        # --- 9. Motivation ---
        home_rank = pred.get('home_rank', 150)
        away_rank = pred.get('away_rank', 150)
        home_conf = pred.get('home_conference', '')
        away_conf = pred.get('away_conference', '')

        # Parse records
        h_w, h_l = self._parse_record(pred.get('home_record', '10-10'))
        a_w, a_l = self._parse_record(pred.get('away_record', '10-10'))

        h_motiv = compute_motivation_score(home, home_rank, home_conf, h_w, h_l, target)
        a_motiv = compute_motivation_score(away, away_rank, away_conf, a_w, a_l, target)

        # Rivalry boost
        if is_rivalry(home, away):
            h_motiv = min(1.0, h_motiv + 0.15)
            a_motiv = min(1.0, a_motiv + 0.15)
            v2_factors['is_rivalry'] = True

        motiv_edge = h_motiv - a_motiv
        v2_factors['motivation'] = motiv_edge
        w = self.v2_weights['motivation']
        home_score += max(0, motiv_edge) * w
        away_score += max(0, -motiv_edge) * w

        # --- 10. Advanced SOS ---
        h_sos = h_bart.get('sos', 0.5)
        a_sos = a_bart.get('sos', 0.5)
        # Higher SOS + good record = more impressive
        h_wp = h_w / max(h_w + h_l, 1)
        a_wp = a_w / max(a_w + a_l, 1)
        h_adj_sos = h_sos * h_wp
        a_adj_sos = a_sos * a_wp
        sos_edge = h_adj_sos - a_adj_sos
        v2_factors['adv_sos'] = sos_edge
        w = self.v2_weights['adv_sos']
        home_score += max(0, sos_edge) * w
        away_score += max(0, -sos_edge) * w

        # --- 11. Coaching ---
        h_coach = get_coaching_score(home)
        a_coach = get_coaching_score(away)
        coach_edge = h_coach - a_coach
        v2_factors['coaching'] = coach_edge
        w = self.v2_weights['coaching']
        home_score += max(0, coach_edge) * w
        away_score += max(0, -coach_edge) * w

        # --- 12. Home Court Magnitude ---
        if not self.tournament_mode:
            hc_mult = get_home_court_multiplier(home)
            # Base home court is ~0.65 win rate. Multiply by venue factor.
            hc_edge = (0.65 * hc_mult) - 0.5  # positive = home advantage
            v2_factors['home_court_magnitude'] = hc_edge
            w = self.v2_weights['home_court_magnitude']
            home_score += max(0, hc_edge) * w
        else:
            v2_factors['home_court_magnitude'] = 0.0

        # --- 13. Conference vs Non-Conference ---
        h_split = compute_conf_vs_nonconf(h_sched, home_conf)
        a_split = compute_conf_vs_nonconf(a_sched, away_conf)
        # Positive split_score = consistent performer
        split_edge = h_split['split_score'] - a_split['split_score']
        v2_factors['conf_vs_nonconf'] = max(-0.5, min(0.5, split_edge))
        w = self.v2_weights['conf_vs_nonconf']
        home_score += max(0, v2_factors['conf_vs_nonconf']) * w
        away_score += max(0, -v2_factors['conf_vs_nonconf']) * w

        # --- 14. Free Throw Clutch ---
        h_ft = og_factors.get('ft_pct', 0)
        # Enhanced: also consider FT rate context (teams that get to the line more)
        h_ortg = h_bart.get('ortg', 100)
        a_ortg = a_bart.get('ortg', 100)
        # FT% matters more in close games — weight by how close the game might be
        spread = pred.get('spread')
        close_game_factor = 1.0
        if spread is not None:
            if abs(spread) < 5:
                close_game_factor = 1.5  # FT% matters more in close games
            elif abs(spread) > 12:
                close_game_factor = 0.5  # blowout, FT% less important

        ft_edge = h_ft * close_game_factor
        v2_factors['ft_clutch'] = ft_edge
        w = self.v2_weights['ft_clutch']
        home_score += max(0, ft_edge) * w
        away_score += max(0, -ft_edge) * w

        # --- 15. Turnover Differential ---
        to_base = og_factors.get('turnovers', 0)
        # Enhance: turnovers against good defensive teams matter more
        h_drtg = h_bart.get('drtg', 100)
        a_drtg = a_bart.get('drtg', 100)
        # If facing a top defense, TO risk is higher
        defense_context = 0.0
        if a_drtg < 95:  # elite defense opponent
            defense_context = -0.1  # home team may turn it over more
        if h_drtg < 95:
            defense_context += 0.1  # away team may turn it over more

        to_edge = to_base + defense_context
        v2_factors['turnover_diff'] = max(-0.5, min(0.5, to_edge))
        w = self.v2_weights['turnover_diff']
        home_score += max(0, v2_factors['turnover_diff']) * w
        away_score += max(0, -v2_factors['turnover_diff']) * w

        # --- 16. Line Movement ---
        lm_edge = 0.0
        try:
            from morning_line_movement import get_morning_line_signals
            lm_signals = get_morning_line_signals(target.isoformat())
            game_key = f"{away} @ {home}"
            lm = lm_signals.get(game_key, {})
            if lm:
                # movement_edge is home-perspective (>0.5 favors home)
                raw = lm.get('movement_edge', 0.5)
                lm_edge = (raw - 0.5)  # positive = home advantage
        except Exception:
            pass
        v2_factors['line_movement'] = max(-0.5, min(0.5, lm_edge))
        w = self.v2_weights['line_movement']
        home_score += max(0, v2_factors['line_movement']) * w
        away_score += max(0, -v2_factors['line_movement']) * w

        # ━━━ COMPUTE FINAL V2 PROBABILITY ━━━

        total_score = home_score + away_score
        if total_score == 0:
            v2_home_prob = 0.5
        else:
            v2_home_prob = home_score / total_score

        # Blend V2 model with market (55/45 split, same as OG)
        market_home = pred.get('market_home_prob', 0.5)
        market_away = pred.get('market_away_prob', 0.5)

        if market_home > 0 and market_away > 0:
            blended = 0.55 * v2_home_prob + 0.45 * market_home
        else:
            blended = v2_home_prob

        blended = max(0.15, min(0.85, blended))
        blended_away = 1 - blended

        predicted_winner = home if blended >= 0.5 else away
        confidence = max(blended, blended_away)

        # Recompute spread pick with V2 probability
        spread = pred.get('spread')
        spread_pick = None
        spread_confidence = 0
        if spread is not None:
            pred_margin = (blended - 0.5) * 20
            cover_margin = pred_margin + spread
            if cover_margin > 0:
                spread_pick = f"{home} {spread:+.1f}"
                spread_confidence = min(0.85, 0.5 + abs(cover_margin) / 20)
            else:
                spread_pick = f"{away} {-spread:+.1f}"
                spread_confidence = min(0.85, 0.5 + abs(cover_margin) / 20)

        # Update prediction with V2 results
        pred.update({
            'engine': ENGINE_NAME,
            'engine_version': ENGINE_VERSION,
            'predicted_winner': predicted_winner,
            'confidence': round(confidence, 4),
            'win_probability': round(blended if predicted_winner == home else blended_away, 4),
            'ml_pick': predicted_winner,
            'ml_confidence': round(confidence, 4),
            'home_win_prob': round(blended, 4),
            'away_win_prob': round(blended_away, 4),
            'spread_pick': spread_pick,
            'spread_confidence': round(spread_confidence, 4),
            'v2_model_home_prob': round(v2_home_prob, 4),
            'v2_factors': v2_factors,
            'v2_home_score': round(home_score, 4),
            'v2_away_score': round(away_score, 4),
            # factor_scores for adaptive learner (positive = favors pick side)
            'factor_scores': {k: round(v if predicted_winner == home else -v, 4) 
                              for k, v in v2_factors.items() if isinstance(v, (int, float))},
        })

        # Recompute upset composite
        pred['upset_composite'] = self._v2_upset_composite(pred)

        # Rex V2 focuses strictly on ML/spreads — no O/U
        pred['ou_pick'] = None

        return pred

    def _find_bart(self, team_name: str, bart_data: Dict) -> Dict:
        """Fuzzy match team to barttorvik data."""
        t = team_name.lower()
        if t in bart_data:
            return bart_data[t]
        for key, val in bart_data.items():
            if t in key or key in t:
                return val
        # Try partial words
        words = t.split()
        for key, val in bart_data.items():
            if any(w in key for w in words if len(w) > 3):
                return val
        return {'ortg': 100, 'drtg': 100, 'net_rtg': 0, 'tempo': 67,
                'barthag': 0.5, 'sos': 0.5}

    def _parse_record(self, record: str) -> tuple:
        try:
            parts = record.split('-')
            return int(parts[0]), int(parts[1])
        except Exception:
            return 10, 10

    def _v2_upset_composite(self, pred: Dict) -> float:
        """Enhanced upset detection using V2 factors."""
        home_prob = pred.get('home_win_prob', 0.5)
        market_home = pred.get('market_home_prob', 0.5)

        model_picks_home = home_prob > 0.5
        market_favors_home = market_home > 0.5

        if model_picks_home == market_favors_home:
            return 0.0

        v2 = pred.get('v2_factors', {})
        disagree = abs(home_prob - market_home)
        conf_mismatch = abs(v2.get('conf_vs_nonconf', 0))
        form_diff = abs(v2.get('ats_season', 0))
        line_value = abs(v2.get('line_value', 0))
        motiv = abs(v2.get('motivation', 0))
        coaching = abs(v2.get('coaching', 0))

        composite = (
            disagree * 0.25 +
            conf_mismatch * 0.10 +
            form_diff * 0.15 +
            line_value * 0.20 +
            motiv * 0.15 +
            coaching * 0.15
        )
        return round(min(1.0, composite * 3), 3)

    def _apply_rex_filters(self, predictions: List[Dict]) -> List[Dict]:
        """Apply Rex confidence floors (same logic as V1)."""
        picks, passes = 0, 0

        for pred in predictions:
            spread_conf = pred.get('spread_confidence', 0)
            ml_conf = pred.get('confidence', 0)

            if pred.get('spread_pick') and spread_conf < SPREAD_CONFIDENCE_FLOOR:
                pred['spread_pick_original'] = pred['spread_pick']
                pred['spread_confidence_original'] = spread_conf
                pred['spread_pick'] = None
                pred['spread_confidence'] = 0
                pred['spread_status'] = 'PASS'
                pred['spread_pass_reason'] = f'Below {SPREAD_CONFIDENCE_FLOOR:.0%} floor ({spread_conf:.1%})'
                passes += 1
            elif pred.get('spread_pick'):
                pred['spread_status'] = 'PICK'
                picks += 1
                # Recalibrate
                edge = spread_conf - 0.5
                recalibrated = 0.5 + edge * 1.25
                pred['spread_confidence_recalibrated'] = round(
                    max(SPREAD_CONFIDENCE_FLOOR, min(0.90, recalibrated)), 4)

            if ml_conf < ML_CONFIDENCE_FLOOR:
                pred['ml_status'] = 'WEAK'
            else:
                pred['ml_status'] = 'PICK'

        logger.info(f"Rex V2 filter: {picks} PICKS, {passes} PASSES")
        return predictions


# ─── CLI Entry Point ────────────────────────────────────────

def run_predictions(target_date: Optional[str] = None, tournament: bool = False,
                    seeds_file: Optional[str] = None, output_file: Optional[str] = None):
    """CLI entry point for Rex V2 engine."""
    engine = NCAABEngineRexV2(tournament_mode=tournament)

    td = date.fromisoformat(target_date) if target_date else date.today()

    seeds = None
    if seeds_file and os.path.exists(seeds_file):
        with open(seeds_file) as f:
            seeds = json.load(f)

    predictions = engine.predict_games(td, seeds)

    if not predictions:
        print("No games found.")
        return

    picks = [p for p in predictions if p.get('spread_status') == 'PICK']
    passes = [p for p in predictions if p.get('spread_status') == 'PASS']

    print(f"\n{'='*70}")
    print(f"  🦖 REX V2 NCAAB ENGINE — {td.strftime('%A %B %d, %Y')}")
    print(f"  45-Factor Model | Spread floor: {SPREAD_CONFIDENCE_FLOOR:.0%} | ML floor: {ML_CONFIDENCE_FLOOR:.0%}")
    print(f"  {len(picks)} PICKS | {len(passes)} PASSES | {len(predictions)} total games")
    print(f"{'='*70}\n")

    if picks:
        print(f"  ── REAL PICKS (spread ≥ {SPREAD_CONFIDENCE_FLOOR:.0%}) ──\n")
        for i, p in enumerate(picks, 1):
            winner = p['predicted_winner']
            loser = p['away_team'] if winner == p['home_team'] else p['home_team']
            conf = p['confidence']
            upset = p.get('upset_composite', 0)

            conf_bar = '█' * int(conf * 20) + '░' * (20 - int(conf * 20))
            upset_flag = ' 🔥 UPSET' if upset > 0.3 else ''

            print(f"  {i:2d}. {winner} over {loser}")
            print(f"      ML: [{conf_bar}] {conf:.1%}{upset_flag}")
            if p.get('spread_pick'):
                s_conf = p['spread_confidence']
                s_bar = '█' * int(s_conf * 20) + '░' * (20 - int(s_conf * 20))
                print(f"      Spread: {p['spread_pick']} [{s_bar}] {s_conf:.1%}")
            if p.get('ou_pick'):
                print(f"      O/U: {p['ou_pick']}")

            # Show V2 factor highlights
            v2 = p.get('v2_factors', {})
            highlights = []
            if abs(v2.get('adv_net_rating', 0)) > 0.15:
                highlights.append(f"NetRtg:{v2['adv_net_rating']:+.2f}")
            if abs(v2.get('coaching', 0)) > 0.2:
                highlights.append(f"Coach:{v2['coaching']:+.2f}")
            if v2.get('is_rivalry'):
                highlights.append("🏀RIVALRY")
            if abs(v2.get('travel_fatigue', 0)) > 0.1:
                highlights.append(f"Travel:{v2['travel_fatigue']:.2f}")
            if abs(v2.get('schedule_density', 0)) > 0.15:
                highlights.append(f"Rest:{v2['schedule_density']:+.2f}")
            if highlights:
                print(f"      V2: {' | '.join(highlights)}")

            print(f"      {p['home_team']} ({p.get('home_record','')}) vs {p['away_team']} ({p.get('away_record','')})")
            print()

    if passes:
        print(f"\n  ── PASSES ({len(passes)} games below threshold) ──\n")
        for p in passes[:10]:  # Show first 10
            orig = p.get('spread_pick_original', '?')
            orig_conf = p.get('spread_confidence_original', 0)
            print(f"      PASS: {p['away_team']} @ {p['home_team']} — "
                  f"was {orig} ({orig_conf:.1%})")

    # Save output
    out = output_file or f"rex_v2_ncaab_picks_{td.isoformat()}.json"
    clean = []
    for p in predictions:
        pc = dict(p)
        pc.pop('factors', None)
        clean.append(pc)

    out_path = os.path.join(os.path.dirname(__file__), out)
    with open(out_path, 'w') as f:
        json.dump(clean, f, indent=2, default=str)
    print(f"\nSaved to {out}")

    # Save comparison
    comparison = {
        'date': td.isoformat(),
        'engine': ENGINE_NAME,
        'version': ENGINE_VERSION,
        'total_games': len(predictions),
        'spread_picks': len(picks),
        'spread_passes': len(passes),
        'weights': V2_WEIGHTS,
        'picks_summary': [
            {
                'game': f"{p['away_team']} @ {p['home_team']}",
                'spread_pick': p.get('spread_pick'),
                'spread_confidence': p.get('spread_confidence'),
                'ml_pick': p['predicted_winner'],
                'ml_confidence': p['confidence'],
                'spread_status': p.get('spread_status'),
                'v2_model_prob': p.get('v2_model_home_prob'),
                'upset_composite': p.get('upset_composite'),
            }
            for p in predictions
        ]
    }
    comp_path = os.path.join(os.path.dirname(__file__), f"rex_v2_comparison_{td.isoformat()}.json")
    with open(comp_path, 'w') as f:
        json.dump(comparison, f, indent=2, default=str)
    print(f"Comparison: {comp_path}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Rex V2 NCAAB Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--tournament', action='store_true', help='March Madness mode')
    parser.add_argument('--seeds', type=str, help='Path to seeds JSON file')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_predictions(args.date, args.tournament, args.seeds, args.output)
