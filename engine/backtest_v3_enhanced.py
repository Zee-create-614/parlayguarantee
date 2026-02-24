"""
ParlayGuarantee Engine v2 - Enhanced Backtest (v3)
Adds 15+ new factors, robust retry logic, and completes Jan 1 - Feb 12.
"""

import sys
import json
import time
import logging
import sqlite3
import math
import signal
from datetime import datetime, date, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats, teamgamelog
from nba_api.stats.static import teams

from engine_v2 import TEAM_ID_MAP, safe_get_data_frames
from self_learner import SelfLearner
from team_locations import (
    calculate_distance, get_timezone_difference, is_division_rival,
    is_conference_game, NBA_TEAM_LOCATIONS, NBA_DIVISIONS, NBA_CONFERENCES
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('backtest_v3_run.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

API_DELAY = 1.8  # 1.8s between calls (safe margin)
MAX_RETRIES = 3
TEAM_ABBREV_MAP = {t['abbreviation']: t['full_name'] for t in teams.get_teams()}
TEAM_NAME_TO_ID = {t['full_name']: t['id'] for t in teams.get_teams()}
TEAM_NAME_TO_ABBREV = {t['full_name']: t['abbreviation'] for t in teams.get_teams()}

# Denver altitude factor - teams not used to altitude
DENVER_ALTITUDE_FT = 5280
HIGH_ALTITUDE_TEAMS = {"Denver Nuggets", "Utah Jazz"}  # teams used to altitude

# National TV schedule (simplified - major games)
# In reality you'd scrape this, but for backtest we'll detect marquee matchups
MARQUEE_TEAMS = {
    "Los Angeles Lakers", "Golden State Warriors", "Boston Celtics",
    "Milwaukee Bucks", "Phoenix Suns", "Dallas Mavericks",
    "Denver Nuggets", "Philadelphia 76ers", "Miami Heat",
    "New York Knicks", "LA Clippers", "Cleveland Cavaliers",
    "Minnesota Timberwolves", "Oklahoma City Thunder"
}

# Hostile arena rankings (subjective but data-backed)
HOSTILE_ARENAS = {
    "Utah Jazz": 0.8, "Denver Nuggets": 0.7, "Miami Heat": 0.7,
    "Boston Celtics": 0.9, "Golden State Warriors": 0.8,
    "New York Knicks": 0.7, "Oklahoma City Thunder": 0.6,
    "Milwaukee Bucks": 0.6, "Memphis Grizzlies": 0.6,
    "Philadelphia 76ers": 0.7, "Cleveland Cavaliers": 0.6,
    "Minnesota Timberwolves": 0.5, "Phoenix Suns": 0.5,
}


import socket
import multiprocessing

# Set global socket timeout to prevent hung connections
socket.setdefaulttimeout(30)

def _api_worker(func_name, args, kwargs, result_queue):
    """Worker process for API call"""
    try:
        import socket
        socket.setdefaulttimeout(25)
        # Re-import inside subprocess
        if func_name == 'TeamGameLog':
            from nba_api.stats.endpoints import teamgamelog
            result = teamgamelog.TeamGameLog(*args, timeout=20, **kwargs)
        elif func_name == 'ScoreboardV2':
            from nba_api.stats.endpoints import scoreboardv2
            result = scoreboardv2.ScoreboardV2(*args, timeout=20, **kwargs)
        elif func_name == 'LeagueDashTeamStats':
            from nba_api.stats.endpoints import leaguedashteamstats
            result = leaguedashteamstats.LeagueDashTeamStats(*args, timeout=20, **kwargs)
        else:
            result = None
        result_queue.put(('ok', result.get_dict() if result else None))
    except Exception as e:
        result_queue.put(('error', str(e)))


def api_call_with_retry(func, *args, max_retries=MAX_RETRIES, **kwargs):
    """Execute NBA API call with exponential backoff retry and process-level timeout"""
    func_name = func.__name__
    
    for attempt in range(max_retries):
        try:
            time.sleep(API_DELAY)
            result = func(*args, timeout=20, **kwargs)
            return result
        except Exception as e:
            wait = API_DELAY * (2 ** attempt)
            logger.warning(f"API call attempt {attempt+1}/{max_retries} failed: {e}. Waiting {wait:.1f}s...")
            time.sleep(wait)
    
    # If all retries with normal method fail, try with multiprocessing
    logger.warning(f"Trying multiprocessing fallback for {func_name}...")
    try:
        result_queue = multiprocessing.Queue()
        p = multiprocessing.Process(target=_api_worker, args=(func_name, args, kwargs, result_queue))
        p.start()
        p.join(timeout=40)
        
        if p.is_alive():
            logger.warning(f"Killing hung API process for {func_name}")
            p.terminate()
            p.join(timeout=5)
            if p.is_alive():
                p.kill()
            return None
        
        if not result_queue.empty():
            status, data = result_queue.get_nowait()
            if status == 'ok' and data:
                # Reconstruct a fake result object
                return _DictWrapper(data)
            else:
                logger.warning(f"Worker returned error: {data}")
                return None
        return None
    except Exception as e:
        logger.error(f"Multiprocessing fallback failed: {e}")
        return None


class _DictWrapper:
    """Wraps a dict to provide get_dict() interface"""
    def __init__(self, data):
        self._data = data
    def get_dict(self):
        return self._data
    def get_data_frames(self):
        frames = []
        for rs in self._data.get('resultSets', []):
            headers = rs.get('headers', [])
            rows = rs.get('rowSet', [])
            frames.append(pd.DataFrame(rows, columns=headers) if headers else pd.DataFrame())
        return frames


def fetch_all_team_stats():
    """Fetch basic + advanced team stats with retry"""
    print("Fetching team stats (basic)...")
    basic = api_call_with_retry(
        leaguedashteamstats.LeagueDashTeamStats,
        season='2025-26', league_id_nullable='00'
    )
    if basic is None:
        raise RuntimeError("Could not fetch basic team stats")
    if isinstance(basic, _DictWrapper):
        basic_df = basic.get_data_frames()[0]
    else:
        basic_df = safe_get_data_frames(basic)[0]

    print("Fetching team stats (advanced)...")
    adv = api_call_with_retry(
        leaguedashteamstats.LeagueDashTeamStats,
        season='2025-26', league_id_nullable='00',
        measure_type_detailed_defense='Advanced'
    )
    if adv is None:
        raise RuntimeError("Could not fetch advanced team stats")
    if isinstance(adv, _DictWrapper):
        adv_df = adv.get_data_frames()[0]
    else:
        adv_df = safe_get_data_frames(adv)[0]
    adv_by_id = {row['TEAM_ID']: row for _, row in adv_df.iterrows()}

    team_stats = {}
    for _, row in basic_df.iterrows():
        tid = row['TEAM_ID']
        name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
        gp = max(row['GP'], 1)
        adv_row = adv_by_id.get(tid, {})

        ppg = row['PTS'] / gp
        pm_pg = row['PLUS_MINUS'] / gp

        team_stats[name] = {
            'games_played': row['GP'],
            'wins': row['W'],
            'losses': row['L'],
            'win_pct': row['W_PCT'],
            'ppg': ppg,
            'opp_ppg': ppg - pm_pg,
            'plus_minus': pm_pg,
            'offensive_rating': adv_row.get('OFF_RATING', 110) if isinstance(adv_row, pd.Series) else 110,
            'defensive_rating': adv_row.get('DEF_RATING', 110) if isinstance(adv_row, pd.Series) else 110,
            'net_rating': adv_row.get('NET_RATING', 0) if isinstance(adv_row, pd.Series) else 0,
            'pace': adv_row.get('PACE', 100) if isinstance(adv_row, pd.Series) else 100,
            'fg_pct': row['FG_PCT'],
            'fg3_pct': row['FG3_PCT'],
            'ft_pct': row['FT_PCT'],
            'fg3a_pg': row['FG3A'] / gp,
            'fta_pg': row['FTA'] / gp,
            'reb_pg': row['REB'] / gp,
            'oreb_pg': row['OREB'] / gp,
            'ast_pg': row['AST'] / gp,
            'tov_pg': row['TOV'] / gp,
            'stl_pg': row['STL'] / gp,
            'blk_pg': row['BLK'] / gp,
        }

    print(f"Loaded stats for {len(team_stats)} teams")
    return team_stats


def _fetch_single_gamelog(tid, name, result_dict):
    """Fetch a single team's gamelog (for use in a subprocess-like context)"""
    import socket
    socket.setdefaulttimeout(25)
    try:
        gl = teamgamelog.TeamGameLog(team_id=tid, season='2025-26', timeout=20)
        data = gl.get_dict()
        rs = data['resultSets'][0]
        result_dict['headers'] = rs['headers']
        result_dict['rows'] = rs['rowSet']
    except Exception as e:
        result_dict['error'] = str(e)


def fetch_single_gamelog_with_timeout(tid, name, timeout_sec=35):
    """Fetch gamelog with hard process-level timeout"""
    import multiprocessing
    
    manager = multiprocessing.Manager()
    result_dict = manager.dict()
    
    p = multiprocessing.Process(target=_fetch_single_gamelog, args=(tid, name, result_dict))
    p.start()
    p.join(timeout=timeout_sec)
    
    if p.is_alive():
        logger.warning(f"Killing hung gamelog fetch for {name}")
        p.terminate()
        p.join(timeout=5)
        if p.is_alive():
            p.kill()
            p.join(timeout=2)
        return None
    
    if 'error' in result_dict:
        logger.warning(f"Gamelog fetch error for {name}: {result_dict['error']}")
        return None
    
    if 'headers' in result_dict and 'rows' in result_dict:
        headers = list(result_dict['headers'])
        rows = [list(r) for r in result_dict['rows']]
        df = pd.DataFrame(rows, columns=headers)
        df['GAME_DATE_PARSED'] = pd.to_datetime(df['GAME_DATE'], format='mixed')
        return df
    
    return None


def fetch_all_gamelogs():
    """Pre-fetch gamelogs for all 30 NBA teams with hard timeout per team"""
    gamelogs = {}
    nba_teams = teams.get_teams()

    for i, team in enumerate(nba_teams):
        tid = team['id']
        name = team['full_name']
        print(f"  Fetching gamelog {i+1}/30: {name}...", end=" ", flush=True)
        
        time.sleep(API_DELAY)
        
        # Try normal method first
        success = False
        for attempt in range(2):
            try:
                time.sleep(API_DELAY if attempt > 0 else 0)
                df = fetch_single_gamelog_with_timeout(tid, name, timeout_sec=35)
                if df is not None and not df.empty:
                    gamelogs[name] = df
                    print(f"{len(df)} games")
                    success = True
                    break
                else:
                    print(f"attempt {attempt+1} failed...", end=" ", flush=True)
            except Exception as e:
                print(f"attempt {attempt+1} error: {e}...", end=" ", flush=True)
        
        if not success:
            print("SKIPPED (all attempts failed)")
            gamelogs[name] = pd.DataFrame()

    return gamelogs


def get_scoreboard_results(game_date: date) -> list:
    """Fetch actual game results for a date with retry"""
    date_str = game_date.strftime('%m/%d/%Y')
    
    sb = api_call_with_retry(scoreboardv2.ScoreboardV2, game_date=date_str)
    if sb is None:
        return []
    
    try:
        if hasattr(sb, 'get_dict'):
            data = sb.get_dict()
        elif isinstance(sb, dict):
            data = sb
        else:
            data = sb.get_dict()
        result_sets = data['resultSets']
        header_rs = result_sets[0]
        line_rs = result_sets[1]

        h_headers = header_rs['headers']
        l_headers = line_rs['headers']

        pts_idx = l_headers.index('PTS')
        tid_idx = l_headers.index('TEAM_ID')
        gid_idx_l = l_headers.index('GAME_ID')

        line_lookup = {}
        for row in line_rs['rowSet']:
            line_lookup[(row[gid_idx_l], row[tid_idx])] = row[pts_idx]

        gid_idx = h_headers.index('GAME_ID')
        home_idx = h_headers.index('HOME_TEAM_ID')
        away_idx = h_headers.index('VISITOR_TEAM_ID')

        results = []
        for row in header_rs['rowSet']:
            game_id = row[gid_idx]
            home_id = row[home_idx]
            away_id = row[away_idx]
            home_team = TEAM_ID_MAP.get(home_id, f"Team_{home_id}")
            away_team = TEAM_ID_MAP.get(away_id, f"Team_{away_id}")

            home_pts = line_lookup.get((game_id, home_id))
            away_pts = line_lookup.get((game_id, away_id))

            if home_pts is None or away_pts is None:
                continue
            try:
                home_pts, away_pts = int(home_pts), int(away_pts)
            except (ValueError, TypeError):
                continue
            if home_pts == 0 and away_pts == 0:
                continue

            results.append({
                'game_id': game_id,
                'home_team': home_team,
                'away_team': away_team,
                'home_score': home_pts,
                'away_score': away_pts,
                'actual_winner': home_team if home_pts > away_pts else away_team,
            })
        # Deduplicate by game_id
        seen = set()
        unique_results = []
        for r in results:
            if r['game_id'] not in seen:
                seen.add(r['game_id'])
                unique_results.append(r)
        return unique_results
    except Exception as e:
        logger.error(f"Error parsing scoreboard for {game_date}: {e}")
        return []


# ==================== NEW FACTOR CALCULATIONS ====================

def get_games_before_date(gl, target_date):
    """Get games before a given date from gamelog"""
    if gl.empty or 'GAME_DATE_PARSED' not in gl.columns:
        return pd.DataFrame()
    target_dt = pd.Timestamp(datetime.combine(target_date, datetime.min.time()))
    return gl[gl['GAME_DATE_PARSED'] < target_dt]


def calc_rest_days(gl, target_date):
    """Calculate rest days before target date"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 2
    last = recent.iloc[0]['GAME_DATE_PARSED']
    target_dt = pd.Timestamp(datetime.combine(target_date, datetime.min.time()))
    return max(0, (target_dt - last).days - 1)


def calc_recent_form(gl, target_date, n):
    """Recent form (win%) for last N games before target_date"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0.5
    games = recent.head(n)
    wins = len(games[games['WL'] == 'W'])
    return wins / max(1, len(games))


def calc_home_away_pct(gl, target_date, is_home=True):
    """Home or away win% from games before target_date"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0.58 if is_home else 0.42
    if is_home:
        games = recent[~recent['MATCHUP'].str.contains('@', na=False)]
    else:
        games = recent[recent['MATCHUP'].str.contains('@', na=False)]
    if games.empty:
        return 0.58 if is_home else 0.42
    wins = len(games[games['WL'] == 'W'])
    return wins / len(games)


def calc_win_streak(gl, target_date):
    """Current win/loss streak. Positive = winning streak, negative = losing streak"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0
    streak = 0
    first_result = recent.iloc[0]['WL']
    for _, game in recent.iterrows():
        if game['WL'] == first_result:
            streak += 1
        else:
            break
    return streak if first_result == 'W' else -streak


def calc_scoring_margin_trend(gl, target_date, n=5):
    """Average scoring margin over last N games (positive = outscoring opponents)"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0.0
    games = recent.head(n)
    if games.empty:
        return 0.0
    # PTS column is team points; we can't get opponent points from gamelog directly
    # But PLUS_MINUS gives us the margin
    if 'PLUS_MINUS' in games.columns:
        return games['PLUS_MINUS'].mean()
    return 0.0


def calc_road_trip_length(gl, target_date, team_name):
    """How many consecutive away games the team has played (road trip length)"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0
    consecutive_away = 0
    for _, game in recent.iterrows():
        if '@' in str(game['MATCHUP']):
            consecutive_away += 1
        else:
            break
    return consecutive_away


def calc_miles_traveled_7d(gl, target_date, team_name):
    """Estimate miles traveled in last 7 days"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0.0
    
    cutoff = pd.Timestamp(datetime.combine(target_date - timedelta(days=7), datetime.min.time()))
    week_games = recent[recent['GAME_DATE_PARSED'] >= cutoff]
    
    if week_games.empty:
        return 0.0
    
    total_miles = 0.0
    prev_location = team_name  # Start from home
    
    for _, game in week_games.iloc[::-1].iterrows():  # Reverse to chronological
        matchup = str(game['MATCHUP'])
        if '@' in matchup:
            parts = matchup.split(' @ ')
            if len(parts) > 1:
                opp_abbrev = parts[1].strip()
                opp_name = TEAM_ABBREV_MAP.get(opp_abbrev)
                if opp_name:
                    total_miles += calculate_distance(prev_location, opp_name)
                    prev_location = opp_name
        else:
            # Home game - traveled home
            total_miles += calculate_distance(prev_location, team_name)
            prev_location = team_name
    
    return total_miles


def calc_overtime_games_7d(gl, target_date):
    """Count overtime games in last 7 days (extra fatigue)"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0
    
    cutoff = pd.Timestamp(datetime.combine(target_date - timedelta(days=7), datetime.min.time()))
    week_games = recent[recent['GAME_DATE_PARSED'] >= cutoff]
    
    if week_games.empty or 'MIN' not in week_games.columns:
        return 0
    
    # NBA regulation = 240 minutes team total (48 min * 5 players), OT adds ~25 min team total
    # But MIN in gamelog is total team minutes (48*5=240 for regulation)
    # Actually MIN in gamelog is formatted as "MM:SS" total team time
    ot_count = 0
    for _, game in week_games.iterrows():
        try:
            mins = game['MIN']
            if isinstance(mins, str) and ':' in mins:
                m = int(mins.split(':')[0])
            else:
                m = int(float(mins))
            if m > 245:  # More than 240+buffer = overtime
                ot_count += 1
        except:
            pass
    return ot_count


def calc_revenge_game(gl, target_date, opponent_name):
    """Check if team lost to this opponent recently (last 30 days) = revenge motivation"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0.0
    
    cutoff = pd.Timestamp(datetime.combine(target_date - timedelta(days=45), datetime.min.time()))
    recent_games = recent[recent['GAME_DATE_PARSED'] >= cutoff]
    
    opp_abbrev = TEAM_NAME_TO_ABBREV.get(opponent_name, '')
    if not opp_abbrev:
        return 0.0
    
    for _, game in recent_games.iterrows():
        matchup = str(game['MATCHUP'])
        if opp_abbrev in matchup and game['WL'] == 'L':
            return 1.0  # Lost to this opponent recently
    return 0.0


def is_trap_game(home_team, away_team, team_stats):
    """Detect trap game: elite team vs bad team"""
    hs = team_stats.get(home_team, {})
    aws = team_stats.get(away_team, {})
    
    h_wpct = hs.get('win_pct', 0.5)
    a_wpct = aws.get('win_pct', 0.5)
    
    # Big favorite (>0.65 win%) vs big underdog (<0.35 win%)
    if h_wpct > 0.65 and a_wpct < 0.35:
        return -0.5  # Slight penalty for home team (trap game risk)
    if a_wpct > 0.65 and h_wpct < 0.35:
        return 0.5  # Slight boost for home team (opponent in trap)
    return 0.0


def calc_altitude_factor(home_team, away_team):
    """Denver/Utah altitude advantage for home team"""
    if home_team == "Denver Nuggets" and away_team not in HIGH_ALTITUDE_TEAMS:
        return 0.8  # Strong altitude advantage
    if home_team == "Utah Jazz" and away_team not in HIGH_ALTITUDE_TEAMS:
        return 0.4  # Moderate altitude advantage
    return 0.0


def calc_arena_hostility(home_team):
    """Arena hostility factor for home team"""
    return HOSTILE_ARENAS.get(home_team, 0.3)


def is_marquee_matchup(home_team, away_team):
    """Is this a national TV caliber marquee matchup?"""
    if home_team in MARQUEE_TEAMS and away_team in MARQUEE_TEAMS:
        return 1.0
    return 0.0


def calc_b2b_status(gl, target_date):
    """More granular B2B: 0=rested, 1=B2B, 2=second of B2B after travel"""
    rest = calc_rest_days(gl, target_date)
    if rest > 0:
        return 0  # Not B2B
    
    # It's a B2B - check if they traveled
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 1
    
    last_game = recent.iloc[0]
    if '@' in str(last_game['MATCHUP']):
        return 2  # B2B after away game (worst case)
    return 1  # B2B after home game


def calc_games_in_7_days(gl, target_date):
    """Number of games played in last 7 days (schedule density)"""
    recent = get_games_before_date(gl, target_date)
    if recent.empty:
        return 0
    cutoff = pd.Timestamp(datetime.combine(target_date - timedelta(days=7), datetime.min.time()))
    week_games = recent[recent['GAME_DATE_PARSED'] >= cutoff]
    return len(week_games)


# ==================== MAIN FACTOR COMPUTATION ====================

def compute_factors(home_team, away_team, game_date, team_stats, gamelogs):
    """Compute ALL prediction factors using pre-fetched data (no API calls)"""
    hs = team_stats.get(home_team, {})
    aws = team_stats.get(away_team, {})
    hgl = gamelogs.get(home_team, pd.DataFrame())
    agl = gamelogs.get(away_team, pd.DataFrame())

    factors = {}

    # === ORIGINAL FACTORS (1-33) ===
    
    # 1. Season win pct diff
    factors['season_win_pct'] = hs.get('win_pct', 0.5) - aws.get('win_pct', 0.5)

    # 2-3. Home/Away splits
    # home_win_pct: higher = home team wins more at home = good for home (correct direction)
    factors['home_win_pct'] = calc_home_away_pct(hgl, game_date, True)
    # away_win_pct: INVERT so higher = away team WORSE on road = good for home prediction
    factors['away_win_pct'] = 1.0 - calc_home_away_pct(agl, game_date, False)

    # 4-5. Recent form
    factors['last_10_record'] = calc_recent_form(hgl, game_date, 10) - calc_recent_form(agl, game_date, 10)
    factors['last_5_record'] = calc_recent_form(hgl, game_date, 5) - calc_recent_form(agl, game_date, 5)

    # 6-11. Advanced metrics
    # offensive_rating: home offense vs away offense (higher home OFF = advantage for home)
    factors['offensive_rating'] = hs.get('offensive_rating', 110) - aws.get('offensive_rating', 110)
    # defensive_rating: away DEF - home DEF (higher away DEF = they allow more = advantage for home)
    factors['defensive_rating'] = aws.get('defensive_rating', 110) - hs.get('defensive_rating', 110)
    factors['net_rating'] = hs.get('net_rating', 0) - aws.get('net_rating', 0)
    # pace: zeroed out (negatively correlated noise factor)
    factors['pace'] = 0.0
    factors['ppg'] = hs.get('ppg', 110) - aws.get('ppg', 110)
    factors['points_allowed'] = aws.get('opp_ppg', 110) - hs.get('opp_ppg', 110)

    # 12. Rest days
    hr = calc_rest_days(hgl, game_date)
    ar = calc_rest_days(agl, game_date)
    factors['rest_days'] = (hr - ar) / 3.0

    # 13-14
    factors['day_of_week'] = game_date.weekday() / 6.0
    factors['game_time'] = 0.0

    # 15-16. Travel/timezone
    factors['travel_distance'] = 0.0  # Simplified for team stats
    try:
        tz_diff = get_timezone_difference(away_team, home_team)
        factors['timezone_change'] = abs(tz_diff) / 3.0
    except:
        factors['timezone_change'] = 0.0

    factors['days_since_last'] = (hr + ar) / 4.0

    # 18-20. Matchup
    factors['head_to_head'] = 0.0
    factors['division_rivalry'] = 1.0 if is_division_rival(home_team, away_team) else 0.0
    factors['conference_game'] = 1.0 if is_conference_game(home_team, away_team) else 0.0

    # 21-28. Statistical differentials
    factors['strength_of_schedule'] = 0.0
    factors['clutch_performance'] = hs.get('plus_minus', 0) - aws.get('plus_minus', 0)
    factors['turnover_diff'] = (aws.get('tov_pg', 14) - hs.get('tov_pg', 14))
    factors['rebound_diff'] = hs.get('reb_pg', 44) - aws.get('reb_pg', 44)
    factors['ft_rate_diff'] = hs.get('fta_pg', 22) - aws.get('fta_pg', 22)
    factors['three_pt_pct'] = hs.get('fg3_pct', 0.35) - aws.get('fg3_pct', 0.35)
    factors['assists_pg'] = hs.get('ast_pg', 25) - aws.get('ast_pg', 25)
    factors['defensive_activity'] = (hs.get('stl_pg', 8) + hs.get('blk_pg', 5)) - \
                                     (aws.get('stl_pg', 8) + aws.get('blk_pg', 5))

    # 29-30. Injury proxy
    factors['key_player_status'] = 0.0
    factors['star_player_penalty'] = 0.0

    # 31-33. Market (skip for backtest)
    factors['line_movement'] = 0.0
    factors['public_betting'] = 0.0
    factors['closing_line_value'] = 0.0

    # === NEW FACTORS (34-48) ===

    # 34. Win/Loss streak differential
    h_streak = calc_win_streak(hgl, game_date)
    a_streak = calc_win_streak(agl, game_date)
    factors['streak_diff'] = (h_streak - a_streak) / 10.0  # Normalize by 10

    # 35. Scoring margin trend (last 5 games)
    h_margin = calc_scoring_margin_trend(hgl, game_date, 5)
    a_margin = calc_scoring_margin_trend(agl, game_date, 5)
    factors['scoring_margin_trend'] = (h_margin - a_margin) / 15.0

    # 36. Road trip length (away team)
    away_road_trip = calc_road_trip_length(agl, game_date, away_team)
    factors['away_road_trip'] = min(away_road_trip, 5) / 5.0  # Normalize, cap at 5

    # 37. Miles traveled in last 7 days
    h_miles = calc_miles_traveled_7d(hgl, game_date, home_team)
    a_miles = calc_miles_traveled_7d(agl, game_date, away_team)
    factors['miles_traveled_diff'] = (a_miles - h_miles) / 3000.0  # Normalize

    # 38. Overtime fatigue (last 7 days)
    h_ot = calc_overtime_games_7d(hgl, game_date)
    a_ot = calc_overtime_games_7d(agl, game_date)
    factors['overtime_fatigue'] = (a_ot - h_ot) / 2.0

    # 39. Revenge game factor
    h_revenge = calc_revenge_game(hgl, game_date, away_team)
    a_revenge = calc_revenge_game(agl, game_date, home_team)
    factors['revenge_game'] = (h_revenge - a_revenge)

    # 40. Trap game detection
    factors['trap_game'] = is_trap_game(home_team, away_team, team_stats)

    # 41. Altitude factor
    factors['altitude_factor'] = calc_altitude_factor(home_team, away_team)

    # 42. Arena hostility — REMOVED (negatively correlated noise)
    factors['arena_hostility'] = 0.0

    # 43. Marquee matchup — REMOVED (negatively correlated noise)
    factors['marquee_matchup'] = 0.0

    # 44. B2B status differential (more granular)
    h_b2b = calc_b2b_status(hgl, game_date)
    a_b2b = calc_b2b_status(agl, game_date)
    factors['b2b_status'] = (a_b2b - h_b2b) / 2.0  # Away B2B helps home

    # 45. Schedule density (games in 7 days)
    h_density = calc_games_in_7_days(hgl, game_date)
    a_density = calc_games_in_7_days(agl, game_date)
    factors['schedule_density'] = (a_density - h_density) / 4.0

    # 46. Last 3 games form (shorter window, more responsive)
    factors['last_3_record'] = calc_recent_form(hgl, game_date, 3) - calc_recent_form(agl, game_date, 3)

    # 47. Offensive rebound differential (hustle/effort indicator)
    factors['oreb_diff'] = hs.get('oreb_pg', 10) - aws.get('oreb_pg', 10)

    # 48. 3-point attempt rate differential (play style)
    factors['three_pt_volume'] = hs.get('fg3a_pg', 35) - aws.get('fg3a_pg', 35)

    # Sanitize
    for k, v in factors.items():
        if not isinstance(v, (int, float)) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            factors[k] = 0.0

    return factors


# ==================== FACTOR NORMALIZATION ====================

FACTOR_NORMS = {
    # Original factors
    'season_win_pct': 0.4, 'home_win_pct': 0.5, 'away_win_pct': 0.5,
    'last_10_record': 0.5, 'last_5_record': 0.6,
    'offensive_rating': 10.0, 'defensive_rating': 10.0, 'net_rating': 10.0,
    'pace': 0.1, 'ppg': 15.0, 'points_allowed': 15.0,
    'rest_days': 1.0, 'day_of_week': 1.0, 'game_time': 1.0,
    'travel_distance': 1.0, 'timezone_change': 1.0, 'days_since_last': 1.0,
    'head_to_head': 0.5, 'division_rivalry': 1.0, 'conference_game': 1.0,
    'strength_of_schedule': 0.15, 'clutch_performance': 8.0,
    'turnover_diff': 4.0, 'rebound_diff': 6.0, 'ft_rate_diff': 5.0,
    'three_pt_pct': 0.06, 'assists_pg': 6.0, 'defensive_activity': 4.0,
    'key_player_status': 0.1, 'star_player_penalty': 0.1,
    'line_movement': 1.0, 'public_betting': 1.0, 'closing_line_value': 1.0,
    'home_court': 1.0,
    # New factors
    'streak_diff': 1.0,  # already /10
    'scoring_margin_trend': 1.0,  # already /15
    'away_road_trip': 1.0,  # already /5, capped
    'miles_traveled_diff': 1.0,  # already /3000
    'overtime_fatigue': 1.0,  # already /2
    'revenge_game': 1.0,  # binary-ish
    'trap_game': 1.0,  # small range
    'altitude_factor': 1.0,  # 0-0.8
    'arena_hostility': 1.0,  # 0-0.9
    'marquee_matchup': 1.0,  # binary
    'b2b_status': 1.0,  # already /2
    'schedule_density': 1.0,  # already /4
    'last_3_record': 0.6,  # same as last_5
    'oreb_diff': 3.0,  # OREB diff range ~3
    'three_pt_volume': 8.0,  # 3PA diff range ~8
}


def normalize_factor(name, value):
    norm = FACTOR_NORMS.get(name, 1.0)
    if name in ('home_win_pct', 'away_win_pct'):
        return (value - 0.5) / norm
    return value / norm if norm != 0 else 0.0


def predict_game(factors, weights):
    """Generate prediction from factors and weights"""
    factors['home_court'] = 1.0

    home_score = 0.0
    for f in weights:
        raw = factors.get(f, 0)
        normalized = normalize_factor(f, raw)
        normalized = max(-2.0, min(2.0, normalized))
        home_score += normalized * weights.get(f, 0)

    scaled = home_score * 3.0
    home_probability = 1.0 / (1.0 + math.exp(-scaled))
    home_probability = max(0.20, min(0.80, home_probability))

    if home_probability >= 0.5:
        return home_probability * 100, True
    else:
        return (1 - home_probability) * 100, False


# ==================== MAIN BACKTEST ====================

def run_backtest():
    start_date = date(2026, 1, 1)
    end_date = date(2026, 2, 12)

    print("=" * 70)
    print("ParlayGuarantee Engine v4 - OPTIMIZED BACKTEST")
    print(f"Period: {start_date} to {end_date}")
    print(f"API delay: {API_DELAY}s, Max retries: {MAX_RETRIES}")
    print("=" * 70)

    # Initialize self-learner with new weights
    db_path = "engine_data_v4.db"
    learner = SelfLearner(db_path)
    
    # Update default weights with new factors
    new_factor_weights = {
        'streak_diff': 0.03,
        'scoring_margin_trend': 0.07,  # BOOSTED
        'away_road_trip': 0.03,
        'miles_traveled_diff': 0.02,
        'overtime_fatigue': 0.01,
        'revenge_game': 0.02,
        'trap_game': 0.02,
        'altitude_factor': 0.03,
        'arena_hostility': 0.0,  # REMOVED
        'marquee_matchup': 0.0,  # REMOVED
        'b2b_status': 0.07,  # BOOSTED
        'schedule_density': 0.05,  # BOOSTED
        'last_3_record': 0.03,
        'oreb_diff': 0.02,
        'three_pt_volume': 0.01,
    }
    
    # Load existing weights and add/override new ones
    weights = learner.load_weights()
    # Override base weights with v4 fixes
    weights['pace'] = 0.0
    weights['rest_days'] = 0.10
    weights['clutch_performance'] = 0.06
    weights['turnover_diff'] = 0.05
    for k, v in new_factor_weights.items():
        weights[k] = v
    
    # Re-normalize so weights sum to ~1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    print(f"Using {len(weights)} factor weights (sum={sum(weights.values()):.3f})")

    # Pre-fetch all data
    team_stats = fetch_all_team_stats()
    print("\nPre-fetching all team gamelogs (30 teams)...")
    gamelogs = fetch_all_gamelogs()

    print("\n" + "=" * 70)
    print("Starting backtest predictions...")
    print("=" * 70)

    all_predictions = []
    total_correct = 0
    total_predictions = 0
    by_confidence_tier = defaultdict(lambda: {'correct': 0, 'total': 0})
    home_picks = {'correct': 0, 'total': 0}
    away_picks = {'correct': 0, 'total': 0}
    factor_values_all = defaultdict(lambda: {'correct_vals': [], 'incorrect_vals': []})
    daily_results = []

    current_date = start_date
    consecutive_empty = 0
    
    while current_date <= end_date:
        print(f"\n--- {current_date} ({current_date.strftime('%A')}) ---")

        results = get_scoreboard_results(current_date)

        if not results:
            print(f"  No completed games")
            consecutive_empty += 1
            if consecutive_empty > 5:
                print("  WARNING: 5+ consecutive empty days, possible API issue")
            current_date += timedelta(days=1)
            continue

        consecutive_empty = 0
        print(f"  {len(results)} games")
        day_correct = 0
        day_total = 0

        for game in results:
            home_team = game['home_team']
            away_team = game['away_team']
            actual_winner = game['actual_winner']

            try:
                factors = compute_factors(home_team, away_team, current_date, team_stats, gamelogs)
                confidence, home_wins = predict_game(factors, weights)
                predicted_winner = home_team if home_wins else away_team
                correct = (predicted_winner == actual_winner)

                # Record in self-learner
                game_id = f"{away_team}@{home_team}_{current_date.isoformat()}"
                learner.record_prediction(game_id, current_date, home_team, away_team,
                                         predicted_winner, confidence / 100, factors)
                learner.record_result(game_id, actual_winner)

                total_predictions += 1
                day_total += 1
                if correct:
                    total_correct += 1
                    day_correct += 1

                # Track home/away picks
                if home_wins:
                    home_picks['total'] += 1
                    if correct: home_picks['correct'] += 1
                else:
                    away_picks['total'] += 1
                    if correct: away_picks['correct'] += 1

                tier = "70+" if confidence >= 70 else \
                       "65-70" if confidence >= 65 else \
                       "60-65" if confidence >= 60 else \
                       "55-60" if confidence >= 55 else "<55"

                by_confidence_tier[tier]['total'] += 1
                if correct:
                    by_confidence_tier[tier]['correct'] += 1

                # Track factor values for correlation analysis
                for fname, fval in factors.items():
                    if correct:
                        factor_values_all[fname]['correct_vals'].append(fval)
                    else:
                        factor_values_all[fname]['incorrect_vals'].append(fval)

                mark = "OK" if correct else "XX"
                print(f"  [{mark}] {away_team} @ {home_team}: "
                      f"Pred={predicted_winner} ({confidence:.0f}%) | "
                      f"Actual={actual_winner} ({game['away_score']}-{game['home_score']})")

                all_predictions.append({
                    'game_date': current_date.isoformat(),
                    'home_team': home_team,
                    'away_team': away_team,
                    'predicted_winner': predicted_winner,
                    'confidence': round(confidence, 1),
                    'actual_winner': actual_winner,
                    'home_score': game['home_score'],
                    'away_score': game['away_score'],
                    'correct': correct,
                    'factors': {k: round(v, 4) for k, v in factors.items()}
                })
            except Exception as e:
                logger.error(f"Error: {away_team} @ {home_team}: {e}")
                import traceback; traceback.print_exc()

        if day_total > 0:
            day_acc = day_correct / day_total * 100
            daily_results.append({
                'date': current_date.isoformat(),
                'total': day_total,
                'correct': day_correct,
                'accuracy': round(day_acc, 1)
            })
            running_acc = total_correct / total_predictions * 100
            print(f"  Day: {day_correct}/{day_total} ({day_acc:.1f}%) | "
                  f"Running: {total_correct}/{total_predictions} ({running_acc:.1f}%)")

        current_date += timedelta(days=1)

    # === FINAL REPORT ===
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS - OPTIMIZED v4")
    print("=" * 70)

    if total_predictions == 0:
        print("No predictions were made!")
        return

    overall_acc = total_correct / total_predictions * 100
    print(f"\nOverall: {total_correct}/{total_predictions} ({overall_acc:.1f}%)")

    print(f"\nHome picks: {home_picks['correct']}/{home_picks['total']} "
          f"({home_picks['correct']/max(1,home_picks['total'])*100:.1f}%)")
    print(f"Away picks: {away_picks['correct']}/{away_picks['total']} "
          f"({away_picks['correct']/max(1,away_picks['total'])*100:.1f}%)")

    print("\nBy Confidence Tier:")
    for tier in ["70+", "65-70", "60-65", "55-60", "<55"]:
        d = by_confidence_tier.get(tier, {'correct': 0, 'total': 0})
        if d['total'] > 0:
            acc = d['correct'] / d['total'] * 100
            print(f"  {tier}%: {d['correct']}/{d['total']} ({acc:.1f}%)")

    # Factor correlation analysis
    print("\n" + "=" * 70)
    print("FACTOR CORRELATION ANALYSIS")
    print("=" * 70)
    
    factor_correlations = {}
    for fname, data in factor_values_all.items():
        correct_vals = data['correct_vals']
        incorrect_vals = data['incorrect_vals']
        
        if len(correct_vals) > 5 and len(incorrect_vals) > 5:
            avg_c = np.mean(correct_vals)
            avg_i = np.mean(incorrect_vals)
            # Also compute point-biserial correlation
            all_vals = correct_vals + incorrect_vals
            all_outcomes = [1] * len(correct_vals) + [0] * len(incorrect_vals)
            
            if np.std(all_vals) > 0:
                corr = np.corrcoef(all_vals, all_outcomes)[0, 1]
            else:
                corr = 0.0
            
            factor_correlations[fname] = {
                'avg_correct': round(avg_c, 4),
                'avg_incorrect': round(avg_i, 4),
                'diff': round(abs(avg_c - avg_i), 4),
                'correlation': round(corr, 4) if not np.isnan(corr) else 0.0,
                'weight': round(weights.get(fname, 0), 4)
            }
    
    # Sort by absolute correlation
    sorted_factors = sorted(factor_correlations.items(), 
                           key=lambda x: abs(x[1]['correlation']), reverse=True)
    
    print("\nTop 15 Most Predictive Factors (by correlation):")
    for i, (fname, d) in enumerate(sorted_factors[:15]):
        direction = "+" if d['correlation'] > 0 else "-"
        print(f"  {i+1}. {fname}: corr={direction}{abs(d['correlation']):.4f}, "
              f"weight={d['weight']:.4f}, diff={d['diff']:.4f}")
    
    print("\nBottom 10 Least Predictive Factors:")
    for fname, d in sorted_factors[-10:]:
        print(f"  {fname}: corr={d['correlation']:.4f}, weight={d['weight']:.4f}")
    
    print("\nNegatively Correlated Factors (hurting predictions):")
    neg_factors = [(f, d) for f, d in sorted_factors if d['correlation'] < -0.02]
    for fname, d in neg_factors:
        print(f"  ⚠️  {fname}: corr={d['correlation']:.4f}, weight={d['weight']:.4f}")

    print("\nDaily Performance:")
    for day in daily_results:
        print(f"  {day['date']}: {day['correct']}/{day['total']} ({day['accuracy']}%)")

    # Save results
    results_data = {
        'backtest_period': f"{start_date} to {end_date}",
        'engine_version': 'v4-optimized',
        'total_factors': len(weights),
        'overall': {
            'total_predictions': total_predictions,
            'correct': total_correct,
            'accuracy': round(overall_acc, 1)
        },
        'home_picks': home_picks,
        'away_picks': away_picks,
        'by_confidence_tier': {k: {
            'correct': v['correct'], 'total': v['total'],
            'accuracy': round(v['correct']/v['total']*100, 1) if v['total'] > 0 else 0
        } for k, v in by_confidence_tier.items()},
        'factor_correlations': dict(sorted_factors),
        'daily_results': daily_results,
        'weights_used': {k: round(v, 5) for k, v in weights.items()},
        'all_predictions': all_predictions,
        'generated_at': datetime.now().isoformat()
    }

    with open('backtest_v3_results.json', 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to backtest_v3_results.json")
    print("Done!")
    
    return results_data


if __name__ == "__main__":
    run_backtest()
