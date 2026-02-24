import json
d = json.load(open(r'C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-24\all_picks.json'))
games = d.get('all_games', [])
confs = [g.get('confidence', g.get('enhanced_prob',0)*100) for g in games]
print(f"Total: {len(games)} | Conf range: {min(confs):.1f}% - {max(confs):.1f}%")
top = sorted(games, key=lambda x: -x.get('confidence', x.get('enhanced_prob',0)*100))[:10]
for g in top:
    c = g.get('confidence', g.get('enhanced_prob',0)*100)
    print(f"  {g['pick']} {g.get('spread_str','')} ({c:.1f}%) [{g['sport']}]")
