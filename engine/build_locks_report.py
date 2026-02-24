import json

with open('tonight_analysis_data.json') as f:
    tonight = json.load(f)

with open('analyzed_games.json') as f:
    engine = json.load(f)

with open('ncaab_picks_2026-02-20.json') as f:
    ncaab = json.load(f)

print("=== TONIGHT ANALYSIS ===")
for g in tonight.get('games', []):
    keys_to_show = ['home', 'away', 'spread', 'confidence', 'pick', 'upset_composite', 'injury_adjustment', 'h2h_factor', 'line_movement', 'total', 'over_under']
    info = {k: g.get(k) for k in keys_to_show if g.get(k) is not None}
    print(json.dumps(info))

print("\n=== ENGINE PICKS ===")
for g in engine:
    print(f"{g['away']} @ {g['home']} | pick={g['pick']} {g.get('spread_str','')} | cover_prob={g.get('cover_prob',0):.1%} | edge={g.get('edge',0):.1%}")

print("\n=== NCAAB PICKS ===")
for g in ncaab:
    print(f"{g.get('away_team','')} @ {g.get('home_team','')} | spread_pick={g.get('spread_pick','')} ({g.get('spread_confidence',0):.1%}) | ou={g.get('ou_pick','')} total={g.get('total','')} | win_conf={g.get('confidence',0):.1%}")
