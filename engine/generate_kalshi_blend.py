#!/usr/bin/env python3
"""
generate_kalshi_blend.py — A/B Test: Engine + Kalshi Blended Picks
==================================================================
Reads today's engine-only picks, fetches Kalshi consensus, blends them,
and saves to picks_YYYY-MM-DD_engine_plus_kalshi/.

NOT part of the daily autopilot. Manual A/B test script only.

Blending logic:
- Kalshi provides moneyline win probabilities (no spreads/totals)
- For spread picks: if Kalshi disagrees on winner, reduce confidence
- For spread picks: if Kalshi agrees, boost confidence slightly
- Weight: 75% engine, 25% Kalshi consensus
- Flag games where divergence > 10% as potential edges
- NCAAB: no Kalshi game markets available, passes through unchanged

Usage:
    python generate_kalshi_blend.py
    python generate_kalshi_blend.py --date 2026-02-23
"""

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# Setup
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("kalshi_blend")

ENGINE_DIR = Path(__file__).parent
EST = timezone(timedelta(hours=-5))

from kalshi_client import KalshiClient, KALSHI_ABBREV_TO_TEAM


def load_engine_picks(picks_dir: Path) -> dict:
    """Load all engine pick files from a picks directory."""
    result = {
        'nba_spread': [],
        'ncaab_spread': [],
        'nba_picks': [],
        'ncaab_picks': [],
        'all_picks': None,
    }

    for fname, key in [
        ('nba_spread_picks.json', 'nba_spread'),
        ('ncaab_spread_picks.json', 'ncaab_spread'),
        ('nba_picks.json', 'nba_picks'),
        ('ncaab_picks.json', 'ncaab_picks'),
    ]:
        fpath = picks_dir / fname
        if fpath.exists():
            with open(fpath, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    result[key] = data
                elif isinstance(data, dict) and 'picks' in data:
                    result[key] = data['picks']
                else:
                    result[key] = data

    all_file = picks_dir / 'all_picks.json'
    if all_file.exists():
        with open(all_file, encoding='utf-8') as f:
            result['all_picks'] = json.load(f)

    return result


def blend_spread_pick(pick: dict, kalshi: dict, engine_weight: float = 0.75) -> dict:
    """
    Blend a single spread pick with Kalshi moneyline probability.
    
    Kalshi gives us moneyline win probability. We use it to adjust spread confidence:
    - If our spread pick is on the team Kalshi also favors → boost confidence
    - If our spread pick disagrees with Kalshi favorite → reduce confidence
    - The magnitude of adjustment depends on divergence
    """
    blended = dict(pick)  # Copy
    kalshi_weight = 1 - engine_weight
    
    home = pick.get('home_team', pick.get('home', ''))
    away = pick.get('away_team', pick.get('away', ''))
    
    # Who does our engine pick to cover the spread?
    engine_pick_team = pick.get('predicted_winner', pick.get('pick', ''))
    engine_conf = pick.get('confidence', pick.get('enhanced_prob', pick.get('cover_prob', 0.5)))
    
    # Kalshi win probabilities
    kalshi_home_prob = kalshi['home_win_prob']
    kalshi_away_prob = kalshi['away_win_prob']
    kalshi_favorite = home if kalshi_home_prob > kalshi_away_prob else away
    kalshi_fav_prob = max(kalshi_home_prob, kalshi_away_prob)
    
    # Does our pick agree with Kalshi on the likely winner?
    engine_picks_home = (engine_pick_team == home)
    kalshi_picks_home = (kalshi_home_prob > kalshi_away_prob)
    agreement = (engine_picks_home == kalshi_picks_home)
    
    # Calculate Kalshi-implied spread confidence
    # If Kalshi says team wins at 70%, that's roughly a strong spread cover signal
    # But spread != moneyline, so we dampen the signal
    if engine_picks_home:
        kalshi_signal = kalshi_home_prob
    else:
        kalshi_signal = kalshi_away_prob
    
    # Blend confidence
    blended_conf = (engine_conf * engine_weight) + (kalshi_signal * kalshi_weight)
    blended_conf = round(min(max(blended_conf, 0.30), 0.85), 4)  # Clamp
    
    # Divergence analysis
    divergence = abs(engine_conf - kalshi_signal)
    
    # Flag potential edges (>10% divergence)
    edge_flag = False
    edge_direction = None
    if divergence > 0.10:
        edge_flag = True
        if engine_conf > kalshi_signal:
            edge_direction = "ENGINE_HIGHER"  # Our model more confident than market
        else:
            edge_direction = "KALSHI_HIGHER"  # Market more confident than our model
    
    # Check if the pick would CHANGE (flip) due to Kalshi
    pick_changed = False
    new_pick_team = engine_pick_team
    if not agreement and kalshi_fav_prob > 0.60 and engine_conf < 0.55:
        # Strong Kalshi signal contradicts a weak engine pick → flag but don't flip
        # (We trust our spread model, but note the disagreement)
        blended['kalshi_warning'] = f"Kalshi strongly favors {kalshi_favorite} ({kalshi_fav_prob:.0%})"
    
    if not agreement and blended_conf < 0.48:
        # After blending, if confidence drops below 48%, consider flipping
        pick_changed = True
        new_pick_team = kalshi_favorite
        # Recalculate confidence for the flipped pick
        if new_pick_team == home:
            blended_conf = (0.5 * engine_weight) + (kalshi_home_prob * kalshi_weight)
        else:
            blended_conf = (0.5 * engine_weight) + (kalshi_away_prob * kalshi_weight)
        blended_conf = round(min(max(blended_conf, 0.30), 0.85), 4)
    
    # Update the pick
    blended['original_confidence'] = engine_conf
    blended['kalshi_home_prob'] = kalshi_home_prob
    blended['kalshi_away_prob'] = kalshi_away_prob
    blended['kalshi_volume'] = kalshi.get('total_volume', 0)
    blended['kalshi_event_ticker'] = kalshi.get('event_ticker', '')
    blended['blended_confidence'] = blended_conf
    blended['confidence'] = blended_conf
    blended['kalshi_agreement'] = agreement
    blended['kalshi_divergence'] = round(divergence, 4)
    blended['kalshi_edge_flag'] = edge_flag
    blended['kalshi_edge_direction'] = edge_direction
    blended['pick_changed'] = pick_changed
    
    if pick_changed:
        blended['original_pick'] = engine_pick_team
        blended['predicted_winner'] = new_pick_team
        if 'pick' in blended:
            blended['pick'] = new_pick_team
    
    if 'enhanced_prob' in blended:
        blended['enhanced_prob'] = blended_conf
    if 'cover_prob' in blended:
        blended['cover_prob'] = blended_conf
    
    return blended


def run_blend(target_date: str = None):
    """Main blending pipeline."""
    if not target_date:
        target_date = datetime.now(EST).strftime('%Y-%m-%d')

    engine_dir = ENGINE_DIR / f"picks_{target_date}_engine_only"
    if not engine_dir.exists():
        engine_dir = ENGINE_DIR / f"picks_{target_date}"
    
    if not engine_dir.exists():
        log.error(f"No picks directory found for {target_date}")
        return

    log.info(f"Loading engine picks from {engine_dir}")
    picks = load_engine_picks(engine_dir)

    # Output directory
    out_dir = ENGINE_DIR / f"picks_{target_date}_engine_plus_kalshi"
    out_dir.mkdir(exist_ok=True)

    # Fetch Kalshi NBA data
    log.info("Fetching Kalshi NBA game markets...")
    client = KalshiClient()
    
    # Try today's date, but also check the actual game dates in our picks
    kalshi_games = client.fetch_nba_game_markets()  # All active
    if not kalshi_games:
        log.warning("No Kalshi NBA game markets found!")
    else:
        log.info(f"Fetched {len(kalshi_games)} Kalshi NBA game markets")

    # Build lookup by home team
    kalshi_by_home = {}
    for kg in kalshi_games:
        kalshi_by_home[kg['home_team'].lower()] = kg

    # ── Blend NBA spread picks ──
    nba_spread = picks.get('nba_spread', [])
    nba_spread_blended = []
    nba_changes = []
    for pick in nba_spread:
        home = pick.get('home_team', pick.get('home', ''))
        kalshi = kalshi_by_home.get(home.lower())
        if kalshi:
            blended = blend_spread_pick(pick, kalshi)
            nba_spread_blended.append(blended)
            if blended.get('pick_changed'):
                nba_changes.append(blended)
        else:
            # No Kalshi data — pass through unchanged
            unchanged = dict(pick)
            unchanged['kalshi_matched'] = False
            unchanged['blended_confidence'] = pick.get('confidence', pick.get('enhanced_prob', 0.5))
            nba_spread_blended.append(unchanged)

    # ── NCAAB: pass through (no Kalshi game markets) ──
    ncaab_spread = picks.get('ncaab_spread', [])
    ncaab_spread_blended = []
    for pick in ncaab_spread:
        unchanged = dict(pick)
        unchanged['kalshi_matched'] = False
        unchanged['kalshi_note'] = 'No Kalshi NCAAB game markets available'
        unchanged['blended_confidence'] = pick.get('confidence', pick.get('enhanced_prob', 0.5))
        ncaab_spread_blended.append(unchanged)

    # ── Blend NBA full picks (from nba_picks.json) ──
    nba_full = picks.get('nba_picks', [])
    nba_full_blended = []
    for pick in nba_full:
        home = pick.get('home_team', pick.get('home', ''))
        kalshi = kalshi_by_home.get(home.lower())
        if kalshi:
            blended = blend_spread_pick(pick, kalshi)
            nba_full_blended.append(blended)
        else:
            unchanged = dict(pick)
            unchanged['kalshi_matched'] = False
            unchanged['blended_confidence'] = pick.get('confidence', pick.get('enhanced_prob', 0.5))
            nba_full_blended.append(unchanged)

    # ── Save all outputs ──
    log.info(f"\nSaving blended picks to {out_dir}")

    with open(out_dir / 'nba_spread_picks.json', 'w', encoding='utf-8') as f:
        json.dump(nba_spread_blended, f, indent=2, default=str)

    with open(out_dir / 'ncaab_spread_picks.json', 'w', encoding='utf-8') as f:
        json.dump(ncaab_spread_blended, f, indent=2, default=str)

    # NBA full picks
    if nba_full_blended:
        nba_out = {'sport': 'NBA', 'date': target_date, 'picks': nba_full_blended}
        with open(out_dir / 'nba_picks.json', 'w', encoding='utf-8') as f:
            json.dump(nba_out, f, indent=2, default=str)

    # NCAAB full picks (passthrough)
    ncaab_full = picks.get('ncaab_picks', [])
    if ncaab_full:
        ncaab_out = ncaab_full if isinstance(ncaab_full, dict) else {'sport': 'NCAAB', 'date': target_date, 'picks': ncaab_full}
        with open(out_dir / 'ncaab_picks.json', 'w', encoding='utf-8') as f:
            json.dump(ncaab_out, f, indent=2, default=str)

    # Copy all_picks.json with kalshi annotations
    if picks.get('all_picks'):
        all_data = dict(picks['all_picks'])
        all_data['kalshi_blend'] = True
        all_data['kalshi_blend_timestamp'] = datetime.now(EST).isoformat()
        with open(out_dir / 'all_picks.json', 'w', encoding='utf-8') as f:
            json.dump(all_data, f, indent=2, default=str)

    # Copy other files from engine_only that we don't modify
    for fname in ['autopilot.log', 'dk_parlays.json', 'summary.txt', 'telegram_summary.txt']:
        src = engine_dir / fname
        if src.exists():
            shutil.copy2(src, out_dir / fname)

    # ── Print summary ──
    matched_count = sum(1 for p in nba_spread_blended if p.get('kalshi_home_prob') is not None)
    edge_count = sum(1 for p in nba_spread_blended if p.get('kalshi_edge_flag'))
    changed_count = sum(1 for p in nba_spread_blended if p.get('pick_changed'))

    log.info(f"\n{'='*60}")
    log.info(f"KALSHI BLEND COMPLETE — {target_date}")
    log.info(f"{'='*60}")
    log.info(f"NBA spread picks: {len(nba_spread_blended)} ({matched_count} matched to Kalshi)")
    log.info(f"NCAAB spread picks: {len(ncaab_spread_blended)} (no Kalshi markets)")
    log.info(f"Edge flags (>10% divergence): {edge_count}")
    log.info(f"Picks changed by Kalshi: {changed_count}")

    if edge_count > 0:
        log.info(f"\n🔥 EDGE OPPORTUNITIES:")
        for p in nba_spread_blended:
            if p.get('kalshi_edge_flag'):
                home = p.get('home_team', p.get('home', ''))
                away = p.get('away_team', p.get('away', ''))
                eng_conf = p.get('original_confidence', p.get('confidence', 0))
                kalshi_prob = p.get('kalshi_home_prob', 0) if p.get('predicted_winner', p.get('pick', '')) == home else p.get('kalshi_away_prob', 0)
                log.info(f"  {away} @ {home}: Engine {eng_conf:.0%} vs Kalshi {kalshi_prob:.0%} "
                        f"({p.get('kalshi_edge_direction', '')})")

    if changed_count > 0:
        log.info(f"\n⚡ PICKS CHANGED:")
        for p in nba_spread_blended:
            if p.get('pick_changed'):
                home = p.get('home_team', p.get('home', ''))
                away = p.get('away_team', p.get('away', ''))
                log.info(f"  {away} @ {home}: {p.get('original_pick')} → {p.get('predicted_winner', p.get('pick', ''))}")

    # ── Generate comparison.md ──
    generate_comparison(target_date, nba_spread, nba_spread_blended, ncaab_spread, ncaab_spread_blended)

    return {
        'nba_matched': matched_count,
        'nba_total': len(nba_spread_blended),
        'ncaab_total': len(ncaab_spread_blended),
        'edges': edge_count,
        'changes': changed_count,
    }


def generate_comparison(target_date: str, 
                        nba_engine: list, nba_blended: list,
                        ncaab_engine: list, ncaab_blended: list):
    """Generate comparison.md in the engine directory."""
    lines = [
        f"# A/B Test Comparison: Engine vs Engine+Kalshi — {target_date}",
        "",
        "## Overview",
        "- **Engine Only**: Our 38-factor model with upset composite, injury adjustments, totals v3",
        "- **Engine + Kalshi**: Same model blended with Kalshi prediction market consensus (75% engine / 25% Kalshi)",
        "- **Kalshi Coverage**: NBA game-by-game moneyline markets only (no NCAAB, no spreads, no totals)",
        "",
        "---",
        "",
        "## NBA Spread Picks",
        "",
        f"| Game | Engine Pick | Engine Conf | Kalshi Home% | Kalshi Away% | Blended Conf | Changed? | Edge? |",
        f"|------|-----------|------------|-------------|-------------|-------------|---------|-------|",
    ]

    for i, bp in enumerate(nba_blended):
        home = bp.get('home_team', bp.get('home', ''))
        away = bp.get('away_team', bp.get('away', ''))
        game_str = f"{away} @ {home}"
        
        eng_pick = nba_engine[i].get('predicted_winner', nba_engine[i].get('pick', '')) if i < len(nba_engine) else '?'
        eng_conf = nba_engine[i].get('confidence', nba_engine[i].get('enhanced_prob', 0)) if i < len(nba_engine) else 0
        
        kh = bp.get('kalshi_home_prob', '-')
        ka = bp.get('kalshi_away_prob', '-')
        bc = bp.get('blended_confidence', bp.get('confidence', 0))
        changed = "⚡ YES" if bp.get('pick_changed') else ""
        edge = "🔥" if bp.get('kalshi_edge_flag') else ""
        
        kh_str = f"{kh:.0%}" if isinstance(kh, float) else str(kh)
        ka_str = f"{ka:.0%}" if isinstance(ka, float) else str(ka)
        
        lines.append(f"| {game_str} | {eng_pick} | {eng_conf:.0%} | {kh_str} | {ka_str} | {bc:.0%} | {changed} | {edge} |")

    lines.extend([
        "",
        "## NCAAB Spread Picks",
        "",
        "⚠️ **No Kalshi NCAAB game markets available.** All NCAAB picks pass through unchanged.",
        "",
        f"| Game | Engine Pick | Engine Conf |",
        f"|------|-----------|------------|",
    ])

    for p in ncaab_blended:
        home = p.get('home_team', p.get('home', ''))
        away = p.get('away_team', p.get('away', ''))
        pick_team = p.get('predicted_winner', p.get('pick', ''))
        conf = p.get('confidence', p.get('enhanced_prob', 0))
        lines.append(f"| {away} @ {home} | {pick_team} | {conf:.0%} |")

    # Confidence changes summary
    lines.extend([
        "",
        "## Confidence Changes Summary (NBA only)",
        "",
    ])

    changes = []
    for i, bp in enumerate(nba_blended):
        if bp.get('kalshi_home_prob') is None:
            continue
        eng_conf = bp.get('original_confidence', 0)
        blend_conf = bp.get('blended_confidence', 0)
        diff = blend_conf - eng_conf
        if abs(diff) > 0.005:
            home = bp.get('home_team', bp.get('home', ''))
            away = bp.get('away_team', bp.get('away', ''))
            direction = "↑" if diff > 0 else "↓"
            changes.append((f"{away} @ {home}", eng_conf, blend_conf, diff, direction))

    if changes:
        lines.append(f"| Game | Engine | Blended | Change |")
        lines.append(f"|------|--------|---------|--------|")
        for game, ec, bc, diff, d in sorted(changes, key=lambda x: abs(x[3]), reverse=True):
            lines.append(f"| {game} | {ec:.0%} | {bc:.0%} | {d} {abs(diff):.1%} |")
    else:
        lines.append("No significant confidence changes.")

    # Edge opportunities
    edges = [p for p in nba_blended if p.get('kalshi_edge_flag')]
    if edges:
        lines.extend([
            "",
            "## 🔥 Potential Edge Opportunities (>10% divergence)",
            "",
        ])
        for p in edges:
            home = p.get('home_team', p.get('home', ''))
            away = p.get('away_team', p.get('away', ''))
            eng_conf = p.get('original_confidence', 0)
            div = p.get('kalshi_divergence', 0)
            direction = p.get('kalshi_edge_direction', '')
            lines.append(f"- **{away} @ {home}**: {div:.0%} divergence ({direction})")
            if direction == 'ENGINE_HIGHER':
                lines.append(f"  - Our model is MORE confident than the market → possible value bet")
            else:
                lines.append(f"  - Market is MORE confident → our model may be undervaluing")

    lines.extend([
        "",
        "---",
        f"*Generated {datetime.now(EST).strftime('%Y-%m-%d %I:%M %p ET')}*",
        f"*Kalshi API: public, no auth required. NBA game markets only (KXNBAGAME series).*",
    ])

    comparison_file = ENGINE_DIR / "comparison.md"
    with open(comparison_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    log.info(f"\n📄 Saved comparison.md")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate Engine+Kalshi blended picks')
    parser.add_argument('--date', default=None, help='Target date (YYYY-MM-DD)')
    args = parser.parse_args()
    
    result = run_blend(args.date)
    if result:
        print(f"\n✅ Done! NBA: {result['nba_matched']}/{result['nba_total']} matched, "
              f"{result['edges']} edges, {result['changes']} picks changed")
