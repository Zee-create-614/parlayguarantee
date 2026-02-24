"""Fetch NCAAB team PPG/PAPG from ESPN standings API (all conferences)."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import requests
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "totals_engine_v3.db"

def fetch_all_ncaab_stats():
    """Fetch PPG/PAPG for all D1 teams from ESPN conference standings."""
    # ESPN groups: 50=all conferences. Each child is a conference.
    url = "https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings"
    params = {'group': '50'}
    
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    
    teams = {}
    for group in data.get('children', []):
        conf_name = group.get('name', '')
        for entry in group.get('standings', {}).get('entries', []):
            team_info = entry.get('team', {})
            name = team_info.get('displayName', '')
            if not name:
                continue
            
            stats = {}
            for s in entry.get('stats', []):
                sn = s.get('name', '')
                sv = s.get('value', 0)
                if sn == 'avgPointsFor': stats['ppg'] = float(sv)
                elif sn == 'avgPointsAgainst': stats['papg'] = float(sv)
                elif sn == 'wins': stats['wins'] = int(sv)
                elif sn == 'losses': stats['losses'] = int(sv)
                elif sn == 'streak': stats['streak'] = int(sv) if sv else 0
                elif sn == 'winPercent': stats['win_pct'] = float(sv)
            
            gp = stats.get('wins', 0) + stats.get('losses', 0)
            if gp < 5 or 'ppg' not in stats:
                continue
            
            stats['games_played'] = gp
            stats['conference'] = conf_name
            teams[name] = stats
    
    print(f"Fetched stats for {len(teams)} NCAAB teams")
    
    # Store in DB
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS ncaab_team_stats (
        team TEXT PRIMARY KEY,
        ppg REAL, papg REAL, wins INT, losses INT,
        win_pct REAL, streak INT, games_played INT, conference TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    for name, s in teams.items():
        c.execute('''INSERT OR REPLACE INTO ncaab_team_stats VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)''',
                  (name, s.get('ppg', 72.5), s.get('papg', 72.5),
                   s.get('wins', 0), s.get('losses', 0),
                   s.get('win_pct', 0.5), s.get('streak', 0),
                   s.get('games_played', 0), s.get('conference', '')))
    conn.commit()
    conn.close()
    
    # Print some stats
    ppgs = [s['ppg'] for s in teams.values()]
    papgs = [s['papg'] for s in teams.values()]
    avg_ppg = sum(ppgs) / len(ppgs)
    print(f"League avg PPG: {avg_ppg:.1f}")
    print(f"PPG range: {min(ppgs):.1f} - {max(ppgs):.1f}")
    
    # Save as JSON too
    out = Path(__file__).parent / "ncaab_team_stats.json"
    with open(out, 'w') as f:
        json.dump(teams, f, indent=2)
    print(f"Saved to {out}")
    
    return teams

if __name__ == "__main__":
    fetch_all_ncaab_stats()
