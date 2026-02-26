#!/usr/bin/env python3
"""Fetch NBA.com stats and output JSON. Run on VPS where NBA.com isn't blocked."""
import requests, json, sys

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.nba.com/',
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true'
}

def fetch_team_ratings():
    url = "https://stats.nba.com/stats/leaguedashteamstats"
    params = {
        'Conference':'','DateFrom':'','DateTo':'','Division':'','GameScope':'',
        'GameSegment':'','Height':'','ISTRound':'','LastNGames':'0','LeagueID':'00',
        'Location':'','MeasureType':'Advanced','Month':'0','OpponentTeamID':'0',
        'Outcome':'','PORound':'0','PaceAdjust':'N','PerMode':'PerGame','Period':'0',
        'PlayerExperience':'','PlayerPosition':'','PlusMinus':'N','Rank':'N',
        'Season':'2025-26','SeasonSegment':'','SeasonType':'Regular Season',
        'ShotClockRange':'','StarterBench':'','TeamID':'0','TwoWay':'0',
        'VsConference':'','VsDivision':'',
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    hs = data['resultSets'][0]['headers']
    rows = data['resultSets'][0]['rowSet']
    idx = {h:i for i,h in enumerate(hs)}
    result = {}
    for row in rows:
        name = row[idx.get('TEAM_NAME',1)]
        result[name] = {
            'ortg': row[idx.get('OFF_RATING',0)],
            'drtg': row[idx.get('DEF_RATING',0)],
            'net_rtg': row[idx.get('NET_RATING',0)],
            'pace': row[idx.get('PACE',0)],
        }
    return result

def fetch_clutch():
    url = "https://stats.nba.com/stats/leaguedashteamclutch"
    params = {
        'AheadBehind':'Ahead or Behind','ClutchTime':'Last 5 Minutes',
        'Conference':'','DateFrom':'','DateTo':'','Division':'','GameScope':'',
        'GameSegment':'','Height':'','ISTRound':'','LastNGames':'0','LeagueID':'00',
        'Location':'','MeasureType':'Base','Month':'0','OpponentTeamID':'0',
        'Outcome':'','PORound':'0','PaceAdjust':'N','PerMode':'PerGame','Period':'0',
        'PlayerExperience':'','PlayerPosition':'','PlusMinus':'N','PointDiff':'5',
        'Rank':'N','Season':'2025-26','SeasonSegment':'','SeasonType':'Regular Season',
        'ShotClockRange':'','StarterBench':'','TeamID':'0','VsConference':'','VsDivision':'',
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    hs = data['resultSets'][0]['headers']
    rows = data['resultSets'][0]['rowSet']
    idx = {h:i for i,h in enumerate(hs)}
    result = {}
    for row in rows:
        name = row[idx.get('TEAM_NAME',1)]
        result[name] = {
            'clutch_w': row[idx.get('W',0)],
            'clutch_l': row[idx.get('L',0)],
            'clutch_win_pct': row[idx.get('W_PCT',0)],
            'clutch_pts': row[idx.get('PTS',0)],
            'clutch_plus_minus': row[idx.get('PLUS_MINUS',0)],
        }
    return result

def fetch_player_advanced():
    url = "https://stats.nba.com/stats/leaguedashplayerstats"
    params = {
        'Conference':'','DateFrom':'','DateTo':'','Division':'','GameScope':'',
        'GameSegment':'','Height':'','ISTRound':'','LastNGames':'0','LeagueID':'00',
        'Location':'','MeasureType':'Advanced','Month':'0','OpponentTeamID':'0',
        'Outcome':'','PORound':'0','PaceAdjust':'N','PerMode':'PerGame','Period':'0',
        'PlayerExperience':'','PlayerPosition':'','PlusMinus':'N','Rank':'N',
        'Season':'2025-26','SeasonSegment':'','SeasonType':'Regular Season',
        'ShotClockRange':'','StarterBench':'','TeamID':'0',
    }
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    hs = data['resultSets'][0]['headers']
    rows = data['resultSets'][0]['rowSet']
    idx = {h:i for i,h in enumerate(hs)}
    by_team = {}
    for row in rows:
        team = row[idx.get('TEAM_ABBREVIATION',0)]
        if team not in by_team:
            by_team[team] = []
        by_team[team].append({
            'name': row[idx.get('PLAYER_NAME','')] if 'PLAYER_NAME' in idx else '',
            'pie': row[idx.get('PIE',0)] if 'PIE' in idx else 0,
            'usage': row[idx.get('USG_PCT',0)] if 'USG_PCT' in idx else 0,
            'ts_pct': row[idx.get('TS_PCT',0)] if 'TS_PCT' in idx else 0,
        })
    return by_team

if __name__ == '__main__':
    output = {}
    for name, fn in [('team_ratings', fetch_team_ratings), ('clutch_stats', fetch_clutch), ('player_advanced', fetch_player_advanced)]:
        try:
            data = fn()
            output[name] = data
            print(f"OK: {name} = {len(data) if data else 0} entries", file=sys.stderr)
        except Exception as e:
            output[name] = None
            print(f"FAIL: {name} = {e}", file=sys.stderr)
    
    print(json.dumps(output))
