import sys, json, glob
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

for f in sorted(glob.glob('*parlays*2026-02-20*')):
    try:
        d = json.load(open(f, encoding='utf-8'))
        s = d.get('summary', {})
        print(f"{f}: {s.get('total_bets','?')} bets, {d.get('total_games','?')} games, product={d.get('product','?')}")
    except Exception as e:
        print(f"{f}: ERROR {e}")
