import json

with open('picks_2026-02-23_engine_plus_kalshi/kalshi_comparison.json') as f:
    data = json.load(f)

print(f"Games with Kalshi: {data['games_with_kalshi']}/{data['total_games']}")
print(f"Picks changed: {data['picks_changed']}\n")

for c in data['comparison']:
    hp = c.get('kalshi_home_prob')
    ap = c.get('kalshi_away_prob')
    game = c['game']
    eng = c['engine_pick']
    eng_c = c['engine_conf']
    bp = c['blended_pick']
    bc = c['blended_conf']
    
    if hp is not None:
        fav = c['kalshi_favors']
        div = c['divergence']
        vol = c['kalshi_volume']
        print(f"{game}")
        print(f"  Engine:  {eng} @ {eng_c:.1%}")
        print(f"  Kalshi:  Home={hp:.1%} Away={ap:.1%} (favors {fav}, vol={vol:,})")
        print(f"  Blended: {bp} @ {bc:.1%} (divergence: {div:.1%})")
        if c['changed']:
            print(f"  *** PICK FLIPPED ***")
    else:
        print(f"{game}")
        print(f"  Engine:  {eng} @ {eng_c:.1%}")
        print(f"  Kalshi:  NO DATA (game not on Kalshi today)")
    print()
