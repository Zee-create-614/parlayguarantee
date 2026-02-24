import json
with open('analyzed_games.json', encoding='utf-8') as f:
    d = json.load(f)
for g in d:
    if 'Montana' in g.get('home','') or 'Montana' in g.get('away','') or 'Idaho S' in g.get('home','') or 'Weber' in g.get('home','') or 'Alabama S' in g.get('home','') or 'Alabama S' in g.get('away',''):
        print(f"{g['away']} @ {g['home']}")
        print(f"  pick: {g['pick']}")
        print(f"  spread (home): {g.get('spread')}")
        print(f"  pick_spread: {g.get('pick_spread')}")
        print(f"  spread_str: {g.get('spread_str')}")
        print(f"  cover_prob: {g.get('cover_prob')}")
        print(f"  upset_score: {g.get('upset_score')}")
        print()
