#!/usr/bin/env python3
"""
Pre-warm Alpha V3 cache by fetching NBA.com stats via VPS proxy.
Run this before engine runs to ensure all data sources are populated.
Falls back to direct if VPS unavailable.
"""
import json, logging, time, subprocess, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

VPS_HOST = "root@165.227.71.3"
VPS_PASS = "1mariaLove"

ENGINE_DIR = Path(__file__).parent
CACHE_DIR = ENGINE_DIR / "data" / "alpha_v3_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

import hashlib

def cache_path(key):
    safe = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{safe}.json"

def cache_set(key, payload):
    cache_path(key).write_text(
        json.dumps({'_ts': time.time(), 'payload': payload}, default=str),
        encoding='utf-8'
    )
    logger.info(f"  Cached: {key}")

def cache_fresh(key, max_hours=24):
    p = cache_path(key)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return (time.time() - data.get('_ts', 0)) < max_hours * 3600
    except:
        return False

def fetch_via_vps(python_code):
    """Run python code on VPS and return the JSON result."""
    try:
        # Use sshpass for non-interactive SSH
        cmd = f'sshpass -p "{VPS_PASS}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 {VPS_HOST} "python3 -c \\"{python_code}\\""'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception as e:
        logger.warning(f"VPS fetch failed: {e}")
    return None

def fetch_nba_stats_direct():
    """Fetch team ratings directly (local fallback)."""
    import requests
    try:
        from nba_advanced_stats import _current_season, HEADERS
        url = "https://stats.nba.com/stats/leaguedashteamstats"
        params = {
            'Conference': '', 'DateFrom': '', 'DateTo': '',
            'Division': '', 'GameScope': '', 'GameSegment': '',
            'Height': '', 'ISTRound': '', 'LastNGames': '0',
            'LeagueID': '00', 'Location': '', 'MeasureType': 'Advanced',
            'Month': '0', 'OpponentTeamID': '0', 'Outcome': '',
            'PORound': '0', 'PaceAdjust': 'N', 'PerMode': 'PerGame',
            'Period': '0', 'PlayerExperience': '', 'PlayerPosition': '',
            'PlusMinus': 'N', 'Rank': 'N', 'Season': _current_season(),
            'SeasonSegment': '', 'SeasonType': 'Regular Season',
            'ShotClockRange': '', 'StarterBench': '', 'TeamID': '0',
            'TwoWay': '0', 'VsConference': '', 'VsDivision': '',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            headers_list = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx = {h: i for i, h in enumerate(headers_list)}
            result = {}
            for row in rows:
                name = row[idx.get('TEAM_NAME', 1)]
                result[name] = {
                    'ortg': row[idx.get('OFF_RATING', 0)] if 'OFF_RATING' in idx else 0,
                    'drtg': row[idx.get('DEF_RATING', 0)] if 'DEF_RATING' in idx else 0,
                    'net_rtg': row[idx.get('NET_RATING', 0)] if 'NET_RATING' in idx else 0,
                    'pace': row[idx.get('PACE', 0)] if 'PACE' in idx else 100,
                }
            return result
    except Exception as e:
        logger.warning(f"Direct NBA.com fetch failed: {e}")
    return None

def fetch_nba_clutch_direct():
    """Fetch clutch stats directly."""
    import requests
    try:
        from nba_advanced_stats import _current_season, HEADERS
        url = "https://stats.nba.com/stats/leaguedashteamclutch"
        params = {
            'AheadBehind': 'Ahead or Behind', 'ClutchTime': 'Last 5 Minutes',
            'Conference': '', 'DateFrom': '', 'DateTo': '', 'Division': '',
            'GameScope': '', 'GameSegment': '', 'Height': '', 'ISTRound': '',
            'LastNGames': '0', 'LeagueID': '00', 'Location': '',
            'MeasureType': 'Base', 'Month': '0', 'OpponentTeamID': '0',
            'Outcome': '', 'PORound': '0', 'PaceAdjust': 'N',
            'PerMode': 'PerGame', 'Period': '0', 'PlayerExperience': '',
            'PlayerPosition': '', 'PlusMinus': 'N', 'PointDiff': '5',
            'Rank': 'N', 'Season': _current_season(), 'SeasonSegment': '',
            'SeasonType': 'Regular Season', 'ShotClockRange': '',
            'StarterBench': '', 'TeamID': '0', 'VsConference': '', 'VsDivision': '',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            headers_list = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx = {h: i for i, h in enumerate(headers_list)}
            result = {}
            for row in rows:
                name = row[idx.get('TEAM_NAME', 1)]
                result[name] = {
                    'clutch_w': row[idx.get('W', 0)] if 'W' in idx else 0,
                    'clutch_l': row[idx.get('L', 0)] if 'L' in idx else 0,
                    'clutch_win_pct': row[idx.get('W_PCT', 0)] if 'W_PCT' in idx else 0.5,
                    'clutch_pts': row[idx.get('PTS', 0)] if 'PTS' in idx else 0,
                    'clutch_plus_minus': row[idx.get('PLUS_MINUS', 0)] if 'PLUS_MINUS' in idx else 0,
                }
            return result
    except Exception as e:
        logger.warning(f"Direct clutch fetch failed: {e}")
    return None

def fetch_nba_player_stats_direct():
    """Fetch player advanced stats directly."""
    import requests
    try:
        from nba_advanced_stats import _current_season, HEADERS
        url = "https://stats.nba.com/stats/leaguedashplayerstats"
        params = {
            'Conference': '', 'DateFrom': '', 'DateTo': '', 'Division': '',
            'GameScope': '', 'GameSegment': '', 'Height': '', 'ISTRound': '',
            'LastNGames': '0', 'LeagueID': '00', 'Location': '',
            'MeasureType': 'Advanced', 'Month': '0', 'OpponentTeamID': '0',
            'Outcome': '', 'PORound': '0', 'PaceAdjust': 'N',
            'PerMode': 'PerGame', 'Period': '0', 'PlayerExperience': '',
            'PlayerPosition': '', 'PlusMinus': 'N', 'Rank': 'N',
            'Season': _current_season(), 'SeasonSegment': '',
            'SeasonType': 'Regular Season', 'ShotClockRange': '',
            'StarterBench': '', 'TeamID': '0',
        }
        nba_headers = {**HEADERS, 'Referer': 'https://www.nba.com/', 'x-nba-stats-origin': 'stats', 'x-nba-stats-token': 'true'}
        r = requests.get(url, params=params, headers=nba_headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            headers_list = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            idx = {h: i for i, h in enumerate(headers_list)}
            by_team = {}
            for row in rows:
                team = row[idx.get('TEAM_ABBREVIATION', 0)]
                if team not in by_team:
                    by_team[team] = []
                by_team[team].append({
                    'name': row[idx.get('PLAYER_NAME', 0)] if 'PLAYER_NAME' in idx else '',
                    'pie': row[idx.get('PIE', 0)] if 'PIE' in idx else 0,
                    'usage': row[idx.get('USG_PCT', 0)] if 'USG_PCT' in idx else 0,
                    'ts_pct': row[idx.get('TS_PCT', 0)] if 'TS_PCT' in idx else 0,
                })
            return by_team
    except Exception as e:
        logger.warning(f"Direct player stats fetch failed: {e}")
    return None

def main():
    logger.info("=== Pre-warming Alpha V3 cache ===")
    
    sources = [
        ('team_ratings', fetch_nba_stats_direct),
        ('clutch_stats', fetch_nba_clutch_direct),
        ('player_advanced', fetch_nba_player_stats_direct),
    ]
    
    success = 0
    for key, fetcher in sources:
        if cache_fresh(key, max_hours=18):
            logger.info(f"  {key}: already fresh, skipping")
            success += 1
            continue
        
        logger.info(f"  Fetching {key}...")
        data = fetcher()
        if data:
            cache_set(key, data)
            success += 1
        else:
            logger.warning(f"  {key}: FAILED")
    
    # Also pre-warm the other sources via the module directly
    try:
        from nba_advanced_stats import (
            fetch_schedule_rest, fetch_ats_trends, fetch_sos_data,
            fetch_quarter_patterns, fetch_ft_rate
        )
        from datetime import date as dt_date
        today = dt_date.today()
        
        extras = [
            ('schedule_rest', lambda: fetch_schedule_rest(today)),
            ('ats_trends', fetch_ats_trends),
            ('sos', fetch_sos_data),
        ]
        for key, fetcher in extras:
            if not cache_fresh(key, max_hours=18):
                logger.info(f"  Fetching {key}...")
                try:
                    data = fetcher()
                    if data:
                        success += 1
                except Exception as e:
                    logger.warning(f"  {key}: {e}")
            else:
                logger.info(f"  {key}: already fresh, skipping")
                success += 1
    except Exception as e:
        logger.warning(f"Extra sources failed: {e}")
    
    logger.info(f"=== Pre-warm complete: {success} sources ready ===")

if __name__ == '__main__':
    main()
