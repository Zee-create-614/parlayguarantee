import sys, json
sys.stdout.reconfigure(encoding='utf-8')
stats = json.load(open('ncaab_team_stats.json'))
teams = ['Maryland-Eastern Shore Hawks', 'Coppin State Eagles', 'Coppin St Eagles']
for name in teams:
    s = stats.get(name, {})
    if s:
        print(f"{name}: PPG={s['ppg']}, PAPG={s['papg']}")
    else:
        # Search fuzzy
        matches = [k for k in stats if name.split()[0] in k]
        print(f"{name}: NOT FOUND. Similar: {matches[:3]}")
