"""
NBA Injury Scraper - Live injury data for ParlayGuarantee
Sources: CBS Sports NBA injury page (primary), with caching to JSON
"""

import json
import os
import sys
import time
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.path.dirname(__file__), 'injury_cache.json')
CACHE_TTL_MINUTES = 10

# ESPN injury page
ESPN_INJURY_URL = "https://www.espn.com/nba/injuries"
# CBS Sports
CBS_INJURY_URL = "https://www.cbssports.com/nba/injuries/"
# Rotowire fallback
ROTOWIRE_URL = "https://www.rotowire.com/basketball/injury-report.php"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# Team name normalization map
TEAM_NORMALIZE = {
    # CBS Sports short names
    'Atlanta': 'Atlanta Hawks', 'Boston': 'Boston Celtics',
    'Brooklyn': 'Brooklyn Nets', 'Charlotte': 'Charlotte Hornets',
    'Chicago': 'Chicago Bulls', 'Cleveland': 'Cleveland Cavaliers',
    'Dallas': 'Dallas Mavericks', 'Denver': 'Denver Nuggets',
    'Detroit': 'Detroit Pistons', 'Golden St.': 'Golden State Warriors',
    'Houston': 'Houston Rockets', 'Indiana': 'Indiana Pacers',
    'L.A. Clippers': 'Los Angeles Clippers', 'L.A. Lakers': 'Los Angeles Lakers',
    'Memphis': 'Memphis Grizzlies', 'Miami': 'Miami Heat',
    'Milwaukee': 'Milwaukee Bucks', 'Minnesota': 'Minnesota Timberwolves',
    'New Orleans': 'New Orleans Pelicans', 'New York': 'New York Knicks',
    'Oklahoma City': 'Oklahoma City Thunder', 'Orlando': 'Orlando Magic',
    'Philadelphia': 'Philadelphia 76ers', 'Phoenix': 'Phoenix Suns',
    'Portland': 'Portland Trail Blazers', 'Sacramento': 'Sacramento Kings',
    'San Antonio': 'San Antonio Spurs', 'Toronto': 'Toronto Raptors',
    'Utah': 'Utah Jazz', 'Washington': 'Washington Wizards',
    # Other variants
    'LA Clippers': 'Los Angeles Clippers', 'LA Lakers': 'Los Angeles Lakers',
    'GS Warriors': 'Golden State Warriors', 'SA Spurs': 'San Antonio Spurs',
    'NO Pelicans': 'New Orleans Pelicans', 'OKC Thunder': 'Oklahoma City Thunder',
    'NY Knicks': 'New York Knicks', 'PHX Suns': 'Phoenix Suns',
}

# Star player impact ratings (approximate WAR-style impact, 0-1 scale)
# Top ~50 most impactful NBA players
STAR_IMPACT = {
    # MVP-tier
    'Nikola Jokic': 0.95, 'Luka Doncic': 0.92, 'Giannis Antetokounmpo': 0.92,
    'Shai Gilgeous-Alexander': 0.90, 'Joel Embiid': 0.90, 'Jayson Tatum': 0.88,
    'Stephen Curry': 0.88, 'Kevin Durant': 0.87, 'LeBron James': 0.85,
    'Anthony Davis': 0.85, 'Damian Lillard': 0.84, 'Donovan Mitchell': 0.83,
    'Jimmy Butler': 0.82, 'Kawhi Leonard': 0.82, 'Anthony Edwards': 0.85,
    'Jaylen Brown': 0.82, 'Tyrese Haliburton': 0.82, 'De\'Aaron Fox': 0.80,
    'Devin Booker': 0.83, 'Trae Young': 0.80, 'Ja Morant': 0.82,
    'Karl-Anthony Towns': 0.78, 'Bam Adebayo': 0.78, 'Domantas Sabonis': 0.80,
    'Paolo Banchero': 0.78, 'Tyrese Maxey': 0.78, 'Jalen Brunson': 0.82,
    'Lauri Markkanen': 0.76, 'Zion Williamson': 0.78, 'Brandon Ingram': 0.74,
    'Chet Holmgren': 0.76, 'Victor Wembanyama': 0.82, 'James Harden': 0.76,
    'Paul George': 0.76, 'DeMar DeRozan': 0.74, 'Pascal Siakam': 0.76,
    'Kristaps Porzingis': 0.78, 'Scottie Barnes': 0.76, 'Alperen Sengun': 0.74,
    'Franz Wagner': 0.76, 'Cade Cunningham': 0.76, 'Mikal Bridges': 0.72,
    'Derrick White': 0.72, 'Jrue Holiday': 0.74, 'Khris Middleton': 0.72,
}

# Status to impact multiplier
STATUS_MULTIPLIER = {
    'Out': 1.0,
    'Doubtful': 0.85,
    'Questionable': 0.4,
    'Probable': 0.1,
    'Day-To-Day': 0.3,
    'GTD': 0.4,   # Game Time Decision
}


def normalize_team(team_name: str) -> str:
    """Normalize team names to full canonical form"""
    return TEAM_NORMALIZE.get(team_name, team_name)


def normalize_status(raw_status: str) -> str:
    """Normalize injury status strings"""
    s = raw_status.strip().lower()
    if 'out' in s:
        return 'Out'
    if 'doubtful' in s:
        return 'Doubtful'
    if 'questionable' in s:
        return 'Questionable'
    if 'probable' in s:
        return 'Probable'
    if 'day' in s and 'day' in s:
        return 'Day-To-Day'
    if 'gtd' in s or 'game time' in s:
        return 'GTD'
    return raw_status.strip()


def scrape_cbs_injuries() -> List[Dict]:
    """Scrape CBS Sports NBA injury page"""
    injuries = []
    try:
        resp = requests.get(CBS_INJURY_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # CBS uses table rows with team headers
        tables = soup.find_all('table', class_=re.compile(r'TableBase-table'))
        if not tables:
            tables = soup.find_all('table')

        current_team = "Unknown"
        for table in tables:
            # CBS has team name in a span with class containing 'TeamName' before each table
            prev = table.find_previous('span', class_=re.compile(r'TeamName|team'))
            if prev:
                team_text = prev.get_text(strip=True)
                current_team = normalize_team(team_text)

            rows = table.find_all('tr')
            for row in rows[1:]:  # Skip header
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    # CBS has CellPlayerName--long and --short spans; prefer long
                    long_name = cells[0].find('span', class_=re.compile(r'CellPlayerName--long'))
                    if long_name:
                        player = long_name.get_text(strip=True)
                    else:
                        player = cells[0].get_text(strip=True)
                    # Filter out header-like rows
                    if player.lower() in ('player', 'name', ''):
                        continue
                    position = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    # CBS columns: Player, Position, Updated, Injury, Injury Status
                    updated = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                    injury_type = cells[3].get_text(strip=True) if len(cells) > 3 else 'Undisclosed'
                    status = normalize_status(cells[4].get_text(strip=True)) if len(cells) > 4 else 'Unknown'

                    injuries.append({
                        'player': player,
                        'team': current_team,
                        'status': status,
                        'injury': injury_type,
                        'position': position,
                        'updated': updated,
                        'source': 'CBS Sports',
                    })

        logger.info(f"CBS Sports: scraped {len(injuries)} injuries")
    except Exception as e:
        logger.warning(f"CBS Sports scrape failed: {e}")

    return injuries


def scrape_espn_injuries() -> List[Dict]:
    """Scrape ESPN NBA injury page"""
    injuries = []
    try:
        resp = requests.get(ESPN_INJURY_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # ESPN structures injuries by team sections
        team_sections = soup.find_all('div', class_=re.compile(r'ResponsiveTable'))
        if not team_sections:
            team_sections = soup.find_all('div', class_=re.compile(r'Table'))

        for section in team_sections:
            # Find team name
            team_header = section.find_previous(['h2', 'h3', 'span'], class_=re.compile(r'injuries__teamName|Table__Title'))
            team_name = team_header.get_text(strip=True) if team_header else 'Unknown'
            team_name = normalize_team(team_name)

            rows = section.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    player = cells[0].get_text(strip=True)
                    if player.lower() in ('name', 'player', ''):
                        continue
                    status = normalize_status(cells[1].get_text(strip=True))
                    comment = cells[2].get_text(strip=True) if len(cells) > 2 else ''

                    injuries.append({
                        'player': player,
                        'team': team_name,
                        'status': status,
                        'injury': comment,
                        'position': '',
                        'source': 'ESPN',
                    })

        logger.info(f"ESPN: scraped {len(injuries)} injuries")
    except Exception as e:
        logger.warning(f"ESPN scrape failed: {e}")

    return injuries


def scrape_rotowire_injuries() -> List[Dict]:
    """Scrape Rotowire NBA injury page (fallback)"""
    injuries = []
    try:
        resp = requests.get(ROTOWIRE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Rotowire has a structured injury table
        rows = soup.select('.injury-report__table tr, .injury-table tr, table tr')
        current_team = "Unknown"

        for row in rows:
            # Check if this is a team header row
            team_cell = row.find('td', class_=re.compile(r'team|header'))
            if team_cell and not row.find_all('td', limit=4).__len__() >= 3:
                current_team = normalize_team(team_cell.get_text(strip=True))
                continue

            cells = row.find_all('td')
            if len(cells) >= 3:
                player = cells[0].get_text(strip=True)
                if not player or player.lower() in ('player', 'name'):
                    continue
                
                # Try to extract status and injury
                status_text = ''
                injury_text = ''
                for cell in cells[1:]:
                    text = cell.get_text(strip=True)
                    if any(s in text.lower() for s in ['out', 'doubtful', 'questionable', 'probable', 'gtd', 'day-to-day']):
                        status_text = text
                    elif text and not status_text:
                        status_text = text
                    elif text:
                        injury_text = text

                injuries.append({
                    'player': player,
                    'team': current_team,
                    'status': normalize_status(status_text),
                    'injury': injury_text,
                    'position': '',
                    'source': 'Rotowire',
                })

        logger.info(f"Rotowire: scraped {len(injuries)} injuries")
    except Exception as e:
        logger.warning(f"Rotowire scrape failed: {e}")

    return injuries


NBA_OFFICIAL_INJURY_URL = "https://official.nba.com/nba-injury-report-2024-25-season/"


def scrape_nba_official_injuries() -> List[Dict]:
    """Scrape the official NBA injury report — most authoritative source."""
    injuries = []
    try:
        resp = requests.get(NBA_OFFICIAL_INJURY_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # The NBA official report uses tables with team headers
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            current_team = "Unknown"
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue

                # Header rows often have team name spanning columns
                if len(cells) == 1:
                    text = cells[0].get_text(strip=True)
                    if text:
                        current_team = normalize_team(text)
                    continue

                # Try to parse: Game Date | Game Time | Matchup | Team | Player | Current Status | Reason
                texts = [c.get_text(strip=True) for c in cells]
                if len(texts) >= 5:
                    # Skip header rows
                    if any(h in texts[0].lower() for h in ['game date', 'date', '']):
                        # Could be header - check if "Player" is in there
                        if any('player' in t.lower() for t in texts):
                            continue

                    # Try multiple column layouts
                    if len(texts) >= 7:
                        # Full layout: Date, Time, Matchup, Team, Player, Status, Reason
                        team_col = normalize_team(texts[3])
                        player = texts[4]
                        status = normalize_status(texts[5])
                        reason = texts[6] if len(texts) > 6 else ''
                    elif len(texts) >= 5:
                        # Shorter layout
                        team_col = normalize_team(texts[1]) if len(texts) > 4 else current_team
                        player = texts[2] if len(texts) > 4 else texts[0]
                        status = normalize_status(texts[3] if len(texts) > 4 else texts[1])
                        reason = texts[4] if len(texts) > 4 else (texts[2] if len(texts) > 2 else '')
                    else:
                        continue

                    if not player or player.lower() in ('player', 'name', ''):
                        continue

                    if team_col and team_col != "Unknown":
                        current_team = team_col

                    injuries.append({
                        'player': player,
                        'team': current_team,
                        'status': status,
                        'injury': reason,
                        'position': '',
                        'source': 'NBA Official',
                    })

        logger.info(f"NBA Official: scraped {len(injuries)} injuries")
    except Exception as e:
        logger.warning(f"NBA Official scrape failed: {e}")

    return injuries


def get_injuries(force_refresh: bool = False) -> Dict:
    """
    Get current NBA injuries. Uses cache if fresh enough.
    Returns dict with 'injuries' list and 'last_updated' timestamp.
    """
    # Check cache
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            cached_time = datetime.fromisoformat(cached.get('last_updated', '2000-01-01'))
            if datetime.now() - cached_time < timedelta(minutes=CACHE_TTL_MINUTES):
                logger.info(f"Using cached injuries ({len(cached.get('injuries', []))} entries)")
                return cached
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

    # Try sources in order of reliability
    injuries = []
    
    # Try CBS first
    injuries = scrape_cbs_injuries()
    
    # If CBS failed, try ESPN
    if not injuries:
        injuries = scrape_espn_injuries()
    
    # If both failed, try Rotowire
    if not injuries:
        injuries = scrape_rotowire_injuries()

    # ALWAYS try NBA Official as secondary/merge source (most authoritative)
    try:
        nba_official = scrape_nba_official_injuries()
        if nba_official:
            # Merge: NBA official takes priority for status if player already exists
            existing_players = {inj['player'].lower() for inj in injuries}
            for off_inj in nba_official:
                key = off_inj['player'].lower()
                if key in existing_players:
                    # Update status from official source (more authoritative)
                    for inj in injuries:
                        if inj['player'].lower() == key:
                            inj['status'] = off_inj['status']
                            inj['source'] = f"{inj['source']}+NBA Official"
                            break
                else:
                    injuries.append(off_inj)
                    existing_players.add(key)
            logger.info(f"Merged {len(nba_official)} NBA Official entries")
    except Exception as e:
        logger.warning(f"NBA Official merge failed: {e}")

    # Deduplicate by player name
    seen = set()
    unique_injuries = []
    for inj in injuries:
        key = inj['player'].lower()
        if key not in seen:
            seen.add(key)
            unique_injuries.append(inj)

    result = {
        'injuries': unique_injuries,
        'last_updated': datetime.now().isoformat(),
        'source_count': len(unique_injuries),
    }

    # Organize by team
    by_team = {}
    for inj in unique_injuries:
        team = inj['team']
        if team not in by_team:
            by_team[team] = []
        by_team[team].append(inj)
    result['by_team'] = by_team

    # Save cache
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"Cached {len(unique_injuries)} injuries to {CACHE_FILE}")
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")

    return result


def get_team_injury_impact(team_name: str, injuries_data: Optional[Dict] = None) -> float:
    """
    Calculate injury impact score for a team.
    Returns 0.0 (no impact) to ~0.3 (catastrophic injuries).
    Uses star player ratings and status multipliers.
    """
    if injuries_data is None:
        injuries_data = get_injuries()

    by_team = injuries_data.get('by_team', {})
    
    # Try exact match first, then fuzzy
    team_injuries = by_team.get(team_name, [])
    if not team_injuries:
        # Try partial match
        for t, injs in by_team.items():
            if team_name.lower() in t.lower() or t.lower() in team_name.lower():
                team_injuries = injs
                break

    if not team_injuries:
        return 0.0

    total_impact = 0.0
    for inj in team_injuries:
        player = inj['player']
        status = inj['status']
        
        # Get player importance (default 0.3 for non-stars)
        player_rating = STAR_IMPACT.get(player, 0.3)
        status_mult = STATUS_MULTIPLIER.get(status, 0.5)
        
        impact = player_rating * status_mult * 0.15  # Scale to 0-0.15 per player
        total_impact += impact

    # Cap at 0.3 (even losing multiple stars shouldn't exceed this)
    return min(total_impact, 0.30)


# CLI interface
if __name__ == '__main__':
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    
    if '--json' in sys.argv:
        # Output JSON to stdout for the API route
        data = get_injuries(force_refresh='--force' in sys.argv)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif '--team' in sys.argv:
        idx = sys.argv.index('--team')
        team = ' '.join(sys.argv[idx+1:])
        data = get_injuries()
        impact = get_team_injury_impact(team, data)
        team_injs = data.get('by_team', {}).get(team, [])
        print(f"\n{team} Injury Report:")
        print(f"  Impact Score: {impact:.3f}")
        for inj in team_injs:
            star = ' ⭐' if inj['player'] in STAR_IMPACT else ''
            print(f"  - {inj['player']}{star}: {inj['status']} ({inj['injury']})")
    else:
        # Default: print summary
        data = get_injuries(force_refresh=True)
        print(f"\nNBA Injury Report ({data['last_updated']})")
        print(f"Total injuries tracked: {data['source_count']}")
        print()
        for team, injs in sorted(data.get('by_team', {}).items()):
            impact = get_team_injury_impact(team, data)
            print(f"{team} (impact: {impact:.3f}):")
            for inj in injs:
                star = ' ⭐' if inj['player'] in STAR_IMPACT else ''
                print(f"  {inj['player']}{star}: {inj['status']} - {inj['injury']}")
            print()
