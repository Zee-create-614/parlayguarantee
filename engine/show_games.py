import json
d = json.load(open('picks_output.json'))
print("=== Tonight's Games ===")
seen = set()
for key in ['single', '2leg', '3leg']:
    tier = d.get(key, {})
    for p in tier.get('picks', []):
        for g in p.get('games', []):
            gid = g.get('game_id','')
            if gid in seen: continue
            seen.add(gid)
            away = g['away']
            home = g['home']
            spread = g.get('spread', '?')
            wp = g['win_prob']
            pick = g['pick']
            print(f"  {away:30s} @ {home:30s} | spread: {spread:>7} | win_prob: {wp:.3f} | pick: {pick}")
