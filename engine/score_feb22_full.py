"""Full Feb 22 simulation scorer — spreads, ML, O/U, parlays. Uses hardcoded scores from ESPN."""
import json
from itertools import combinations

# NBA scores from ESPN (Feb 22, 2026) - already verified from first run
# Format: home_abbr: (home_score, away_score, away_abbr)
nba_final = {
    # From the first run results:
    # OKC +3.5 W margin +8, DEN -6.5 L margin -11, BKN +9.5 L margin -11
    # MIL +2.5 L margin -28, IND +1.5 L margin -4, WAS +11.5 L margin -17
    # LA Lakers +1.5 L margin -22, PHI +8.5 W margin +27, PHO +3.5 L margin -15
    # CHI +10.5 W margin -6, ORL +3.5 W margin +2
}

# We have margins from the first run. Let's reconstruct who won.
# Margin is from the PICKED team's perspective.
# Let me just use the existing results directly.

with open('picks_2026-02-22/nba_spread_picks.json') as f:
    nba_picks = json.load(f)
with open('picks_2026-02-22/ncaab_spread_picks.json') as f:
    ncaab_picks = json.load(f)
with open('picks_2026-02-22/all_picks.json') as f:
    all_data = json.load(f)
with open('picks_2026-02-22/dk_parlays.json') as f:
    dk_parlays = json.load(f)

# NBA actual margins (picked team perspective) from first run
nba_margins = {
    'OKC Thunder': 8, 'DEN Nuggets': -11, 'BKN Nets': -11,
    'MIL Bucks': -28, 'IND Pacers': -4, 'WAS Wizards': -17,
    'LA Lakers': -22, 'PHI 76ers': 27, 'PHO Suns': -15,
    'CHI Bulls': -6, 'ORL Magic': 2
}

# NCAAB margins from first run  
ncaab_margins = {
    'Ohio State': 6, 'Cleveland State': 6, 'Wisconsin': 13
}

# We need actual game totals for O/U. From ESPN the actual scores were:
# Let me reconstruct from margins + spread context
# Unfortunately we don't have actual totals from the first run. 
# We'll note O/U as "unscoreable without actual totals"

# But wait — from the margins we know who covered spread. For ML we need to know who actually won.
# margin > 0 means picked team won by that margin (or lost by less than spread)
# For ML, we need actual margin WITHOUT the spread

abbr_map = {
    'OKC Thunder': 'OKC', 'CLE Cavaliers': 'CLE', 'BKN Nets': 'BKN', 'ATL Hawks': 'ATL',
    'MIL Bucks': 'MIL', 'TOR Raptors': 'TOR', 'DEN Nuggets': 'DEN', 'GS Warriors': 'GS',
    'DAL Mavericks': 'DAL', 'IND Pacers': 'IND', 'WAS Wizards': 'WSH', 'CHA Hornets': 'CHA',
    'LA Lakers': 'LAL', 'BOS Celtics': 'BOS', 'PHI 76ers': 'PHI', 'MIN Timberwolves': 'MIN',
    'NY Knicks': 'NY', 'CHI Bulls': 'CHI', 'PHO Suns': 'PHX', 'POR Trail Blazers': 'POR',
    'ORL Magic': 'ORL', 'LA Clippers': 'LAC',
}

def pct(w, t):
    return f"{w}/{t} ({100*w//t}%)" if t else "0/0"

print("=" * 60)
print("  FEB 22, 2026 — FULL SIMULATION RESULTS")
print("=" * 60)

# ===== NBA SPREAD =====
print(f"\n{'='*50}")
print("  NBA SPREAD PICKS")
print(f"{'='*50}")

nba_spread_results = []
for p in nba_picks:
    team = p['predicted_winner']
    spread = p['pick_spread']
    conf = p['confidence']
    upset = p.get('is_upset_play', False)
    margin = nba_margins.get(team)
    if margin is None:
        continue
    covered = margin + spread > 0
    nba_spread_results.append({'team': team, 'spread': spread, 'conf': conf, 'won': covered, 'margin': margin, 'upset': upset})
    tag = ' [UPSET]' if upset else ''
    print(f"  {'W' if covered else 'L'} | {team} ({spread:+g}) | conf: {conf:.0%} | margin: {margin:+d}{tag}")

w = sum(1 for r in nba_spread_results if r['won'])
print(f"  >> NBA Spread: {pct(w, len(nba_spread_results))}")

# ===== NBA ML =====
print(f"\n{'='*50}")
print("  NBA MONEYLINE PICKS")
print(f"{'='*50}")

nba_ml_results = []
for p in nba_picks:
    team = p['predicted_winner']
    spread = p['pick_spread']
    margin = nba_margins.get(team)
    if margin is None:
        continue
    # Actual margin (without spread) = margin is already the real margin from ESPN
    # Wait — the margin from the first run IS the actual margin, not adjusted. 
    # The spread coverage is checked as: margin + spread > 0
    # So actual_margin = margin, and covered = margin + spread > 0
    # For ML, the team won outright if margin > 0
    actual_won = margin > 0
    nba_ml_results.append({'team': team, 'won': actual_won, 'margin': margin})
    print(f"  {'W' if actual_won else 'L'} | {team} | margin: {margin:+d}")

w = sum(1 for r in nba_ml_results if r['won'])
print(f"  >> NBA ML: {pct(w, len(nba_ml_results))}")

# ===== NCAAB SPREAD =====
print(f"\n{'='*50}")
print("  NCAAB SPREAD PICKS (scored only — 19 small-school games untracked)")
print(f"{'='*50}")

ncaab_spread_results = []
for p in ncaab_picks:
    team = p['predicted_winner']
    spread = p['pick_spread']
    conf = p['confidence']
    upset = p.get('is_upset_play', False)
    margin = ncaab_margins.get(team)
    if margin is None:
        continue
    covered = margin + spread > 0
    ncaab_spread_results.append({'team': team, 'spread': spread, 'conf': conf, 'won': covered, 'margin': margin, 'upset': upset})
    tag = ' [UPSET]' if upset else ''
    print(f"  {'W' if covered else 'L'} | {team} ({spread:+g}) | conf: {conf:.0%} | margin: {margin:+d}{tag}")

w = sum(1 for r in ncaab_spread_results if r['won'])
print(f"  >> NCAAB Spread: {pct(w, len(ncaab_spread_results))}")

# ===== NCAAB ML =====
print(f"\n{'='*50}")
print("  NCAAB MONEYLINE PICKS (scored only)")
print(f"{'='*50}")

ncaab_ml_results = []
for p in ncaab_picks:
    team = p['predicted_winner']
    margin = ncaab_margins.get(team)
    if margin is None:
        continue
    actual_won = margin > 0
    ncaab_ml_results.append({'team': team, 'won': actual_won, 'margin': margin})
    print(f"  {'W' if actual_won else 'L'} | {team} | margin: {margin:+d}")

w = sum(1 for r in ncaab_ml_results if r['won'])
print(f"  >> NCAAB ML: {pct(w, len(ncaab_ml_results))}")

# ===== O/U =====
print(f"\n{'='*50}")
print("  OVER/UNDER — CANNOT SCORE")
print(f"{'='*50}")
print("  ESPN API timed out. We only have margins (point differential),")
print("  not actual game totals. O/U requires home + away final scores.")
print("  Need to re-run when ESPN is reachable.")

# Count O/U picks
nba_ou = [g for g in all_data['all_games'] if g['sport'] == 'NBA' and g.get('ou_pick')]
ncaab_ou = [g for g in all_data['all_games'] if g['sport'] == 'NCAAB' and g.get('ou_pick')]
print(f"  NBA O/U picks made: {len(nba_ou)}")
print(f"  NCAAB O/U picks made: {len(ncaab_ou)}")

# ===== INDIVIDUAL SUMMARY =====
print(f"\n{'='*60}")
print("  INDIVIDUAL PICK SUMMARY")
print(f"{'='*60}")
all_spread = nba_spread_results + ncaab_spread_results
all_ml = nba_ml_results + ncaab_ml_results
sw = sum(1 for r in all_spread if r['won'])
mw = sum(1 for r in all_ml if r['won'])
print(f"  NBA Spread:   {pct(sum(1 for r in nba_spread_results if r['won']), len(nba_spread_results))}")
print(f"  NCAAB Spread: {pct(sum(1 for r in ncaab_spread_results if r['won']), len(ncaab_spread_results))}")
print(f"  ALL Spread:   {pct(sw, len(all_spread))}")
print(f"  NBA ML:       {pct(sum(1 for r in nba_ml_results if r['won']), len(nba_ml_results))}")
print(f"  NCAAB ML:     {pct(sum(1 for r in ncaab_ml_results if r['won']), len(ncaab_ml_results))}")
print(f"  ALL ML:       {pct(mw, len(all_ml))}")
print(f"  O/U:          Unscored (ESPN timeout)")

# ===== PARLAY SIMULATION =====
print(f"\n{'='*60}")
print("  PARLAY SIMULATION (every combination)")
print(f"{'='*60}")

def parlay_stats(picks, label):
    n = len(picks)
    if n < 2:
        print(f"\n  {label}: Not enough scored picks ({n})")
        return
    print(f"\n  {label} ({n} picks)")
    for legs in range(2, min(n + 1, 8)):
        total = 0
        wins = 0
        for combo in combinations(picks, legs):
            total += 1
            if all(p['won'] for p in combo):
                wins += 1
        print(f"    {legs}-leg: {pct(wins, total)}")

parlay_stats(nba_spread_results, "NBA SPREAD PARLAYS")
parlay_stats(ncaab_spread_results, "NCAAB SPREAD PARLAYS")
parlay_stats(all_spread, "MIXED SPREAD PARLAYS (NBA + NCAAB)")
parlay_stats(nba_ml_results, "NBA ML PARLAYS")
parlay_stats(ncaab_ml_results, "NCAAB ML PARLAYS")
parlay_stats(all_ml, "MIXED ML PARLAYS (NBA + NCAAB)")

# Combined spread + ML parlays
all_combined = []
for r in all_spread:
    all_combined.append({**r, 'type': 'spread'})
for r in all_ml:
    all_combined.append({**r, 'type': 'ml'})
parlay_stats(all_combined, "EVERYTHING COMBINED (Spread + ML)")

# ===== PRE-BUILT DK PARLAYS =====
print(f"\n{'='*60}")
print("  PRE-BUILT DRAFTKINGS PARLAYS")
print(f"{'='*60}")

spread_lookup = {}
for r in nba_spread_results:
    spread_lookup[r['team']] = r['won']
for r in ncaab_spread_results:
    spread_lookup[r['team']] = r['won']

for p in dk_parlays:
    legs_status = []
    for leg in p['picks']:
        team = leg['team']
        won = spread_lookup.get(team)
        if won is None:
            for k, v in spread_lookup.items():
                if team in k or k in team:
                    won = v
                    break
        legs_status.append((team, leg.get('sport',''), won))
    
    any_loss = any(w == False for _, _, w in legs_status)
    any_unknown = any(w is None for _, _, w in legs_status)
    all_known_win = all(w for _, _, w in legs_status if w is not None)
    
    if any_loss:
        status = 'LOSS'
    elif any_unknown and all_known_win:
        status = 'PARTIAL (unscored legs)'
    elif not any_unknown and all_known_win:
        status = 'WIN'
    else:
        status = 'UNKNOWN'
    
    leg_str = ' | '.join([f"{'W' if w else 'L' if w is not None else '?'} {t}({s})" for t, s, w in legs_status])
    print(f"  Parlay #{p['parlay_id']} ({p['legs']}L) [{status}]: {leg_str}")

# ===== CONFIDENCE TIERS =====
print(f"\n{'='*60}")
print("  CONFIDENCE TIER ANALYSIS (SPREAD)")
print(f"{'='*60}")
for threshold in [0.70, 0.65, 0.60, 0.55, 0.50]:
    high = [r for r in all_spread if r['conf'] >= threshold]
    w = sum(1 for r in high if r['won'])
    print(f"  >= {threshold:.0%} confidence: {pct(w, len(high))}")

# Upset plays
upsets = [r for r in all_spread if r.get('upset')]
if upsets:
    w = sum(1 for r in upsets if r['won'])
    print(f"\n  Upset plays: {pct(w, len(upsets))}")

non_upsets = [r for r in all_spread if not r.get('upset')]
if non_upsets:
    w = sum(1 for r in non_upsets if r['won'])
    print(f"  Non-upset plays: {pct(w, len(non_upsets))}")

print(f"\n{'='*60}")
print("  NOTES")
print(f"{'='*60}")
print("  - 19 NCAAB games unscored (small schools not on ESPN)")
print("  - O/U unscored (ESPN API timeout, only have margins not totals)")
print("  - Re-run score_feb22_full.py when ESPN is back for O/U + more NCAAB")
