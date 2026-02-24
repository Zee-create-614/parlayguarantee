import json, sys
sys.stdout.reconfigure(encoding='utf-8')

games = json.load(open('analyzed_games.json'))
ou = []

for g in games:
    v3 = g.get('ou_model_v3')
    if v3 and v3['pick'] != 'PASS':
        ou.append({
            'matchup': g['away'] + ' @ ' + g['home'],
            'sport': g.get('sport', '?'),
            'pick': v3['pick'],
            'posted': v3['posted_total'],
            'predicted': v3['predicted_total'],
            'edge': v3['edge'],
            'confidence': v3['confidence'],
            'tier': v3['tier'],
            'agreement': g.get('ou_agreement', False)
        })

ou.sort(key=lambda x: x['confidence'], reverse=True)

overs = sum(1 for x in ou if 'OVER' in x['pick'])
unders = sum(1 for x in ou if 'UNDER' in x['pick'])

print("V3 O/U PICKS (market-blended, min 1.5pt edge)")
print("=" * 60)

for p in ou:
    arrow = '\u2b06' if 'OVER' in p['pick'] else '\u2b07'
    agree = ' \u2705' if p['agreement'] else ''
    print(f"{arrow} {p['matchup']} \u2014 {p['pick']} {p['posted']} | {p['tier']} | {p['confidence']:.0%} | edge {p['edge']:+.1f}{agree} [{p['sport']}]")

print(f"\nTotal: {len(ou)} picks | Overs: {overs} | Unders: {unders}")
print(f"PASS (no edge): {33 - len(ou)}")
