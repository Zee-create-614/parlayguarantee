import json, glob, os

base = r'C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine'

# Find all scored parlay files
scored_files = glob.glob(os.path.join(base, '*parlays*scored*'))
print("Scored parlay files:", scored_files)

# Also check the main scored file
for f in scored_files:
    data = json.load(open(f))
    print(f"\n=== {os.path.basename(f)} ===")
    if 'parlays' in data:
        parlays = data['parlays']
    elif isinstance(data, list):
        parlays = data
    else:
        # Look for parlay keys
        for k in data:
            if 'parlay' in k.lower():
                print(f"  Key: {k}")
        # Try to find parlays in nested structure
        if 'games' in data:
            print(f"  Games: {len(data['games'])}")
        continue
    
    print(f"  Total parlays: {len(parlays)}")

# Now let's look at the Feb 20 scored file more carefully
f = os.path.join(base, 'all_parlays_2026-02-20_scored.json')
if os.path.exists(f):
    data = json.load(open(f))
    keys = list(data.keys())
    print(f"\nKeys in scored file: {keys}")
    
    # Check if parlays section exists
    for k in keys:
        if isinstance(data[k], list) and len(data[k]) > 0:
            print(f"  {k}: {len(data[k])} items, first item keys: {list(data[k][0].keys()) if isinstance(data[k][0], dict) else 'not dict'}")

# Let's also look at all_parlays_2026-02-20.json for parlay structure
f2 = os.path.join(base, 'all_parlays_2026-02-20.json')
if os.path.exists(f2):
    data2 = json.load(open(f2))
    keys2 = list(data2.keys())
    print(f"\nKeys in unscored file: {keys2}")
    for k in keys2:
        if isinstance(data2[k], list) and len(data2[k]) > 0:
            first = data2[k][0]
            if isinstance(first, dict):
                print(f"  {k}: {len(data2[k])} items")
                if 'legs' in first:
                    print(f"    Sample parlay: {len(first['legs'])} legs, keys: {list(first.keys())}")
                    print(f"    Leg keys: {list(first['legs'][0].keys())}")
                    print(f"    First parlay: {json.dumps(first, indent=2)[:500]}")
