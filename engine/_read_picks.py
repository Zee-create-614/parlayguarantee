import json

data = json.load(open('analyzed_games.json'))

nba_spread = [g for g in data if g.get('sport')=='NBA' and g.get('enhanced_prob')]
ncaab_spread = [g for g in data if g.get('sport')=='NCAAB' and g.get('enhanced_prob')]
ou_picks = [g for g in data if g.get('ou_prob')]

print('=== NBA SPREAD ===')
for g in sorted(nba_spread, key=lambda x: x.get('enhanced_prob',0), reverse=True):
    upset = g.get('upset_flag') or g.get('upset_flip') or (g.get('upset_composite',0) or 0) > 0.5
    print(f"{g.get('away','?')} @ {g.get('home','?')} | Pick: {g.get('pick','?')} | Spread: {g.get('spread','')} | enhanced_prob: {g.get('enhanced_prob',0):.1%} | ml_prob: {g.get('ml_prob',0):.1%} | upset_composite: {g.get('upset_composite','N/A')} | upset: {upset}")

print()
print('=== NCAAB SPREAD (top 20) ===')
for g in sorted(ncaab_spread, key=lambda x: x.get('enhanced_prob',0), reverse=True)[:20]:
    upset = g.get('upset_flag') or g.get('upset_flip') or (g.get('upset_composite',0) or 0) > 0.5
    print(f"{g.get('away','?')} @ {g.get('home','?')} | Pick: {g.get('pick','?')} | Spread: {g.get('spread','')} | enhanced_prob: {g.get('enhanced_prob',0):.1%} | ml_prob: {g.get('ml_prob',0):.1%} | upset_composite: {g.get('upset_composite','N/A')} | upset: {upset}")

print()
print('=== O/U PICKS (top 10) ===')
for g in sorted(ou_picks, key=lambda x: x.get('ou_prob',0), reverse=True)[:10]:
    edge = ''
    pt = g.get('predicted_total')
    t = g.get('total')
    if pt and t:
        try:
            edge = f"{float(pt) - float(t):+.1f}"
        except:
            edge = ''
    print(f"{g.get('away','?')} @ {g.get('home','?')} | O/U: {g.get('ou_pick','?')} | Line: {t} | Model: {pt} | ou_prob: {g.get('ou_prob',0):.1%} | Edge: {edge}")

print()
print(f"Total: {len(data)} | NBA: {len(nba_spread)} | NCAAB: {len(ncaab_spread)} | O/U: {len(ou_picks)}")
