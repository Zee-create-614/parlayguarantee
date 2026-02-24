import json
d = json.load(open('caesars_data.json'))
for s in d:
    if 'basket' in s.get('name','').lower():
        for c in s.get('competitions', []):
            if 'ncaa' in c.get('name','').lower():
                print(json.dumps(c, indent=2)[:500])
