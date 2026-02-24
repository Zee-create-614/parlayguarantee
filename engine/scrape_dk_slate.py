"""Scrape DraftKings NBA slate for tonight's 7PM games"""
import requests
import json
from datetime import datetime

# DK public API for NBA contests/draftables
# Try the draftables endpoint
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Step 1: Get NBA game sets
print("Fetching DK NBA contests...")
url = "https://www.draftkings.com/lobby/getcontests?sport=NBA"
try:
    r = requests.get(url, headers=headers, timeout=15)
    data = r.json()
    
    # Find draft groups for tonight
    draft_groups = set()
    for contest in data.get('Contests', []):
        name = contest.get('n', '')
        dg = contest.get('dg', 0)
        starts = contest.get('sd', '')
        entries = contest.get('m', 0)  # max entries
        if dg and '7:00' in starts:
            draft_groups.add(dg)
            if len(draft_groups) <= 3:
                print(f"  Contest: {name[:60]} | DG: {dg} | Start: {starts}")
    
    if not draft_groups:
        # Try all draft groups
        for contest in data.get('Contests', [])[:5]:
            print(f"  Sample: {contest.get('n','')[:60]} | DG: {contest.get('dg',0)} | Start: {contest.get('sd','')}")
        draft_groups = set(c.get('dg',0) for c in data.get('Contests', [])[:10] if c.get('dg'))
    
    print(f"Found {len(draft_groups)} draft groups")
    
    # Step 2: Get draftables for first matching draft group
    for dg in list(draft_groups)[:3]:
        print(f"\nFetching players for draft group {dg}...")
        draftables_url = f"https://api.draftkings.com/draftgroups/v1/draftgroups/{dg}/draftables"
        r2 = requests.get(draftables_url, headers=headers, timeout=15)
        d2 = r2.json()
        
        players = []
        for p in d2.get('draftables', []):
            player = {
                'name': p.get('displayName', ''),
                'team': p.get('teamAbbreviation', ''),
                'position': p.get('rosterSlotId', p.get('position', '')),
                'salary': p.get('salary', 0),
                'fppg': p.get('draftStatAttributes', [{}])[0].get('value', 0) if p.get('draftStatAttributes') else 0,
                'status': p.get('status', ''),
                'game': f"{p.get('competition',{}).get('name','')}",
                'game_time': p.get('competition',{}).get('startTime',''),
            }
            # Get FPPG from attributes
            for attr in p.get('draftStatAttributes', []):
                if attr.get('id') == 90:  # FPPG
                    player['fppg'] = attr.get('value', 0)
            players.append(player)
        
        if players:
            # Filter to 7PM slate teams if this is the right group
            print(f"Total players in group: {len(players)}")
            
            # Sort by salary desc
            players.sort(key=lambda x: x['salary'], reverse=True)
            
            # Print top players
            print(f"\n{'POS':6s} {'PLAYER':28s} {'TEAM':5s} {'OPP':20s} {'FPPG':>6s} {'SALARY':>8s} {'STATUS':>8s}")
            print("-" * 85)
            for p in players[:50]:
                pos = str(p['position'])
                print(f"{pos:6s} {p['name']:28s} {p['team']:5s} {p['game'][:20]:20s} {p['fppg']:>6.1f} ${p['salary']:>7,} {p['status']:>8s}")
            
            # Save full data
            with open('engine/dk_slate_full.json', 'w') as f:
                json.dump({'draft_group': dg, 'players': players, 'fetched': datetime.now().isoformat()}, f, indent=2)
            print(f"\nSaved {len(players)} players to dk_slate_full.json")
            break
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
