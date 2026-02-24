"""Backtest new NBA upset composite v2 against Feb 22 picks."""
import json, logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from nba_upset_composite import (
    fetch_nba_standings, fetch_yesterday_games, compute_nba_upset_composite
)

# Load Feb 22 NBA picks
with open('picks_2026-02-22/nba_spread_picks.json') as f:
    picks = json.load(f)

# Actual results (Feb 22)
RESULTS = {
    'OKC Thunder': {'won': True, 'margin': 8, 'score': '121-113'},      # OKC 121, CLE 113
    'CLE Cavaliers': {'won': False, 'margin': -8},
    'ATL Hawks': {'won': True, 'margin': 11},      # ATL 115, BKN 104
    'BKN Nets': {'won': False, 'margin': -11},
    'TOR Raptors': {'won': True, 'margin': 28},    # TOR 122, MIL 94
    'MIL Bucks': {'won': False, 'margin': -28},
    'GS Warriors': {'won': True, 'margin': 11},    # GS 128, DEN 117
    'DEN Nuggets': {'won': False, 'margin': -11},
    'DAL Mavericks': {'won': True, 'margin': 4},   # DAL 134, IND 130
    'IND Pacers': {'won': False, 'margin': -4},
    'CHA Hornets': {'won': True, 'margin': 17},    # CHA 129, WAS 112
    'WAS Wizards': {'won': False, 'margin': -17},
    'BOS Celtics': {'won': True, 'margin': 22},    # BOS 111, LAL 89
    'LA Lakers': {'won': False, 'margin': -22},
    'PHI 76ers': {'won': True, 'margin': 27},      # PHI 135, MIN 108
    'MIN Timberwolves': {'won': False, 'margin': -27},
    'NY Knicks': {'won': True, 'margin': 6},       # NYK 105, CHI 99
    'CHI Bulls': {'won': False, 'margin': -6},
    'POR Trail Blazers': {'won': True, 'margin': 15},  # POR 92, PHX 77
    'PHO Suns': {'won': False, 'margin': -15},
    'ORL Magic': {'won': True, 'margin': 2},       # ORL 111, LAC 109
    'LA Clippers': {'won': False, 'margin': -2},
}

standings = fetch_nba_standings()
# For B2B, we'd need Feb 21 games. Use empty set since we're backtesting
b2b_teams = set()  # Can't get historical B2B easily

print("\n" + "=" * 70)
print("NBA UPSET COMPOSITE v2 — BACKTEST Feb 22, 2026")
print("=" * 70)

hits = 0
misses = 0
flagged = 0
not_flagged = 0

for pick in picks:
    home = pick['home_team']
    away = pick['away_team']
    spread = pick.get('spread_home', pick.get('pick_spread', 0))
    
    # Build a game dict compatible with the composite function
    game = {
        'home': home,
        'away': away,
        'spread': spread if 'spread_home' in pick else (-pick['pick_spread'] if pick['predicted_winner'] == away else pick['pick_spread']),
        'pick': pick['predicted_winner'],
        'cover_prob': pick['confidence'],
        'enhanced_prob': pick['confidence'],
        'ml_home_prob': 0.5,  # Approximate from spread
        'ml_away_prob': 0.5,
        'sport': 'NBA',
    }
    
    # Reconstruct spread from pick data
    if pick.get('pick_spread'):
        ps = pick['pick_spread']
        if ps > 0:  # Dog pick
            game['spread'] = ps if pick['predicted_winner'] == home else -ps
        else:
            game['spread'] = ps if pick['predicted_winner'] == home else -ps
    
    # Use upset_composite_score from original pick for ML prob approximation
    orig_score = pick.get('upset_composite_score', 0)
    
    # Better: use actual spread to estimate ML probs
    abs_spread = abs(game['spread'])
    if game['spread'] < 0:
        # Home favored
        home_ml = 0.5 + abs_spread * 0.03  # rough: 3% per point
        game['ml_home_prob'] = min(home_ml, 0.85)
        game['ml_away_prob'] = 1 - game['ml_home_prob']
    else:
        # Away favored
        away_ml = 0.5 + abs_spread * 0.03
        game['ml_away_prob'] = min(away_ml, 0.85)
        game['ml_home_prob'] = 1 - game['ml_away_prob']
    
    score, reasons, is_upset = compute_nba_upset_composite(
        game, standings, b2b_teams, {}
    )
    
    # Check if pick covered
    predicted = pick['predicted_winner']
    pick_spread = pick['pick_spread']
    
    result = RESULTS.get(predicted)
    if result:
        margin = result['margin']
        covered = margin + pick_spread > 0 if pick_spread > 0 else margin > 0
        # For dogs: margin + spread > 0 means covered
        # e.g. PHX +3.5, lost by 15 → -15 + 3.5 = -11.5 → no cover
        # e.g. CHI +10.5, lost by 6 → -6 + 10.5 = +4.5 → covered
        if pick_spread > 0:
            covered = margin + pick_spread > 0
        else:
            covered = margin > 0
    else:
        covered = False
    
    old_flag = pick.get('is_upset_play', False)
    result_emoji = "✅" if covered else "❌"
    flag_emoji = "🔥" if is_upset else "  "
    old_emoji = "🔥" if old_flag else "  "
    
    print(f"\n{result_emoji} {predicted} ({pick_spread:+.1f}) vs {away if predicted == home else home}")
    print(f"   OLD composite: {orig_score:.2f} {old_emoji}  →  NEW composite: {score:.2%} {flag_emoji}")
    if reasons:
        for r in reasons[:4]:
            print(f"   {r}")
    
    if is_upset:
        flagged += 1
        if covered:
            hits += 1
        else:
            misses += 1
    else:
        not_flagged += 1

print("\n" + "=" * 70)
print(f"NEW COMPOSITE RESULTS:")
print(f"  Flagged as upset: {flagged}/{len(picks)} ({flagged/len(picks):.0%})")
print(f"  Upset picks that HIT: {hits}/{flagged if flagged else 1} ({hits/max(flagged,1):.0%})")
print(f"  Not flagged: {not_flagged}/{len(picks)}")
print(f"\nOLD COMPOSITE flagged: {sum(1 for p in picks if p.get('is_upset_play'))}/{len(picks)}")
