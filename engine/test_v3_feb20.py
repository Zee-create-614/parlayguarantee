"""Test v3 model against Feb 20 real data."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from totals_engine_v3 import TotalsEngineV3

# Real posted totals from Feb 20 + actual scores
games = [
    ('Oklahoma City Thunder', 'Brooklyn Nets', 213.2, 191),
    ('Minnesota Timberwolves', 'Dallas Mavericks', 239.6, 233),
    ('Los Angeles Lakers', 'Los Angeles Clippers', 226.1, 247),
    ('Charlotte Hornets', 'Cleveland Cavaliers', 230.1, 231),
    ('New Orleans Pelicans', 'Milwaukee Bucks', 223.4, 257),
    ('Atlanta Hawks', 'Miami Heat', 244.1, 225),
    ('Memphis Grizzlies', 'Utah Jazz', 236.6, 237),
    ('Washington Wizards', 'Indiana Pacers', 229.1, 249),
    ('Portland Trail Blazers', 'Denver Nuggets', 241.7, 260),
]

engine = TotalsEngineV3('nba')
engine.fetch_team_stats()

correct = total = 0
passed = 0
v1_correct = 0

print("\n" + "="*70)
print("  v3 O/U MODEL — REPLAY vs Feb 20 REAL LINES")
print("="*70)

for home, away, posted, actual in games:
    pred = engine.predict(home, away, posted, 0, '2026-02-20')
    actual_result = 'OVER' if actual > posted else 'UNDER'
    
    v1_hit = 'UNDER' == actual_result
    if v1_hit:
        v1_correct += 1
    
    if pred['pick'] == 'PASS':
        passed += 1
        v1e = 'Y' if v1_hit else 'N'
        print(f"  PASS  {away} @ {home}: posted {posted}, our {pred['our_raw_total']}, edge {pred['edge']:+.1f} | actual {actual} ({actual_result}) | v1_UNDER={'Y' if v1_hit else 'N'}")
        continue
    
    hit = pred['pick'] == actual_result
    total += 1
    if hit:
        correct += 1
    
    emoji = 'HIT ' if hit else 'MISS'
    v1e = 'Y' if v1_hit else 'N'
    print(f"  {emoji} {pred['pick']:5s} {away} @ {home}: posted {posted}, predicted {pred['predicted_total']}, edge {pred['edge']:+.1f} | actual {actual} ({actual_result})")

print(f"\n  v3: {correct}/{total} ({round(correct/total*100,1)}%) on {total} actionable picks ({passed} passed)")
print(f"  v1: {v1_correct}/9 ({round(v1_correct/9*100,1)}%) — all UNDER")
print(f"  Coin flip: ~50%")
print("="*70)
