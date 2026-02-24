"""Backtest new NBA upset composite v2 against Feb 22 — using real ML odds."""
import json, logging, re
logging.basicConfig(level=logging.INFO, format="%(message)s")

from nba_upset_composite import (
    fetch_nba_standings, fetch_yesterday_games, compute_nba_upset_composite
)

def american_to_prob(odds_str):
    odds = int(str(odds_str).replace('\u2212', '-').replace('−', '-').replace('+', ''))
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)

def devig(p1, p2):
    total = p1 + p2
    return p1/total, p2/total

with open('analyzed_games.json') as f:
    all_picks = json.load(f)

nba_picks = [p for p in all_picks if p.get('sport') == 'NBA']

RESULTS = {
    'OKC Thunder': 8, 'CLE Cavaliers': -8,
    'ATL Hawks': 11, 'BKN Nets': -11,
    'TOR Raptors': 28, 'MIL Bucks': -28,
    'GS Warriors': 11, 'DEN Nuggets': -11,
    'DAL Mavericks': 4, 'IND Pacers': -4,
    'CHA Hornets': 17, 'WAS Wizards': -17,
    'BOS Celtics': 22, 'LA Lakers': -22,
    'PHI 76ers': 27, 'MIN Timberwolves': -27,
    'NY Knicks': 6, 'CHI Bulls': -6,
    'POR Trail Blazers': 15, 'PHO Suns': -15,
    'ORL Magic': 2, 'LA Clippers': -2,
}

standings = fetch_nba_standings()
b2b_teams = set()  # Historical B2B not available

print("\n" + "=" * 70)
print("NBA UPSET COMPOSITE v2 — BACKTEST Feb 22 (REAL ML ODDS)")
print("=" * 70)

flagged_hits = 0
flagged_misses = 0
unflagged_hits = 0
unflagged_misses = 0

for pick in nba_picks:
    home = pick['home_team']
    away = pick['away_team']
    spread = pick['spread_home']
    predicted = pick['predicted_winner']
    pick_spread = pick['pick_spread']
    
    # Get real ML probs from the pick data
    home_ml_raw = pick.get('home_ml', '+100')
    away_ml_raw = pick.get('away_ml', '-100')
    h_prob = american_to_prob(home_ml_raw)
    a_prob = american_to_prob(away_ml_raw)
    home_prob, away_prob = devig(h_prob, a_prob)
    
    # Build game dict
    game = {
        'home': home,
        'away': away,
        'spread': spread,
        'pick': predicted,
        'cover_prob': pick['confidence'],
        'enhanced_prob': pick['confidence'],
        'ml_home_prob': home_prob,
        'ml_away_prob': away_prob,
        'sport': 'NBA',
    }
    
    score, reasons, is_upset = compute_nba_upset_composite(
        game, standings, b2b_teams, {}
    )
    
    # Check cover
    margin = RESULTS.get(predicted, 0)
    if pick_spread > 0:
        covered = (margin + pick_spread) > 0
    else:
        covered = margin > 0
    
    result_emoji = "✅" if covered else "❌"
    flag_emoji = "🔥" if is_upset else "  "
    old_score = pick.get('upset_composite_score', 0)
    old_flag = "🔥" if pick.get('is_upset_play') else "  "
    
    print(f"\n{result_emoji} {predicted} ({pick_spread:+.1f}) vs {away if predicted == home else home}")
    print(f"   ML probs: H={home_prob:.0%} A={away_prob:.0%}")
    print(f"   OLD: {old_score:.2f} {old_flag}  →  NEW: {score:.0%} {flag_emoji}")
    for r in reasons[:4]:
        print(f"   {r}")
    
    if is_upset:
        if covered: flagged_hits += 1
        else: flagged_misses += 1
    else:
        if covered: unflagged_hits += 1
        else: unflagged_misses += 1

total_flagged = flagged_hits + flagged_misses
total_unflagged = unflagged_hits + unflagged_misses
print("\n" + "=" * 70)
print(f"NEW COMPOSITE:")
print(f"  Flagged: {total_flagged}/{len(nba_picks)} ({total_flagged/len(nba_picks):.0%})")
print(f"  Flagged HIT: {flagged_hits}/{max(total_flagged,1)} ({flagged_hits/max(total_flagged,1):.0%})")
print(f"  Unflagged HIT: {unflagged_hits}/{max(total_unflagged,1)} ({unflagged_hits/max(total_unflagged,1):.0%})")
print(f"\nOLD: flagged {sum(1 for p in nba_picks if p.get('is_upset_play'))}/{len(nba_picks)}")
