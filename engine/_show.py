import json
d = json.load(open('analyzed_games.json'))
print(f"{len(d)} games\n")
for g in d[:20]:
    flip = " 🔄FLIP" if g.get('upset_flip') else ""
    ou = f"| {g['ou_pick']} {g['total_line']}" if g.get('ou_pick') else ""
    print(f"  {g['sport']:5} | {g['pick']:30} {g['spread_str']:6} ({g['enhanced_prob']:.0%}) | {g['away']} @ {g['home']} {ou}{flip}")
