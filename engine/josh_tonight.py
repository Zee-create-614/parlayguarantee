#!/usr/bin/env python3
"""Generate Josh's unique parlays for tonight — diversified, no repeated favorites."""
import json, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

with open(Path(__file__).parent / 'analyzed_games.json', encoding='utf-8') as f:
    ALL_GAMES = json.load(f)

# Build all possible legs
spread_legs = []
for g in ALL_GAMES:
    prob = g.get('enhanced_prob', g.get('cover_prob', 0.5))
    spread_legs.append({
        'id': f"SP_{g['home']}",
        'team': g['pick'], 'spread': g.get('spread_str', ''),
        'prob': prob, 'sport': g['sport'],
        'home': g['home'], 'away': g['away'],
        'matchup': f"{g['away']} @ {g['home']}",
        'bet_type': 'spread',
    })

ou_legs = []
for g in ALL_GAMES:
    v3 = g.get('ou_model_v3', {})
    if v3.get('pick', 'PASS') != 'PASS':
        ou_legs.append({
            'id': f"OU_{g['home']}",
            'team': f"{g['home']} vs {g['away']}",
            'spread': f"{v3['pick']} {v3.get('posted_total', g.get('total_line', 0))}",
            'prob': v3.get('confidence', 0.5),
            'sport': g['sport'],
            'home': g['home'], 'away': g['away'],
            'matchup': f"{g['away']} @ {g['home']}",
            'bet_type': 'ou',
            'edge': v3.get('edge', 0),
        })

# Sort by confidence
spread_legs.sort(key=lambda x: x['prob'], reverse=True)
ou_legs.sort(key=lambda x: x['prob'], reverse=True)

# Tag tiers
nba_spreads = [l for l in spread_legs if l['sport'] == 'NBA']
ncaab_spreads = [l for l in spread_legs if l['sport'] == 'NCAAB']
nba_ou = [l for l in ou_legs if l['sport'] == 'NBA']
ncaab_ou = [l for l in ou_legs if l['sport'] == 'NCAAB']

# MANUALLY CURATE diversified tickets
# Rule: no game appears in more than 2-3 tickets (except hail mary)
# Mix spread AND O/U picks across tickets

tickets = []

# ── TICKET 1: 3-leg (NCAAB spread + NBA O/U) ──
tickets.append({
    'name': '3-Leg A (NCAAB Spread + NBA O/U)',
    'legs': [ncaab_spreads[0], ncaab_spreads[1], nba_ou[0]]  # Top 2 NCAAB spreads + best NBA O/U
})

# ── TICKET 2: 3-leg (NBA spread + NCAAB O/U) ──
tickets.append({
    'name': '3-Leg B (NBA Spread + NCAAB O/U)',
    'legs': [nba_spreads[0], ncaab_ou[0], ncaab_ou[1]]
})

# ── TICKET 3: 3-leg (Mixed O/U locks) ──
tickets.append({
    'name': '3-Leg C (O/U Locks)',
    'legs': [ou_legs[0], ou_legs[1], ou_legs[2]]  # Top 3 O/U by confidence
})

# ── TICKET 4: 4-leg (NCAAB heavy spread) ──
tickets.append({
    'name': '4-Leg (NCAAB Spread Heavy)',
    'legs': [ncaab_spreads[2], ncaab_spreads[3], ncaab_spreads[4], nba_spreads[1]]
})

# ── TICKET 5: 5-leg (Mixed spread + O/U) ──
tickets.append({
    'name': '5-Leg (Mixed Spread + O/U)',
    'legs': [nba_spreads[2], ncaab_spreads[5], ncaab_spreads[6], ncaab_ou[2], nba_ou[1]]
})

# ── TICKET 6: 6-leg (Spread heavy mix) ──
tickets.append({
    'name': '6-Leg (Spread Mix)',
    'legs': [nba_spreads[3], nba_spreads[4], ncaab_spreads[7], ncaab_spreads[8], ncaab_spreads[9], ou_legs[3]]
})

# ── TICKET 7: 7-leg (Best of everything) ──
tickets.append({
    'name': '7-Leg (Best of Everything)',
    'legs': [nba_spreads[5], ncaab_spreads[10], ncaab_spreads[11], ncaab_spreads[12],
             ou_legs[4], ou_legs[5], ou_legs[6]]
})

# ── TICKET 8: 14-leg HAIL MARY (can reuse some) ──
# Take the absolute best picks across all categories
hail_mary_pool = sorted(spread_legs + ou_legs, key=lambda x: x['prob'], reverse=True)
hm_legs = []
hm_games = set()
for leg in hail_mary_pool:
    # Allow same game if different bet type (spread + O/U on same game is fine on DK)
    game_key = f"{leg['matchup']}_{leg['bet_type']}"
    if game_key in hm_games:
        continue
    hm_legs.append(leg)
    hm_games.add(game_key)
    if len(hm_legs) >= 14:
        break

tickets.append({
    'name': '14-Leg HAIL MARY 🚀',
    'legs': hm_legs
})

# Print
print("=" * 65)
print("🎯 JOSH'S PARLAYS — Saturday Feb 22, 2026")
print("   Diversified: no single game dominates your night")
print("=" * 65)

game_usage = {}
for i, t in enumerate(tickets):
    legs = t['legs']
    combined_prob = 1.0
    for leg in legs:
        combined_prob *= leg['prob']
    
    if combined_prob >= 0.5:
        american = round(-combined_prob / (1 - combined_prob) * 100)
    elif combined_prob > 0:
        american = round((1 - combined_prob) / combined_prob * 100)
    else:
        american = 99999
    
    odds_str = f"+{american}" if american > 0 else str(american)
    payout = round(10 * (american / 100 + 1), 2) if american > 0 else round(10 * (100 / abs(american) + 1), 2)
    
    print(f"\n{'🔥' if len(legs) >= 7 else '🎯'} TICKET #{i+1} — {t['name']}")
    print(f"   {len(legs)} legs | {odds_str} | {combined_prob:.4%} prob | $10 wins ${payout:.2f}")
    print(f"   {'─' * 55}")
    
    for j, p in enumerate(legs, 1):
        is_ou = p.get('bet_type') == 'ou'
        tag = f"[{p['sport']}]"
        if is_ou:
            print(f"   {j}. 📊 {p['spread']} {tag} — {p['prob']:.0%} | edge {p.get('edge',0):+.1f}")
        else:
            print(f"   {j}. 🏀 {p['team']} {p['spread']} {tag} — {p['prob']:.1%}")
        
        game_usage[p['matchup']] = game_usage.get(p['matchup'], 0) + 1

print(f"\n{'=' * 65}")
print("📊 GAME DISTRIBUTION")
print(f"{'=' * 65}")
for matchup, count in sorted(game_usage.items(), key=lambda x: -x[1]):
    bar = '█' * count
    print(f"   {bar} ({count}x) {matchup}")

total_legs = sum(len(t['legs']) for t in tickets)
print(f"\n✅ {len(tickets)} tickets | {total_legs} total legs")
print(f"   Max game usage: {max(game_usage.values())}x")

# Save
with open(Path(__file__).parent / 'sim' / 'feb22_josh_tickets.json', 'w', encoding='utf-8') as f:
    json.dump([{
        'ticket': i+1, 'name': t['name'], 'num_legs': len(t['legs']),
        'picks': [{'team': p['team'], 'spread': p['spread'], 'prob': p['prob'],
                    'sport': p['sport'], 'home': p['home'], 'away': p['away'],
                    'bet_type': p.get('bet_type', 'spread')} for p in t['legs']],
        'combined_prob': 1.0,  # recalculate at scoring
    } for i, t in enumerate(tickets)], f, indent=2)
print(f"💾 Saved to sim/feb22_josh_tickets.json")
