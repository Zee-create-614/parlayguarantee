import sys, requests
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
now = datetime.now(timezone.utc)

for sport, label in [("basketball_nba", "NBA"), ("basketball_ncaab", "NCAAB")]:
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
        params={"apiKey": API_KEY, "regions": "us", "markets": "h2h", "dateFormat": "iso"}, timeout=20)
    data = r.json()
    
    upcoming = []
    already = []
    for g in data:
        ct = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        entry = (ct, g["away_team"], g["home_team"])
        if ct > now:
            upcoming.append(entry)
        else:
            already.append(entry)
    
    upcoming.sort()
    print(f"\n{label} - {len(upcoming)} games NOT YET STARTED (DK would show these):")
    for dt, away, home in upcoming:
        from datetime import timedelta
        est = dt - timedelta(hours=5)
        print(f"  {est.strftime('%I:%M %p')} - {away} @ {home}")
    
    print(f"  ({len(already)} games already started/finished today)")
