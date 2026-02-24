"""
Daily Picks Generator v3 — ParlayGuarantee
Generates ALL picks for the day with ISOLATED categories.

Categories (never mixed until O/U proves 55%+):
  1. NBA Spread/ML picks → NBA-only parlays
  2. NCAAB Spread/ML picks → NCAAB-only parlays
  3. Mixed NBA+NCAAB Spread/ML parlays
  4. NBA O/U picks → NBA O/U parlays (ISOLATED)
  5. NCAAB O/U picks → NCAAB O/U parlays (ISOLATED)

Usage:
  python daily_picks_v3.py                    # Today
  python daily_picks_v3.py --date 2026-02-21  # Specific date
"""

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import logging
import os
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent


def load_spread_picks(sport: str, target_date: date) -> List[Dict]:
    """Load spread/ML picks from existing engines."""
    if sport == 'nba':
        path = ENGINE_DIR / f"demo_picks_{target_date}.json"
        if not path.exists():
            path = ENGINE_DIR / "picks_output.json"
        if not path.exists():
            logger.warning(f"No NBA spread picks found. Run: python engine_v2.py --date {target_date}")
    else:
        path = ENGINE_DIR / f"ncaab_picks_{target_date}.json"
        if not path.exists():
            path = ENGINE_DIR / "ncaab_picks_output.json"
        if not path.exists():
            logger.warning(f"No NCAAB spread picks found. Run: python ncaab_engine.py")

    if path.exists():
        with open(path) as f:
            raw = json.load(f)
        
        # Normalize format — engine_v2 wraps picks in a dict
        if isinstance(raw, dict):
            picks = raw.get('all_games', raw.get('games_today', []))
        elif isinstance(raw, list):
            picks = raw
        else:
            picks = []

        # Normalize field names to standard format
        normalized = []
        for p in picks:
            if isinstance(p, str):
                continue
            normalized.append({
                'home_team': p.get('home_team', p.get('home', '')),
                'away_team': p.get('away_team', p.get('away', '')),
                'predicted_winner': p.get('predicted_winner', p.get('pick', '')),
                'confidence': p.get('confidence', p.get('win_prob', 0.5)),
                'spread': p.get('spread', 0),
                'spread_pick': p.get('spread_pick', p.get('pick', '')),
                'game_date': p.get('game_date', target_date.isoformat()),
            })

        logger.info(f"Loaded {len(normalized)} {sport.upper()} spread/ML picks")
        return normalized
    else:
        logger.warning(f"No {sport} spread picks found")
        return []


def load_ou_picks(sport: str, target_date: date) -> List[Dict]:
    """Load O/U picks from totals_engine_v3."""
    path = ENGINE_DIR / f"totals_v3_{sport}_{target_date}.json"
    if not path.exists():
        logger.warning(f"No {sport} O/U picks found. Run: python totals_engine_v3.py {'--ncaab' if sport == 'ncaab' else ''} --date {target_date}")

    if path.exists():
        with open(path) as f:
            all_picks = json.load(f)
        # Filter to actionable picks only (no PASS)
        actionable = [p for p in all_picks if p.get('pick', 'PASS') != 'PASS']
        logger.info(f"Loaded {len(actionable)} actionable {sport.upper()} O/U picks")
        return actionable
    else:
        logger.warning(f"No {sport} O/U picks found")
        return []


def generate_parlays(picks: List[Dict], min_legs: int = 2, max_legs: int = 10,
                     pick_type: str = 'spread') -> List[Dict]:
    """Generate all unique parlay combinations from a set of picks.
    
    For spread/ML: uses predicted_winner + confidence
    For O/U: uses pick (OVER/UNDER) + confidence
    """
    if len(picks) < min_legs:
        return []

    actual_max = min(max_legs, len(picks))
    parlays = []

    for num_legs in range(min_legs, actual_max + 1):
        for combo in combinations(range(len(picks)), num_legs):
            legs = [picks[i] for i in combo]

            if pick_type == 'ou':
                # O/U parlay
                avg_conf = sum(p.get('confidence', 0.55) for p in legs) / len(legs)
                combined_prob = 1.0
                for p in legs:
                    combined_prob *= p.get('confidence', 0.55)

                leg_details = []
                for p in legs:
                    leg_details.append({
                        'matchup': f"{p.get('away_team','')} @ {p.get('home_team','')}",
                        'pick': f"{p['pick']} {p.get('posted_total', '')}",
                        'edge': p.get('edge', 0),
                        'confidence': p.get('confidence', 0.5),
                        'tier': p.get('tier', ''),
                    })
            else:
                # Spread/ML parlay
                avg_conf = sum(p.get('confidence', 0.55) for p in legs) / len(legs)
                combined_prob = 1.0
                for p in legs:
                    combined_prob *= p.get('confidence', 0.55)

                leg_details = []
                for p in legs:
                    winner = p.get('predicted_winner', p.get('home_team', ''))
                    leg_details.append({
                        'matchup': f"{p.get('away_team','')} @ {p.get('home_team','')}",
                        'pick': winner,
                        'confidence': p.get('confidence', 0.5),
                    })

            # Estimate parlay odds (American)
            # For n-leg parlay at -110 each, odds = (2.0^n - 1) * 100
            decimal_odds = 1.0
            for _ in legs:
                decimal_odds *= 1.91  # -110 juice on each leg
            american_odds = round((decimal_odds - 1) * 100)

            parlays.append({
                'num_legs': num_legs,
                'legs': leg_details,
                'avg_confidence': round(avg_conf, 3),
                'combined_probability': round(combined_prob, 4),
                'estimated_american_odds': f"+{american_odds}",
                'estimated_decimal_odds': round(decimal_odds, 2),
            })

    # Sort by combined probability (best first within each leg count)
    parlays.sort(key=lambda x: (-x['num_legs'], -x['combined_probability']))

    logger.info(f"Generated {len(parlays)} {pick_type} parlays")
    return parlays


def filter_by_sportsbook(picks: List[Dict], sportsbook: str) -> List[Dict]:
    """Filter picks to only games available on the specified sportsbook."""
    if not sportsbook:
        return picks
    return [p for p in picks if sportsbook in p.get('available_books', [])]


def run(target_date: date, sportsbook: str = ""):
    """Generate everything for a date. If sportsbook is specified, only use games on that book."""
    out_dir = ENGINE_DIR / f"picks_{target_date}"
    out_dir.mkdir(exist_ok=True)

    # ─── Load all picks ───
    nba_spread = load_spread_picks('nba', target_date)
    ncaab_spread = load_spread_picks('ncaab', target_date)
    nba_ou = load_ou_picks('nba', target_date)
    ncaab_ou = load_ou_picks('ncaab', target_date)

    # Filter by sportsbook if specified
    if sportsbook:
        logger.info(f"Filtering to sportsbook: {sportsbook}")
        nba_spread = filter_by_sportsbook(nba_spread, sportsbook)
        ncaab_spread = filter_by_sportsbook(ncaab_spread, sportsbook)
        nba_ou = filter_by_sportsbook(nba_ou, sportsbook)
        ncaab_ou = filter_by_sportsbook(ncaab_ou, sportsbook)
        logger.info(f"After filter: NBA={len(nba_spread)}, NCAAB={len(ncaab_spread)}, NBA O/U={len(nba_ou)}, NCAAB O/U={len(ncaab_ou)}")

    # ─── Save straight picks ───
    save(out_dir / "nba_spreads.json", nba_spread)
    save(out_dir / "ncaab_spreads.json", ncaab_spread)
    save(out_dir / "nba_totals.json", nba_ou)
    save(out_dir / "ncaab_totals.json", ncaab_ou)

    # ─── Generate parlays ───
    # Cap picks used in parlays to top-confidence to avoid combinatorial explosion
    nba_spread_top = sorted(nba_spread, key=lambda x: x.get('confidence', 0), reverse=True)[:12]
    ncaab_spread_top = sorted(ncaab_spread, key=lambda x: x.get('confidence', 0), reverse=True)[:12]

    # Spread/ML parlays (NO O/U)
    nba_parlays = generate_parlays(nba_spread_top, 2, 8, 'spread')
    ncaab_parlays = generate_parlays(ncaab_spread_top, 2, 8, 'spread')
    mixed_spread = nba_spread_top[:6] + ncaab_spread_top[:6]
    mixed_parlays = generate_parlays(mixed_spread, 2, 8, 'spread')

    save(out_dir / "parlays_nba_spread.json", nba_parlays)
    save(out_dir / "parlays_ncaab_spread.json", ncaab_parlays)
    save(out_dir / "parlays_mixed_spread.json", mixed_parlays)

    # O/U parlays (ISOLATED — never mixed with spread/ML)
    nba_ou_top = sorted(nba_ou, key=lambda x: abs(x.get('edge', 0)), reverse=True)[:8]
    ncaab_ou_top = sorted(ncaab_ou, key=lambda x: abs(x.get('edge', 0)), reverse=True)[:8]

    nba_ou_parlays = generate_parlays(nba_ou_top, 2, 6, 'ou')
    ncaab_ou_parlays = generate_parlays(ncaab_ou_top, 2, 6, 'ou')
    mixed_ou = nba_ou_top[:4] + ncaab_ou_top[:4]
    mixed_ou_parlays = generate_parlays(mixed_ou, 2, 6, 'ou')

    save(out_dir / "parlays_nba_ou.json", nba_ou_parlays)
    save(out_dir / "parlays_ncaab_ou.json", ncaab_ou_parlays)
    save(out_dir / "parlays_mixed_ou.json", mixed_ou_parlays)

    # ─── Summary ───
    summary = {
        'date': target_date.isoformat(),
        'straight_picks': {
            'nba_spread': len(nba_spread),
            'ncaab_spread': len(ncaab_spread),
            'nba_ou': len(nba_ou),
            'ncaab_ou': len(ncaab_ou),
        },
        'parlays': {
            'nba_spread': len(nba_parlays),
            'ncaab_spread': len(ncaab_parlays),
            'mixed_spread': len(mixed_parlays),
            'nba_ou': len(nba_ou_parlays),
            'ncaab_ou': len(ncaab_ou_parlays),
            'mixed_ou': len(mixed_ou_parlays),
        },
        'note': 'O/U picks and parlays are ISOLATED from spread/ML. No mixing until O/U proves 55%+ over 7 days.',
    }
    save(out_dir / "summary.json", summary)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  DAILY PICKS — {target_date}")
    print(f"{'='*60}")
    print(f"\n  Straight Picks:")
    print(f"    NBA Spread/ML:   {len(nba_spread)}")
    print(f"    NCAAB Spread/ML: {len(ncaab_spread)}")
    print(f"    NBA O/U:         {len(nba_ou)} (ISOLATED)")
    print(f"    NCAAB O/U:       {len(ncaab_ou)} (ISOLATED)")
    print(f"\n  Parlay Combos:")
    print(f"    NBA Spread:      {len(nba_parlays)}")
    print(f"    NCAAB Spread:    {len(ncaab_parlays)}")
    print(f"    Mixed Spread:    {len(mixed_parlays)}")
    print(f"    NBA O/U:         {len(nba_ou_parlays)}")
    print(f"    NCAAB O/U:       {len(ncaab_ou_parlays)}")
    print(f"    Mixed O/U:       {len(mixed_ou_parlays)}")
    print(f"\n  Output: {out_dir}")
    print(f"{'='*60}")


def save(path: Path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    target = date.today()
    sportsbook_filter = ""
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target = date.fromisoformat(sys.argv[idx + 1])
    if '--sportsbook' in sys.argv:
        idx = sys.argv.index('--sportsbook')
        if idx + 1 < len(sys.argv):
            sportsbook_filter = sys.argv[idx + 1]
    run(target, sportsbook_filter)
