#!/usr/bin/env python3
"""
ParlayGuarantee NBA Challenger Engine — "ALPHA" v2
====================================================
Challenger to the OG NBA engine (autopilot).

KEY DIFFERENCE FROM OG:
  OG's spread confidence = devigged market odds (always 50-53% → useless).
  Alpha builds its OWN spread confidence from multiple edge signals:
    1. ML-to-Spread Divergence (35%) — if ML says 75% winner but spread is 50/50, there's edge
    2. Home/Away Splits (20%) — team's actual record at home/road vs implied
    3. Recent Form / L10 (15%) — hot/cold streaks the market may be slow to price
    4. Upset Composite (15%) — our proprietary upset detector
    5. Injury Edge (15%) — key player out = spread may be stale

  Separate spread_confidence and ml_confidence like Rex.
  Ranked by Alpha's composite spread score — the EDGE, not the market's 50%.

FROZEN OG: Do not modify autopilot.py. Alpha runs alongside it.
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('nba_engine_alpha.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

ENGINE_NAME = "Alpha"
ENGINE_VERSION = "2.0"
SPORT_KEY = "basketball_nba"
SPORT_LABEL = "NBA"

# ─── Alpha Edge Weights ─────────────────────────────────────
W_ML_DIVERGENCE = 0.35    # ML conviction vs spread implied
W_HOME_AWAY     = 0.20    # Home/away split edge
W_FORM          = 0.15    # L10 / recent momentum
W_UPSET         = 0.15    # Upset composite signal
W_INJURY        = 0.15    # Injury edge

# Minimum edge to be a real PICK
ALPHA_SPREAD_FLOOR = 0.56
ML_CONFIDENCE_FLOOR = 0.58


def _fetch_espn_standings() -> Dict:
    """Fetch team standings from ESPN for splits/form data."""
    try:
        from nba_upset_composite import fetch_nba_standings
        return fetch_nba_standings()
    except Exception as e:
        logger.warning(f"Could not fetch ESPN standings: {e}")
        return {}


def _find_team_stats(team_name: str, standings: Dict) -> Optional[Dict]:
    """Find team stats in ESPN standings by fuzzy match."""
    if not standings:
        return None
    # Direct match
    if team_name in standings:
        return standings[team_name]
    # Fuzzy: check if team name's last word matches
    last_word = team_name.split()[-1].lower() if team_name else ''
    for key, data in standings.items():
        if isinstance(data, dict) and last_word and last_word in key.lower():
            return data
    return None


def _compute_alpha_edge(game: Dict, standings: Dict) -> Dict:
    """
    Compute Alpha's composite spread confidence from multiple edge signals.
    Returns dict with alpha_spread_confidence, edge_breakdown, edge_reasons.
    """
    ml_prob = game.get('ml_prob', 0.5)
    market_spread_prob = game.get('enhanced_prob', game.get('cover_prob', 0.5))
    pick_team = game.get('pick', '')
    home = game.get('home', '')
    away = game.get('away', '')
    spread = game.get('spread', 0)
    upset_score = game.get('upset_score', 0)
    upset_flip = game.get('upset_flip', False)

    edges = {}
    reasons = []

    # ─── 1. ML-to-Spread Divergence (35%) ───
    # If ML says team wins 75% but spread implies 50%, that's a 25% divergence
    # The team the spread picks should benefit from this conviction
    # Figure out if spread pick aligns with ML pick
    ml_pick = game.get('ml_pick', '')
    spread_pick = pick_team

    # ML prob for the spread-picked team
    if spread_pick == ml_pick:
        ml_for_spread_team = ml_prob
    elif spread_pick == home:
        ml_for_spread_team = game.get('ml_home_prob', 1 - ml_prob)
    else:
        ml_for_spread_team = 1 - ml_prob

    # Divergence: how much does ML conviction exceed the market's ~50%?
    ml_divergence = ml_for_spread_team - market_spread_prob
    # Scale: 0% divergence = 0.5, 30%+ divergence = ~0.8
    ml_edge_score = 0.5 + ml_divergence * 1.0  # amplify
    ml_edge_score = max(0.3, min(0.85, ml_edge_score))
    edges['ml_divergence'] = ml_edge_score

    if ml_divergence > 0.10:
        reasons.append(f"ML conviction {ml_for_spread_team:.0%} vs spread {market_spread_prob:.0%} = +{ml_divergence:.0%} edge")
    elif ml_divergence < -0.05:
        reasons.append(f"ML disagrees with spread pick ({ml_for_spread_team:.0%} vs {market_spread_prob:.0%})")

    # ─── 2. Home/Away Splits (20%) ───
    pick_is_home = (spread_pick == home)
    pick_stats = _find_team_stats(spread_pick, standings)
    opp_name = away if pick_is_home else home
    opp_stats = _find_team_stats(opp_name, standings)

    ha_edge = 0.5  # neutral
    if pick_stats:
        if pick_is_home:
            pick_venue_pct = pick_stats.get('home_pct', 0.5)
        else:
            pick_venue_pct = pick_stats.get('away_pct', 0.5)

        if opp_stats:
            if pick_is_home:
                opp_venue_pct = opp_stats.get('away_pct', 0.5)
            else:
                opp_venue_pct = opp_stats.get('home_pct', 0.5)
            # Edge = our team's venue record vs their team's venue record
            venue_gap = pick_venue_pct - opp_venue_pct
            ha_edge = 0.5 + venue_gap * 0.5
        else:
            ha_edge = 0.5 + (pick_venue_pct - 0.5) * 0.5

        ha_edge = max(0.3, min(0.8, ha_edge))

        if pick_venue_pct > 0.60:
            venue = "home" if pick_is_home else "road"
            reasons.append(f"{spread_pick} strong {venue} team ({pick_venue_pct:.0%})")
        elif pick_venue_pct < 0.35:
            venue = "home" if pick_is_home else "road"
            reasons.append(f"{spread_pick} weak {venue} ({pick_venue_pct:.0%}) — risk")

    edges['home_away'] = ha_edge

    # ─── 3. Recent Form / L10 (15%) ───
    form_edge = 0.5
    if pick_stats and opp_stats:
        pick_l10 = pick_stats.get('l10_pct', 0.5)
        opp_l10 = opp_stats.get('l10_pct', 0.5)
        form_gap = pick_l10 - opp_l10
        form_edge = 0.5 + form_gap * 0.5
        form_edge = max(0.3, min(0.8, form_edge))

        if pick_l10 >= 0.7:
            reasons.append(f"{spread_pick} hot ({pick_stats.get('l10_wins',0)}-{pick_stats.get('l10_losses',0)} L10)")
        elif pick_l10 <= 0.3:
            reasons.append(f"{spread_pick} cold ({pick_stats.get('l10_wins',0)}-{pick_stats.get('l10_losses',0)} L10) — risk")

        if opp_l10 <= 0.3:
            reasons.append(f"Opponent cold ({opp_stats.get('l10_wins',0)}-{opp_stats.get('l10_losses',0)} L10)")
    elif pick_stats:
        pick_l10 = pick_stats.get('l10_pct', 0.5)
        form_edge = 0.5 + (pick_l10 - 0.5) * 0.3
        form_edge = max(0.3, min(0.8, form_edge))

    edges['form'] = form_edge

    # ─── 4. Upset Composite (15%) ───
    # When upset composite fires AND we're picking the dog, that's edge
    # When composite says NO upset AND we're picking the favorite, also edge
    upset_edge = 0.5
    if upset_flip:
        # Composite says upset is likely — if spread pick IS the dog, edge UP
        upset_edge = 0.70
        reasons.append(f"Upset composite FIRED ({upset_score:.2f}) — dog has value")
    elif upset_score > 0.3:
        # Moderate upset signal
        upset_edge = 0.55
        reasons.append(f"Mild upset signal ({upset_score:.2f})")
    elif upset_score < 0.1:
        # No upset signal — if we're on the favorite, that's confirmation
        if ml_for_spread_team > 0.6:
            upset_edge = 0.55
            reasons.append("No upset signal — favorite safe")

    edges['upset'] = upset_edge

    # ─── 5. Injury Edge (15%) ───
    inj_edge = 0.5
    home_inj = game.get('home_injuries', [])
    away_inj = game.get('away_injuries', [])

    # Count significant injuries (Out/Doubtful) for each side
    pick_injuries = home_inj if pick_is_home else away_inj
    opp_injuries = away_inj if pick_is_home else home_inj

    pick_out = sum(1 for i in pick_injuries if i.get('status', '').lower() in ('out', 'doubtful'))
    opp_out = sum(1 for i in opp_injuries if i.get('status', '').lower() in ('out', 'doubtful'))

    inj_gap = opp_out - pick_out  # positive = opponent has more injuries = good for us
    if inj_gap > 0:
        inj_edge = min(0.70, 0.5 + inj_gap * 0.08)
        reasons.append(f"Injury edge: opponent has {opp_out} out/doubtful vs our {pick_out}")
    elif inj_gap < 0:
        inj_edge = max(0.35, 0.5 + inj_gap * 0.08)
        reasons.append(f"Injury disadvantage: we have {pick_out} out vs opponent {opp_out}")

    edges['injury'] = inj_edge

    # ─── Composite ───
    alpha_spread_conf = (
        edges['ml_divergence'] * W_ML_DIVERGENCE +
        edges['home_away']     * W_HOME_AWAY +
        edges['form']          * W_FORM +
        edges['upset']         * W_UPSET +
        edges['injury']        * W_INJURY
    )
    # Slight sigmoid to compress extremes
    alpha_spread_conf = max(0.40, min(0.85, alpha_spread_conf))

    return {
        'alpha_spread_confidence': round(alpha_spread_conf, 4),
        'edge_breakdown': {k: round(v, 4) for k, v in edges.items()},
        'edge_reasons': reasons,
    }


def run_alpha(target_date: Optional[str] = None, output_file: Optional[str] = None,
              from_file: Optional[str] = None):
    """Run Alpha challenger engine for NBA."""
    td = date.fromisoformat(target_date) if target_date else date.today()

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

    # Fetch ESPN standings for splits/form
    standings = _fetch_espn_standings()
    logger.info(f"ESPN standings: {len(standings)} teams loaded")

    # Apply Alpha edge model
    alpha_picks = []
    picks_count = 0
    pass_count = 0

    for game in og_picks:
        ag = dict(game)
        ag['engine'] = ENGINE_NAME
        ag['engine_version'] = ENGINE_VERSION

        # Compute Alpha's edge-based spread confidence
        edge_result = _compute_alpha_edge(ag, standings)
        ag['spread_confidence'] = edge_result['alpha_spread_confidence']
        ag['edge_breakdown'] = edge_result['edge_breakdown']
        ag['edge_reasons'] = edge_result['edge_reasons']
        ag['ml_confidence'] = round(ag.get('ml_prob', 0.5), 4)
        ag['market_spread_prob'] = round(ag.get('enhanced_prob', ag.get('cover_prob', 0.5)), 4)

        # Build spread pick string
        if ag.get('pick') and ag.get('spread_str'):
            ag['spread_pick'] = f"{ag['pick']} {ag['spread_str']}"
        else:
            ag['spread_pick'] = None

        # Apply spread floor
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

        # ML status
        if ag['ml_confidence'] < ML_CONFIDENCE_FLOOR:
            ag['ml_status'] = 'WEAK'
        else:
            ag['ml_status'] = 'PICK'

        alpha_picks.append(ag)

    # Sort: PICKS first by spread confidence, then PASSES
    alpha_picks.sort(key=lambda x: (
        x.get('spread_status') == 'PICK',
        x.get('spread_confidence', 0)
    ), reverse=True)

    logger.info(f"Alpha filter: {picks_count} PICKS, {pass_count} PASSES out of {len(og_picks)} games")

    picks = [p for p in alpha_picks if p.get('spread_status') == 'PICK']
    passes = [p for p in alpha_picks if p.get('spread_status') == 'PASS']

    # Console display
    print(f"\n{'='*70}")
    print(f"  🐺 ALPHA NBA CHALLENGER v2 — {td.strftime('%A %B %d, %Y')}")
    print(f"  Edge model: ML divergence + H/A splits + form + upset + injuries")
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
            print(f"            ML: {ml_pick} ({ml_conf:.1%}) | Alpha spread: {orig_conf:.1%} ← not enough edge")

    # Save JSON
    out = output_file or f"alpha_nba_picks_{td.isoformat()}.json"
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
    tg_text = _build_telegram_text(td, picks, passes, alpha_picks)
    tg_path = ENGINE_DIR / f"alpha_nba_telegram_{td.isoformat()}.txt"
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
        'picks_summary': [
            {
                'game': f"{p.get('away','?')} @ {p.get('home','?')}",
                'spread_pick': p.get('spread_pick'),
                'spread_confidence': p.get('spread_confidence'),
                'ml_pick': p.get('ml_pick'),
                'ml_confidence': p.get('ml_confidence'),
                'spread_status': p.get('spread_status'),
                'edge_breakdown': p.get('edge_breakdown'),
                'edge_reasons': p.get('edge_reasons'),
            }
            for p in alpha_picks
        ]
    }
    comp_path = ENGINE_DIR / f"alpha_comparison_{td.isoformat()}.json"
    with open(comp_path, 'w') as f:
        json.dump(comparison, f, indent=2)

    return alpha_picks


def _print_pick(i: int, p: dict):
    """Console print a single pick in Rex format."""
    spread_pick = p.get('spread_pick', '?')
    s_conf = p.get('spread_confidence', 0)
    ml_pick = p.get('ml_pick', '?')
    ml_conf = p.get('ml_confidence', 0)
    mkt_spread = p.get('market_spread_prob', 0)

    s_bar = '#' * int(s_conf * 20) + '.' * (20 - int(s_conf * 20))
    ml_bar = '#' * int(ml_conf * 20) + '.' * (20 - int(ml_conf * 20))
    upset_flag = ' UPSET' if p.get('upset_flip') else ''

    away = p.get('away', '?')
    home = p.get('home', '?')
    game_time = p.get('game_time', '?')

    print(f"  {i:2d}. {away} @ {home} -- {game_time}")
    print(f"      ML: {ml_pick} [{ml_bar}] {ml_conf:.1%}{upset_flag}")
    print(f"      Spread: {spread_pick} [{s_bar}] {s_conf:.1%}  (market: {mkt_spread:.1%})")
    if p.get('ou_pick') and p.get('total_line'):
        print(f"      O/U: {p['ou_pick']} {p['total_line']} ({p.get('ou_prob', 0):.1%})")
    if p.get('edge_reasons'):
        for r in p['edge_reasons'][:3]:
            print(f"      >> {r}")
    print()


def _build_telegram_text(td: date, picks: list, passes: list, all_picks: list) -> str:
    """Build a Telegram-formatted text summary."""
    lines = []
    lines.append(f"🐺 ALPHA NBA v2 — {td.strftime('%A %b %d, %Y')}")
    lines.append(f"Edge model: ML div + H/A + form + upset + injuries")
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
            away = p.get('away', '?')
            home = p.get('home', '?')
            game_time = p.get('game_time', '?')
            upset_flag = ' 🔥UPSET' if p.get('upset_flip') else ''

            lines.append(f"{i}. {away} @ {home} — {game_time}")
            lines.append(f"   ML: {ml_pick} ({ml_conf:.1%}){upset_flag}")
            lines.append(f"   Spread: {spread_pick} ({s_conf:.1%}) [mkt: {mkt:.1%}]")
            if p.get('ou_pick') and p.get('total_line'):
                lines.append(f"   O/U: {p['ou_pick']} {p['total_line']} ({p.get('ou_prob', 0):.1%})")
            if p.get('edge_reasons'):
                for r in p['edge_reasons'][:3]:
                    lines.append(f"   → {r}")
            lines.append("")

    if passes:
        lines.append("── PASSES ──")
        lines.append("")
        for p in passes:
            orig = p.get('spread_pick_original', '?')
            orig_conf = p.get('spread_confidence_original', 0)
            ml_pick = p.get('ml_pick', '?')
            ml_conf = p.get('ml_confidence', 0)
            lines.append(f"PASS: {p.get('away','?')} @ {p.get('home','?')}")
            lines.append(f"  ML: {ml_pick} ({ml_conf:.1%}) | Alpha: {orig_conf:.1%}")
            if p.get('edge_reasons'):
                for r in p['edge_reasons'][:2]:
                    lines.append(f"  → {r}")
            lines.append("")

    return "\n".join(lines)


def _fetch_and_analyze(td: date) -> List[Dict]:
    """Fetch odds and run OG analysis pipeline for NBA games."""
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
        analyzed = nba_upset_v2(analyzed)
        logger.info("NBA upset composite applied")
    except Exception as e:
        logger.warning(f"NBA upset composite not available: {e}")

    logger.info(f"Analyzed {len(analyzed)} NBA games")
    return analyzed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Alpha NBA Challenger Engine v2')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--from-file', type=str, help='Load OG picks from file instead of fetching')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_alpha(args.date, args.output, args.from_file)
