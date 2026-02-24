import sys, json, requests
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

for sport, label in [("basketball_nba", "NBA"), ("basketball_ncaab", "NCAAB")]:
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
        params={"apiKey": API_KEY, "regions": "us", "markets": "h2h", "dateFormat": "iso"}, timeout=20)
    data = r.json()
    
    today_games = []
    for g in data:
        ct = g.get("commence_time", "")
        if "2026-02-21" in ct or "2026-02-20" in ct:
            # Check if it's actually tonight (Feb 20 evening / Feb 21 early UTC)
            dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            today_games.append((dt, g["away_team"], g["home_team"]))
    
    today_games.sort()
    print(f"\n{label} - {len(today_games)} games tonight (Feb 20):")
    for dt, away, home in today_games:
        est = dt.astimezone(timezone(datetime.now(timezone.utc).astimezone().utcoffset()))
        print(f"  {est.strftime('%I:%M %p')} - {away} @ {home}")
    
    print(f"\n  (Total events from API: {len(data)})")
