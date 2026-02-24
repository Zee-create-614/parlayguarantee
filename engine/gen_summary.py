#!/usr/bin/env python3
"""Generate feb22_summary.json from all simulation files."""
import json, sys
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
SIM_DIR = Path(__file__).parent / 'sim'

files = {
    'nba_spread': 'feb22_nba_spread_parlays.json',
    'nba_ml': 'feb22_nba_ml_parlays.json',
    'ncaab_spread': 'feb22_ncaab_spread_parlays.json',
    'ncaab_ml': 'feb22_ncaab_ml_parlays.json',
    'mixed_spread': 'feb22_mixed_spread_parlays.json',
    'mixed_ml': 'feb22_mixed_ml_parlays.json',
    'ou': 'feb22_ou_parlays.json',
    'everything_mixed': 'feb22_everything_mixed.json',
}

summary = {}
for cat, fname in files.items():
    path = SIM_DIR / fname
    if not path.exists():
        print(f'MISSING: {fname}')
        continue
    data = json.load(open(path, encoding='utf-8'))
    parlays = data['parlays']
    legs_index = data['legs_index']
    
    by_legs = defaultdict(list)
    for p in parlays:
        by_legs[p['n']].append(p['p'])
    
    avg_by_legs = {}
    for n, ps in sorted(by_legs.items()):
        avg_by_legs[str(n)] = {'count': len(ps), 'avg_prob': round(sum(ps)/len(ps), 8), 'max_prob': round(max(ps), 8)}
    
    best = max(parlays, key=lambda p: p['p']) if parlays else None
    best_info = None
    if best:
        best_legs_detail = [legs_index[i] for i in best['l']]
        best_info = {
            'leg_ids': best['l'], 'combined_probability': best['p'],
            'combined_american_odds': best['o'], 'number_of_legs': best['n'],
            'legs_detail': best_legs_detail,
        }
    
    summary[cat] = {'total': len(parlays), 'by_legs': avg_by_legs, 'best_parlay': best_info, 'file': fname, 'size_mb': round(path.stat().st_size/1024/1024, 1)}
    print(f'{cat}: {len(parlays):,} parlays ({summary[cat]["size_mb"]}MB)')
    for n, info in avg_by_legs.items():
        print(f'  {n}-leg: {info["count"]:,} combos, avg prob {info["avg_prob"]:.6f}, best {info["max_prob"]:.6f}')

with open(SIM_DIR / 'feb22_summary.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f'\nSummary saved to sim/feb22_summary.json')
