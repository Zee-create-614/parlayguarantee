#!/usr/bin/env python3
"""
ParlayGuarantee NBA Challenger Engine — "ALPHA" v3
====================================================
20-factor edge model. Inherits base data from autopilot (OG engine),
layers on 15 new data sources on top of the original 5 Alpha signals.

ORIGINAL 5 (from V2):
  1. ML-to-Spread Divergence
  2. Home/Away Splits
  3. Recent Form / L10
  4. Upset Composite
  5. Injury Edge

NEW 15 (V3):
  6.  Net Rating / Efficiency
  7.  Rest Days / B2B Detection
  8.  ATS Trends
  9.  Player Advanced Stats Impact
  10. Lineup-Specific Impact (injuries × player stats)
  11. Travel / Fatigue Model
  12. Referee Tendencies
  13. Pace Matchup Modeling
  14. Public Betting % / Sharp Money
  15. Motivation Factors
  16. Strength of Schedule
  17. Coaching Matchup
  18. Quarter-by-Quarter Patterns
  19. Clutch Performance
  20. Free Throw Rate Differential

ENGINE_NAME = "Alpha"
ENGINE_VERSION = "3.0"
"""

import json, logging, math, os, sys
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from autopilot import (
    fetch_odds, analyze_game, enhance_game, american_to_prob, devig,
    EST, ODDS_API_KEY, ENGINE_DIR
)
from injury_scraper import get_injuries
from adaptive_learner import AdaptiveLearner
from nba_advanced_stats import (
    fetch_team_ratings, fetch_schedule_rest, fetch_ats_trends,
    fetch_player_advanced_stats, estimate_lineup_impact,
    compute_travel_fatigue, fetch_referee_data, compute_pace_matchup,
    fetch_public_betting, compute_motivation, fetch_strength_of_schedule,
    get_coaching_matchup, fetch_quarter_patterns, fetch_clutch_stats,
    fetch_ft_rate, find_in_data, resolve_team,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('nba_engine_alpha_v3.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

ENGINE_NAME = "Alpha"
ENGINE_VERSION = "3.0"
SPORT_KEY = "basketball_nba"
SPORT_LABEL = "NBA"

# ─── 20-Factor Weights (sum = 1.0) ──────────────────────────────────
# Tier 1 — Highest impact (0.08-0.10 each)
W = {
    # Original 5
    'ml_divergence':   0.10,   # ML conviction vs spread
    'home_away':       0.05,   # Home/away splits
    'form':            0.05,   # L10 momentum
    'upset':           0.04,   # Upset composite
    'injury':          0.06,   # Injury edge (basic)

    # New 15
    'net_rating':      0.10,   # Net rating / efficiency — HIGHEST IMPACT
    'rest_btb':        0.08,   # Rest/B2B — huge proven edge
    'ats_trends':      0.08,   # ATS record — direct betting signal
    'player_impact':   0.07,   # Player advanced stats
    'lineup_impact':   0.06,   # Injury × player stats
    'travel_fatigue':  0.05,   # Travel/fatigue model
    'referee':         0.02,   # Ref tendencies (small but real)
    'pace_matchup':    0.04,   # Pace modeling
    'public_betting':  0.03,   # Public % / contrarian
    'motivation':      0.04,   # Playoff positioning / rivalry
    'sos':             0.03,   # Strength of schedule
    'coaching':        0.02,   # Coach matchup
    'quarter_pattern': 0.01,   # Q-by-Q patterns
    'clutch':          0.03,   # Close game record
    'ft_rate':         0.01,   # Free throw rate differential
    'line_movement':   0.03,   # Sharp line movement signals
}

assert abs(sum(W.values()) - 1.0) < 0.001, f"Weights sum to {sum(W.values())}, not 1.0"

# Confidence floors
ALPHA_SPREAD_FLOOR = 0.62
ML_CONFIDENCE_FLOOR = 0.60


# ─── ESPN Standings (reuse from V2) ─────────────────────────────────
def _fetch_espn_standings() -> Dict:
    try:
        from nba_upset_composite import fetch_nba_standings
        return fetch_nba_standings()
    except Exception as e:
        logger.warning(f"Could not fetch ESPN standings: {e}")
        return {}


def _find_team_stats(team_name: str, standings: Dict) -> Optional[Dict]:
    if not standings:
        return None
    if team_name in standings:
        return standings[team_name]
    last_word = team_name.split()[-1].lower() if team_name else ''
    for key, data in standings.items():
        if isinstance(data, dict) and last_word and last_word in key.lower():
            return data
    return None


# ─── Compute All 20 Edge Signals ─────────────────────────────────────
def _compute_alpha_v3_edge(game: Dict, standings: Dict,
                            ratings: Dict, rest_data: Dict,
                            ats_data: Dict, player_stats: Dict,
                            ref_data: Dict, public_data: Dict,
                            sos_data: Dict, quarter_data: Dict,
                            clutch_data: Dict, ft_data: Dict,
                            target_date: date,
                            line_movement_data: Dict = None) -> Dict:
    """
    Compute Alpha V3's 20-factor composite spread confidence.
    Each factor → normalized 0-1 score.
    """
    ml_prob = game.get('ml_prob', 0.5)
    market_spread_prob = game.get('enhanced_prob', game.get('cover_prob', 0.5))
    pick_team = game.get('pick', '')
    home = game.get('home', '')
    away = game.get('away', '')
    spread = game.get('spread', 0)
    upset_score = game.get('upset_score', 0)
    upset_flip = game.get('upset_flip', False)

    pick_is_home = (pick_team == home)
    opp_name = away if pick_is_home else home

    edges = {}
    reasons = []

    # ─── 1. ML-to-Spread Divergence (10%) ───
    ml_pick = game.get('ml_pick', '')
    if pick_team == ml_pick:
        ml_for_pick = ml_prob
    elif pick_team == home:
        ml_for_pick = game.get('ml_home_prob', 1 - ml_prob)
    else:
        ml_for_pick = 1 - ml_prob

    ml_div = ml_for_pick - market_spread_prob
    ml_edge = max(0.3, min(0.85, 0.5 + ml_div * 1.0))
    edges['ml_divergence'] = ml_edge
    if ml_div > 0.10:
        reasons.append(f"ML conviction {ml_for_pick:.0%} vs spread {market_spread_prob:.0%} = +{ml_div:.0%} edge")

    # ─── 2. Home/Away Splits (5%) ───
    pick_stats = _find_team_stats(pick_team, standings)
    opp_stats_s = _find_team_stats(opp_name, standings)
    ha_edge = 0.5
    if pick_stats:
        pick_venue_pct = pick_stats.get('home_pct' if pick_is_home else 'away_pct', 0.5)
        opp_venue_pct = 0.5
        if opp_stats_s:
            opp_venue_pct = opp_stats_s.get('away_pct' if pick_is_home else 'home_pct', 0.5)
        ha_edge = max(0.3, min(0.8, 0.5 + (pick_venue_pct - opp_venue_pct) * 0.5))
        if pick_venue_pct > 0.60:
            reasons.append(f"{pick_team} strong {'home' if pick_is_home else 'road'} ({pick_venue_pct:.0%})")
    edges['home_away'] = ha_edge

    # ─── 3. Recent Form / L10 (5%) ───
    form_edge = 0.5
    if pick_stats and opp_stats_s:
        pick_l10 = pick_stats.get('l10_pct', 0.5)
        opp_l10 = opp_stats_s.get('l10_pct', 0.5)
        form_edge = max(0.3, min(0.8, 0.5 + (pick_l10 - opp_l10) * 0.5))
        if pick_l10 >= 0.7:
            reasons.append(f"{pick_team} hot L10 ({pick_stats.get('l10_wins',0)}-{pick_stats.get('l10_losses',0)})")
    edges['form'] = form_edge

    # ─── 4. Upset Composite (4%) ───
    upset_edge = 0.5
    if upset_flip:
        upset_edge = 0.70
        reasons.append(f"Upset composite FIRED ({upset_score:.2f})")
    elif upset_score > 0.3:
        upset_edge = 0.55
    elif upset_score < 0.1 and ml_for_pick > 0.6:
        upset_edge = 0.55
    edges['upset'] = upset_edge

    # ─── 5. Injury Edge (6%) ───
    home_inj = game.get('home_injuries', [])
    away_inj = game.get('away_injuries', [])
    pick_inj = home_inj if pick_is_home else away_inj
    opp_inj = away_inj if pick_is_home else home_inj
    pick_out = sum(1 for i in pick_inj if i.get('status', '').lower() in ('out', 'doubtful'))
    opp_out = sum(1 for i in opp_inj if i.get('status', '').lower() in ('out', 'doubtful'))
    inj_gap = opp_out - pick_out
    inj_edge = max(0.3, min(0.75, 0.5 + inj_gap * 0.08))
    if inj_gap > 0:
        reasons.append(f"Injury edge: opp {opp_out} out vs our {pick_out}")
    edges['injury'] = inj_edge

    # ─── 6. Net Rating / Efficiency (10%) ───
    nr_edge = 0.5
    pick_ratings = find_in_data(pick_team, ratings)
    opp_ratings = find_in_data(opp_name, ratings)
    pick_net = 0.0
    opp_net = 0.0
    pick_pace = 100.0
    opp_pace = 100.0
    pick_ortg = 110.0
    opp_ortg = 110.0
    pick_drtg = 110.0
    opp_drtg = 110.0

    if pick_ratings:
        pick_net = pick_ratings.get('net_rtg', 0)
        pick_pace = pick_ratings.get('pace', 100)
        pick_ortg = pick_ratings.get('ortg', 110)
        pick_drtg = pick_ratings.get('drtg', 110)
    if opp_ratings:
        opp_net = opp_ratings.get('net_rtg', 0)
        opp_pace = opp_ratings.get('pace', 100)
        opp_ortg = opp_ratings.get('ortg', 110)
        opp_drtg = opp_ratings.get('drtg', 110)

    if pick_ratings or opp_ratings:
        net_diff = pick_net - opp_net  # positive = our team better
        # Scale: ±10 net rating diff = significant
        nr_edge = max(0.25, min(0.85, 0.5 + net_diff * 0.025))
        if net_diff > 5:
            reasons.append(f"Net rating edge: {pick_team} +{pick_net:.1f} vs {opp_name} {opp_net:+.1f}")
        elif net_diff < -5:
            reasons.append(f"Net rating disadvantage: {pick_net:+.1f} vs {opp_net:+.1f}")
    edges['net_rating'] = nr_edge

    # ─── 7. Rest / B2B (8%) ───
    rest_edge = 0.5
    pick_rest = rest_data.get(resolve_team(pick_team), rest_data.get(pick_team, {}))
    opp_rest = rest_data.get(resolve_team(opp_name), rest_data.get(opp_name, {}))
    pick_rest_days = pick_rest.get('rest_days', 2)
    opp_rest_days = opp_rest.get('rest_days', 2)
    pick_b2b = pick_rest.get('is_b2b', False)
    opp_b2b = opp_rest.get('is_b2b', False)

    rest_diff = pick_rest_days - opp_rest_days
    if opp_b2b and not pick_b2b:
        rest_edge = 0.72
        reasons.append(f"Opponent on B2B, we have {pick_rest_days} rest days")
    elif pick_b2b and not opp_b2b:
        rest_edge = 0.30
        reasons.append(f"We're on B2B, opponent has {opp_rest_days} rest days — risk")
    elif rest_diff > 1:
        rest_edge = min(0.70, 0.5 + rest_diff * 0.07)
        reasons.append(f"Rest advantage: {pick_rest_days}d vs opp {opp_rest_days}d")
    elif rest_diff < -1:
        rest_edge = max(0.35, 0.5 + rest_diff * 0.07)
    edges['rest_btb'] = rest_edge

    # ─── 8. ATS Trends (8%) ───
    ats_edge = 0.5
    pick_ats = find_in_data(pick_team, ats_data)
    opp_ats = find_in_data(opp_name, ats_data)
    if pick_ats:
        ats_pct = pick_ats.get('ats_pct', 0.5)
        venue_key = 'ats_home_pct' if pick_is_home else 'ats_away_pct'
        venue_ats = pick_ats.get(venue_key, ats_pct)
        # Weight venue ATS more than overall
        blended_ats = venue_ats * 0.6 + ats_pct * 0.4
        ats_edge = max(0.3, min(0.75, blended_ats))
        if blended_ats > 0.55:
            reasons.append(f"{pick_team} ATS: {ats_pct:.0%} overall, {venue_ats:.0%} {'home' if pick_is_home else 'away'}")
        elif blended_ats < 0.45:
            reasons.append(f"{pick_team} poor ATS: {ats_pct:.0%}")
    edges['ats_trends'] = ats_edge

    # ─── 9. Player Advanced Stats Impact (7%) ───
    pa_edge = 0.5
    # Compare top-5 player quality
    pick_players = find_in_data(pick_team, player_stats)
    opp_players = find_in_data(opp_name, player_stats)
    if pick_players and opp_players:
        # Average PER of top 3 players by minutes
        pick_top = sum(p.get('per', 15) for p in pick_players[:3]) / 3
        opp_top = sum(p.get('per', 15) for p in opp_players[:3]) / 3
        per_diff = pick_top - opp_top
        pa_edge = max(0.3, min(0.75, 0.5 + per_diff * 0.02))
        if per_diff > 3:
            reasons.append(f"Top player quality edge (PER diff: +{per_diff:.1f})")
    edges['player_impact'] = pa_edge

    # ─── 10. Lineup-Specific Impact (6%) ───
    li_edge = 0.5
    pick_lineup_impact = estimate_lineup_impact(pick_team, pick_inj, player_stats)
    opp_lineup_impact = estimate_lineup_impact(opp_name, opp_inj, player_stats)
    lineup_diff = opp_lineup_impact - pick_lineup_impact  # positive = opponent hurt more
    if abs(lineup_diff) > 1:
        li_edge = max(0.3, min(0.75, 0.5 + lineup_diff * 0.03))
        if lineup_diff > 3:
            reasons.append(f"Lineup impact edge: opp loses ~{abs(opp_lineup_impact):.1f}pts from injuries")
    edges['lineup_impact'] = li_edge

    # ─── 11. Travel / Fatigue (5%) ───
    pick_fatigue = compute_travel_fatigue(pick_team, opp_name, pick_is_home, rest_data)
    opp_fatigue = compute_travel_fatigue(opp_name, pick_team, not pick_is_home, rest_data)
    fatigue_diff = opp_fatigue['fatigue_score'] - pick_fatigue['fatigue_score']
    tf_edge = max(0.3, min(0.75, 0.5 + fatigue_diff * 0.5))
    if fatigue_diff > 0.2:
        reasons.append(f"Travel/fatigue edge: opp fatigue {opp_fatigue['fatigue_score']:.2f} vs ours {pick_fatigue['fatigue_score']:.2f}")
    edges['travel_fatigue'] = tf_edge

    # ─── 12. Referee Tendencies (3%) ───
    ref_edge = 0.5  # neutral by default — refs are hard to get
    game_key = f"{away} @ {home}"
    ref_info = ref_data.get(game_key)
    if ref_info:
        ou_tend = ref_info.get('ou_tendency', 0)
        ref_edge = 0.5 + ou_tend * 0.1  # minimal impact
    edges['referee'] = ref_edge

    # ─── 13. Pace Matchup (4%) ───
    pace_edge = 0.5
    if pick_ratings and opp_ratings:
        if pick_is_home:
            pace_result = compute_pace_matchup(pick_pace, opp_pace, pick_ortg, opp_ortg, pick_drtg, opp_drtg,
                                                game.get('total_line'))
        else:
            pace_result = compute_pace_matchup(opp_pace, pick_pace, opp_ortg, pick_ortg, opp_drtg, pick_drtg,
                                                game.get('total_line'))
        # Pace edge for spread: faster team at home = slight edge
        pace_diff = pace_result.get('pace_diff', 0)
        if pace_diff > 5:
            # Big pace mismatch — the faster team tends to control
            if pick_pace > opp_pace:
                pace_edge = 0.55
            else:
                pace_edge = 0.45
        game['pace_matchup'] = pace_result
    edges['pace_matchup'] = pace_edge

    # ─── 14. Public Betting % (3%) ───
    pub_edge = 0.5  # often no data available
    # Contrarian: if public is heavily on one side, fade them slightly
    edges['public_betting'] = pub_edge

    # ─── 15. Motivation (4%) ───
    pick_standings = _find_team_stats(pick_team, standings) or {}
    opp_standings = _find_team_stats(opp_name, standings) or {}
    pick_motiv = compute_motivation(pick_standings, opp_standings, pick_team, opp_name, target_date)
    opp_motiv = compute_motivation(opp_standings, pick_standings, opp_name, pick_team, target_date)
    motiv_diff = pick_motiv['motivation_score'] - opp_motiv['motivation_score']
    motiv_edge = max(0.35, min(0.70, 0.5 + motiv_diff * 0.5))
    reasons.extend(pick_motiv.get('reasons', []))
    edges['motivation'] = motiv_edge

    # ─── 16. Strength of Schedule (3%) ───
    sos_edge = 0.5
    pick_sos = find_in_data(pick_team, sos_data)
    opp_sos = find_in_data(opp_name, sos_data)
    if pick_sos and opp_sos:
        # Lower rank = harder schedule = team is battle-tested
        pick_rank = pick_sos.get('sos_rank', 15)
        opp_rank = opp_sos.get('sos_rank', 15)
        rank_diff = opp_rank - pick_rank  # positive = we had harder schedule = advantage
        sos_edge = max(0.35, min(0.65, 0.5 + rank_diff * 0.005))
    edges['sos'] = sos_edge

    # ─── 17. Coaching Matchup (2%) ───
    coach = get_coaching_matchup(home, away)
    coach_edge_val = coach['coaching_edge']
    if not pick_is_home:
        coach_edge_val = -coach_edge_val  # flip for away pick
    coaching_edge = max(0.4, min(0.6, 0.5 + coach_edge_val))
    edges['coaching'] = coaching_edge

    # ─── 18. Quarter-by-Quarter Patterns (2%) ───
    qtr_edge = 0.5  # often no data
    pick_qtr = find_in_data(pick_team, quarter_data)
    opp_qtr = find_in_data(opp_name, quarter_data)
    if pick_qtr and opp_qtr:
        # Strong closers = slight edge in spreads
        pick_close = pick_qtr.get('strong_close', False)
        opp_close = opp_qtr.get('strong_close', False)
        if pick_close and not opp_close:
            qtr_edge = 0.58
        elif opp_close and not pick_close:
            qtr_edge = 0.42
    edges['quarter_pattern'] = qtr_edge

    # ─── 19. Clutch Performance (3%) ───
    clutch_edge = 0.5
    pick_clutch = find_in_data(pick_team, clutch_data)
    opp_clutch = find_in_data(opp_name, clutch_data)
    if pick_clutch and opp_clutch:
        pick_cpct = pick_clutch.get('clutch_pct', 0.5)
        opp_cpct = opp_clutch.get('clutch_pct', 0.5)
        cdiff = pick_cpct - opp_cpct
        clutch_edge = max(0.35, min(0.70, 0.5 + cdiff * 0.5))
        if cdiff > 0.15:
            reasons.append(f"Clutch edge: {pick_team} {pick_cpct:.0%} vs {opp_name} {opp_cpct:.0%}")
    edges['clutch'] = clutch_edge

    # ─── 20. Free Throw Rate (2%) ───
    ftr_edge = 0.5
    pick_ft = find_in_data(pick_team, ft_data)
    opp_ft = find_in_data(opp_name, ft_data)
    if pick_ft and opp_ft:
        pick_ftr = pick_ft.get('ft_rate', 0.25)
        opp_ftr = opp_ft.get('ft_rate', 0.25)
        ftr_diff = pick_ftr - opp_ftr
        ftr_edge = max(0.4, min(0.6, 0.5 + ftr_diff * 2.0))
    edges['ft_rate'] = ftr_edge

    # ─── 21. Line Movement (3%) ───
    lm_edge = 0.5
    try:
        if line_movement_data:
            game_key = f"{away} @ {home}"
            lm_signal = line_movement_data.get(game_key, {})
            if lm_signal:
                raw_edge = lm_signal.get('movement_edge', 0.5)
                # Flip if our pick is away (movement_edge is home-perspective)
                if pick_is_home:
                    lm_edge = raw_edge
                else:
                    lm_edge = 1.0 - raw_edge
                if lm_signal.get('steam_move'):
                    reasons.append(f"Steam move detected ({lm_signal.get('spread_moved', 0):+.1f} pts)")
    except Exception:
        pass
    edges['line_movement'] = lm_edge

    # ─── COMPOSITE ───
    alpha_spread_conf = sum(edges[k] * W[k] for k in W)
    alpha_spread_conf = max(0.40, min(0.85, alpha_spread_conf))

    return {
        'alpha_spread_confidence': round(alpha_spread_conf, 4),
        'edge_breakdown': {k: round(v, 4) for k, v in edges.items()},
        'edge_reasons': reasons,
        'factors_available': sum(1 for v in edges.values() if v != 0.5),
        'factors_total': len(edges),
    }


# ─── Data Prefetch (one batch per run) ───────────────────────────────
def _prefetch_all_data(target_date: date) -> Dict:
    """Fetch all external data once, return as a bundle."""
    logger.info("Prefetching all V3 data sources...")

    data = {}

    # Each fetch is try/except — if it fails, empty dict = all 0.5 neutral
    try:
        data['ratings'] = fetch_team_ratings()
        logger.info(f"  Ratings: {len(data['ratings'])} teams")
    except Exception as e:
        logger.warning(f"  Ratings FAILED: {e}")
        data['ratings'] = {}

    try:
        data['rest'] = fetch_schedule_rest(target_date)
        logger.info(f"  Rest/B2B: {len(data['rest'])} teams")
    except Exception as e:
        logger.warning(f"  Rest FAILED: {e}")
        data['rest'] = {}

    try:
        data['ats'] = fetch_ats_trends()
        logger.info(f"  ATS: {len(data['ats'])} teams")
    except Exception as e:
        logger.warning(f"  ATS FAILED: {e}")
        data['ats'] = {}

    try:
        data['player_stats'] = fetch_player_advanced_stats()
        logger.info(f"  Player stats: {len(data['player_stats'])} teams")
    except Exception as e:
        logger.warning(f"  Player stats FAILED: {e}")
        data['player_stats'] = {}

    try:
        data['refs'] = fetch_referee_data(target_date)
        logger.info(f"  Refs: {len(data['refs'])} games")
    except Exception as e:
        logger.warning(f"  Refs FAILED: {e}")
        data['refs'] = {}

    try:
        data['public'] = fetch_public_betting()
        logger.info(f"  Public betting: {len(data['public'])} games")
    except Exception as e:
        logger.warning(f"  Public FAILED: {e}")
        data['public'] = {}

    try:
        data['sos'] = fetch_strength_of_schedule()
        logger.info(f"  SOS: {len(data['sos'])} teams")
    except Exception as e:
        logger.warning(f"  SOS FAILED: {e}")
        data['sos'] = {}

    try:
        data['quarters'] = fetch_quarter_patterns()
        logger.info(f"  Quarter patterns: {len(data['quarters'])} teams")
    except Exception as e:
        logger.warning(f"  Quarter FAILED: {e}")
        data['quarters'] = {}

    try:
        data['clutch'] = fetch_clutch_stats()
        logger.info(f"  Clutch: {len(data['clutch'])} teams")
    except Exception as e:
        logger.warning(f"  Clutch FAILED: {e}")
        data['clutch'] = {}

    try:
        data['ft'] = fetch_ft_rate()
        logger.info(f"  FT rate: {len(data['ft'])} teams")
    except Exception as e:
        logger.warning(f"  FT rate FAILED: {e}")
        data['ft'] = {}

    try:
        from morning_line_movement import get_morning_line_signals
        data['line_movement'] = get_morning_line_signals()
        logger.info(f"  Line movement: {len(data['line_movement'])} games")
    except Exception as e:
        logger.warning(f"  Line movement FAILED: {e}")
        data['line_movement'] = {}

    available = sum(1 for v in data.values() if v)
    logger.info(f"Data prefetch complete: {available}/{len(data)} sources loaded")
    return data


# ─── Main Runner ──────────────────────────────────────────────────────
def run_alpha_v3(target_date: Optional[str] = None, output_file: Optional[str] = None,
                 from_file: Optional[str] = None):
    """Run Alpha V3 challenger engine for NBA."""
    global W
    td = date.fromisoformat(target_date) if target_date else date.today()

    # ─── Adaptive Learning: Load learned weights if available ───
    learner = AdaptiveLearner("alpha")
    W = learner.get_weights(W)
    logger.info(f"Alpha V3 using weights (learned={learner.weights_file.exists()}): "
                f"top 5 = {sorted(W.items(), key=lambda x: -x[1])[:5]}")

    # Get OG picks
    if from_file and os.path.exists(from_file):
        logger.info(f"Loading OG picks from {from_file}")
        with open(from_file) as f:
            raw = json.load(f)
        if isinstance(raw, dict) and 'picks' in raw:
            og_picks = raw['picks']
        elif isinstance(raw, list):
            og_picks = raw
        else:
            og_picks = []
        og_picks = [p for p in og_picks if p.get('sport') == SPORT_LABEL]
    else:
        logger.info(f"Fetching fresh NBA odds for {td}")
        og_picks = _fetch_and_analyze(td)

    if not og_picks:
        print("No NBA games found.")
        return []

    # Fetch all data sources
    standings = _fetch_espn_standings()
    logger.info(f"ESPN standings: {len(standings)} teams")

    ext_data = _prefetch_all_data(td)

    # Apply Alpha V3 edge model
    alpha_picks = []
    picks_count = 0
    pass_count = 0

    for game in og_picks:
        ag = dict(game)
        ag['engine'] = ENGINE_NAME
        ag['engine_version'] = ENGINE_VERSION

        edge_result = _compute_alpha_v3_edge(
            ag, standings,
            ratings=ext_data['ratings'],
            rest_data=ext_data['rest'],
            ats_data=ext_data['ats'],
            player_stats=ext_data['player_stats'],
            ref_data=ext_data['refs'],
            public_data=ext_data['public'],
            sos_data=ext_data['sos'],
            quarter_data=ext_data['quarters'],
            clutch_data=ext_data['clutch'],
            ft_data=ext_data['ft'],
            target_date=td,
            line_movement_data=ext_data.get('line_movement', {}),
        )

        ag['spread_confidence'] = edge_result['alpha_spread_confidence']
        ag['edge_breakdown'] = edge_result['edge_breakdown']
        # factor_scores = edge - 0.5 (positive = favors pick, negative = against)
        ag['factor_scores'] = {k: round(v - 0.5, 4) for k, v in edge_result['edge_breakdown'].items()}
        ag['edge_reasons'] = edge_result['edge_reasons']
        ag['factors_available'] = edge_result['factors_available']
        ag['factors_total'] = edge_result['factors_total']
        ag['ml_confidence'] = round(ag.get('ml_prob', 0.5), 4)
        ag['market_spread_prob'] = round(ag.get('enhanced_prob', ag.get('cover_prob', 0.5)), 4)

        if ag.get('pick') and ag.get('spread_str'):
            ag['spread_pick'] = f"{ag['pick']} {ag['spread_str']}"
        else:
            ag['spread_pick'] = None

        # Apply floor
        if ag['spread_confidence'] < ALPHA_SPREAD_FLOOR:
            ag['spread_pick_original'] = ag['spread_pick']
            ag['spread_confidence_original'] = ag['spread_confidence']
            ag['spread_pick'] = None
            ag['spread_status'] = 'PASS'
            ag['spread_pass_reason'] = f"Below {ALPHA_SPREAD_FLOOR:.0%} floor ({ag['spread_confidence_original']:.1%})"
            pass_count += 1
        else:
            ag['spread_status'] = 'PICK'
            picks_count += 1

        ag['ml_status'] = 'PICK' if ag['ml_confidence'] >= ML_CONFIDENCE_FLOOR else 'WEAK'
        alpha_picks.append(ag)

    # Sort
    alpha_picks.sort(key=lambda x: (x.get('spread_status') == 'PICK', x.get('spread_confidence', 0)), reverse=True)

    logger.info(f"Alpha V3: {picks_count} PICKS, {pass_count} PASSES out of {len(og_picks)} games")

    picks = [p for p in alpha_picks if p.get('spread_status') == 'PICK']
    passes = [p for p in alpha_picks if p.get('spread_status') == 'PASS']

    # Console display
    print(f"\n{'='*70}")
    print(f"  🐺 ALPHA NBA CHALLENGER v3 — {td.strftime('%A %B %d, %Y')}")
    print(f"  20-factor edge model | {sum(1 for d in ext_data.values() if d)}/{len(ext_data)} data sources active")
    print(f"  Spread floor: {ALPHA_SPREAD_FLOOR:.0%} | ML floor: {ML_CONFIDENCE_FLOOR:.0%}")
    print(f"  {len(picks)} PICKS | {len(passes)} PASSES | {len(alpha_picks)} total games")
    print(f"{'='*70}\n")

    if picks:
        print(f"  ── REAL PICKS (Alpha spread >= {ALPHA_SPREAD_FLOOR:.0%}) ──\n")
        for i, p in enumerate(picks, 1):
            _print_pick(i, p)

    if passes:
        print(f"\n  ── PASSES (Alpha spread < {ALPHA_SPREAD_FLOOR:.0%}) ──\n")
        for p in passes:
            orig = p.get('spread_pick_original', '?')
            orig_conf = p.get('spread_confidence_original', 0)
            ml_conf = p['ml_confidence']
            ml_pick = p.get('ml_pick', '?')
            print(f"      PASS: {p.get('away','?')} @ {p.get('home','?')}")
            print(f"            ML: {ml_pick} ({ml_conf:.1%}) | Alpha spread: {orig_conf:.1%}")

    # Save JSON
    out = output_file or f"alpha_v3_nba_picks_{td.isoformat()}.json"
    out_path = ENGINE_DIR / out
    clean = []
    for p in alpha_picks:
        pc = dict(p)
        for k in list(pc.keys()):
            if callable(pc[k]):
                del pc[k]
        clean.append(pc)
    with open(out_path, 'w') as f:
        json.dump(clean, f, indent=2)
    print(f"\nSaved to {out_path}")

    # Save Telegram text
    tg_text = _build_telegram_text(td, picks, passes, alpha_picks, ext_data)
    tg_path = ENGINE_DIR / f"alpha_v3_nba_telegram_{td.isoformat()}.txt"
    with open(tg_path, 'w', encoding='utf-8') as f:
        f.write(tg_text)
    print(f"Telegram text: {tg_path}")

    # Save comparison
    comparison = {
        'date': td.isoformat(),
        'engine': ENGINE_NAME,
        'version': ENGINE_VERSION,
        'total_games': len(alpha_picks),
        'spread_picks': len(picks),
        'spread_passes': len(passes),
        'data_sources': {k: len(v) for k, v in ext_data.items()},
        'picks_summary': [
            {
                'game': f"{p.get('away','?')} @ {p.get('home','?')}",
                'spread_pick': p.get('spread_pick') or p.get('spread_pick_original'),
                'spread_confidence': p.get('spread_confidence'),
                'ml_pick': p.get('ml_pick'),
                'ml_confidence': p.get('ml_confidence'),
                'spread_status': p.get('spread_status'),
                'factors_available': p.get('factors_available'),
                'edge_breakdown': p.get('edge_breakdown'),
                'edge_reasons': p.get('edge_reasons'),
            }
            for p in alpha_picks
        ]
    }
    comp_path = ENGINE_DIR / f"alpha_v3_comparison_{td.isoformat()}.json"
    with open(comp_path, 'w') as f:
        json.dump(comparison, f, indent=2)

    return alpha_picks


def _print_pick(i: int, p: dict):
    spread_pick = p.get('spread_pick', '?')
    s_conf = p.get('spread_confidence', 0)
    ml_pick = p.get('ml_pick', '?')
    ml_conf = p.get('ml_confidence', 0)
    mkt_spread = p.get('market_spread_prob', 0)
    factors = p.get('factors_available', 0)
    total_f = p.get('factors_total', 20)

    s_bar = '#' * int(s_conf * 20) + '.' * (20 - int(s_conf * 20))
    ml_bar = '#' * int(ml_conf * 20) + '.' * (20 - int(ml_conf * 20))
    upset_flag = ' UPSET' if p.get('upset_flip') else ''

    away = p.get('away', '?')
    home = p.get('home', '?')
    game_time = p.get('game_time', '?')

    print(f"  {i:2d}. {away} @ {home} -- {game_time}")
    print(f"      ML: {ml_pick} [{ml_bar}] {ml_conf:.1%}{upset_flag}")
    print(f"      Spread: {spread_pick} [{s_bar}] {s_conf:.1%}  (market: {mkt_spread:.1%})  [{factors}/{total_f} factors]")
    # O/U handled by separate totals engine — not Alpha V3's job
    if p.get('edge_reasons'):
        for r in p['edge_reasons'][:5]:
            print(f"      >> {r}")

    # Show edge breakdown summary (top 5 non-neutral)
    breakdown = p.get('edge_breakdown', {})
    sorted_edges = sorted(breakdown.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)[:5]
    edge_str = ' | '.join(f"{k}:{v:.2f}" for k, v in sorted_edges if v != 0.5)
    if edge_str:
        print(f"      Edges: {edge_str}")
    print()


def _build_telegram_text(td: date, picks: list, passes: list, all_picks: list, ext_data: dict) -> str:
    lines = []
    sources = sum(1 for v in ext_data.values() if v)
    lines.append(f"🐺 ALPHA NBA v3 — {td.strftime('%A %b %d, %Y')}")
    lines.append(f"20-factor edge model | {sources}/{len(ext_data)} data sources")
    lines.append(f"Spread floor: {ALPHA_SPREAD_FLOOR:.0%} | ML floor: {ML_CONFIDENCE_FLOOR:.0%}")
    lines.append(f"{len(picks)} PICKS | {len(passes)} PASSES | {len(all_picks)} games")
    lines.append("")

    if picks:
        lines.append("── PICKS ──")
        lines.append("")
        for i, p in enumerate(picks, 1):
            spread_pick = p.get('spread_pick', '?')
            s_conf = p.get('spread_confidence', 0)
            ml_pick = p.get('ml_pick', '?')
            ml_conf = p.get('ml_confidence', 0)
            mkt = p.get('market_spread_prob', 0)
            factors = p.get('factors_available', 0)
            upset_flag = ' 🔥UPSET' if p.get('upset_flip') else ''

            lines.append(f"{i}. {p.get('away','?')} @ {p.get('home','?')} — {p.get('game_time','?')}")
            lines.append(f"   ML: {ml_pick} ({ml_conf:.1%}){upset_flag}")
            lines.append(f"   Spread: {spread_pick} ({s_conf:.1%}) [mkt: {mkt:.1%}] [{factors}F]")
            # O/U handled by separate totals engine — not Alpha V3's job
            if p.get('edge_reasons'):
                for r in p['edge_reasons'][:4]:
                    lines.append(f"   → {r}")
            lines.append("")

    if passes:
        lines.append("── PASSES ──")
        lines.append("")
        for p in passes:
            orig_conf = p.get('spread_confidence_original', p.get('spread_confidence', 0))
            ml_pick = p.get('ml_pick', '?')
            ml_conf = p.get('ml_confidence', 0)
            lines.append(f"PASS: {p.get('away','?')} @ {p.get('home','?')}")
            lines.append(f"  ML: {ml_pick} ({ml_conf:.1%}) | Alpha: {orig_conf:.1%}")
            lines.append("")

    return "\n".join(lines)


def _fetch_and_analyze(td: date) -> List[Dict]:
    raw_games = fetch_odds(SPORT_KEY)
    if not raw_games:
        logger.warning("No NBA odds returned from API")
        return []

    analyzed = []
    for game in raw_games:
        result = analyze_game(game, SPORT_LABEL)
        if result:
            analyzed.append(result)

    if not analyzed:
        return []

    try:
        injuries = get_injuries()
    except Exception as e:
        logger.warning(f"Injury fetch failed: {e}")
        injuries = {}

    for game in analyzed:
        try:
            enhance_game(game, injuries)
        except Exception as e:
            logger.warning(f"Enhance failed for {game.get('away')} @ {game.get('home')}: {e}")

    try:
        from nba_upset_composite import enhance_games_with_upset_composite as nba_upset_v2
        nba_upset_v2(analyzed, injuries)
        logger.info("NBA upset composite applied")
    except Exception as e:
        logger.warning(f"NBA upset composite not available: {e}")

    logger.info(f"Analyzed {len(analyzed)} NBA games")
    return analyzed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Alpha NBA Challenger Engine v3 — 20 Factor Model')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--from-file', type=str, help='Load OG picks from file instead of fetching')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_alpha_v3(args.date, args.output, args.from_file)
