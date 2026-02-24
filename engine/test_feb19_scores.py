"""
Test ESPN API for Feb 19, 2026 NBA scores
"""
import requests
import json
from datetime import date

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

def fetch_feb19_scores():
    """Fetch scores for Feb 19, 2026"""
    # ESPN API expects YYYYMMDD format
    date_str = "20260219"
    print(f"Fetching NBA scores for Feb 19, 2026 (date_str: {date_str})")
    
    try:
        resp = requests.get(ESPN_SCOREBOARD, params={'dates': date_str}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        print(f"ESPN API Response received (status: {resp.status_code})")
        
        # Save the full response for debugging
        with open('espn_feb19_response.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        events = data.get('events', [])
        print(f"Found {len(events)} events")
        
        if not events:
            print("No games found for Feb 19, 2026")
            return []
        
        results = []
        for event in events:
            print(f"\nEvent: {event.get('name', 'Unknown')}")
            
            competitions = event.get('competitions', [])
            if not competitions:
                continue
                
            comp = competitions[0]
            status = comp.get('status', {}).get('type', {}).get('name', '')
            print(f"  Status: {status}")
            
            teams = comp.get('competitors', [])
            if len(teams) < 2:
                continue
            
            home = away = None
            home_score = away_score = 0
            
            for t in teams:
                team_name = t.get('team', {}).get('displayName', '')
                score = int(t.get('score', 0))
                is_home = t.get('homeAway') == 'home'
                
                print(f"  {'Home' if is_home else 'Away'}: {team_name} ({score})")
                
                if is_home:
                    home = team_name
                    home_score = score
                else:
                    away = team_name
                    away_score = score
            
            if home and away:
                winner = home if home_score > away_score else away
                result = {
                    'home': home,
                    'away': away,
                    'home_score': home_score,
                    'away_score': away_score,
                    'winner': winner,
                    'margin': abs(home_score - away_score),
                    'final': status == 'STATUS_FINAL',
                }
                results.append(result)
                print(f"  Result: {away} {away_score} @ {home} {home_score} — Winner: {winner}")
        
        return results
        
    except Exception as e:
        print(f"Error fetching scores: {e}")
        return []

if __name__ == '__main__':
    results = fetch_feb19_scores()
    print(f"\n=== SUMMARY ===")
    print(f"Total games: {len(results)}")
    for r in results:
        status = "FINAL" if r['final'] else "IN PROGRESS"
        print(f"  {r['away']} {r['away_score']} @ {r['home']} {r['home_score']} — {r['winner']} ({status})")