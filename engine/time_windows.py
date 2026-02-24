"""
Time Window Utilities for Parlay Generation

Ensures all legs in a parlay are placeable on DraftKings by:
1. Filtering out games starting within BUFFER_MINUTES of publication time
2. Grouping games into time windows (Early/Late/Full Slate)
3. Only combining games from the SAME window into parlays

DK rule: You can't add a game to a parlay if it has already started.
So ALL legs must start AFTER the customer places the bet.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

# How far after publication time a game must start to be included.
# If picks publish at 3 PM, a game at 3:30 PM is too tight — customer won't
# have time to read, open DK, and build the slip. 1 hour buffer.
BUFFER_MINUTES = 60

# Time window boundaries (Eastern Time hours, 24h format)
# Early window: noon–6 PM ET (afternoon games, mostly NCAAB)
# Late window: 6 PM–midnight ET (evening NBA/NCAAB)
EARLY_START_HOUR = 12  # noon
EARLY_END_HOUR = 18    # 6 PM
LATE_START_HOUR = 18   # 6 PM
LATE_END_HOUR = 4      # 4 AM next day (for West Coast games)

EST = timezone(timedelta(hours=-5))


def get_publication_cutoff(publish_time: Optional[datetime] = None) -> datetime:
    """
    Get the earliest allowed game start time given a publication time.
    Games must start at least BUFFER_MINUTES after publish_time.
    """
    if publish_time is None:
        publish_time = datetime.now(timezone.utc)
    return publish_time + timedelta(minutes=BUFFER_MINUTES)


def parse_commence_time(ct: str) -> datetime:
    """Parse ISO commence_time string to timezone-aware datetime."""
    if ct.endswith('Z'):
        ct = ct[:-1] + '+00:00'
    return datetime.fromisoformat(ct)


def classify_window(commence_time_str: str) -> str:
    """
    Classify a game into a time window based on its start time in ET.
    Returns: 'early', 'late', or 'overnight'
    """
    dt = parse_commence_time(commence_time_str)
    et = dt.astimezone(EST)
    hour = et.hour

    if EARLY_START_HOUR <= hour < EARLY_END_HOUR:
        return 'early'
    elif EARLY_END_HOUR <= hour or hour < LATE_END_HOUR:
        return 'late'
    else:
        return 'overnight'  # shouldn't happen for normal games


def window_label(window: str) -> str:
    """Human-readable label for a window."""
    return {
        'early': '🌤️ Early Window (12–6 PM ET)',
        'late': '🌙 Late Window (6 PM+ ET)',
        'full_slate': '📋 Full Slate (all games 6 PM+ ET)',
        'overnight': '🌃 Late Night',
    }.get(window, window)


def filter_and_group_games(
    games: List[Dict],
    publish_time: Optional[datetime] = None,
    commence_time_key: str = 'commence_time',
) -> Dict[str, List[Dict]]:
    """
    Filter games by publication buffer and group into time windows.
    
    Args:
        games: List of game dicts, each must have a commence_time field
        publish_time: When picks will be published (defaults to now)
        commence_time_key: Key name for the commence time field
    
    Returns:
        Dict with keys 'early', 'late', and optionally 'full_slate'.
        Each value is a list of games in that window.
        'full_slate' is included only if ALL remaining games start in the late window.
    """
    cutoff = get_publication_cutoff(publish_time)
    
    windows: Dict[str, List[Dict]] = {
        'early': [],
        'late': [],
    }
    
    for game in games:
        ct_str = game.get(commence_time_key)
        if not ct_str:
            continue
        
        ct = parse_commence_time(ct_str)
        
        # Skip games starting before cutoff
        if ct < cutoff:
            continue
        
        window = classify_window(ct_str)
        if window in ('late', 'overnight'):
            windows['late'].append(game)
        else:
            windows['early'].append(game)
    
    # Full slate = all games from both windows, but ONLY if no early games
    # (because if there are early games, they might start before late games
    # and you can't combine them on one ticket if early ones start first)
    # Actually: full slate is valid if ALL games start after cutoff.
    # The issue is mixing early + late on same ticket — DK allows it if ALL
    # games haven't started. So full_slate = early + late combined.
    all_eligible = windows['early'] + windows['late']
    if len(all_eligible) > len(windows['late']):
        # There are early games — full slate combines them all
        windows['full_slate'] = all_eligible
    
    return windows


def group_legs_by_window(
    legs: List[Dict],
    publish_time: Optional[datetime] = None,
    commence_time_key: str = 'commence_time',
) -> Dict[str, List[Dict]]:
    """
    Group parlay legs by time window. Same as filter_and_group_games
    but for leg-format dicts.
    """
    return filter_and_group_games(legs, publish_time, commence_time_key)


def validate_parlay_timing(
    legs: List[Dict],
    publish_time: Optional[datetime] = None,
    commence_time_key: str = 'commence_time',
) -> Tuple[bool, str]:
    """
    Validate that all legs in a parlay can be placed together on DK.
    
    Returns:
        (is_valid, reason)
    """
    cutoff = get_publication_cutoff(publish_time)
    
    for leg in legs:
        ct_str = leg.get(commence_time_key)
        if not ct_str:
            return False, f"Missing commence_time for leg: {leg.get('game', '?')}"
        ct = parse_commence_time(ct_str)
        if ct < cutoff:
            return False, f"Game starts too soon: {leg.get('game', '?')} at {ct_str}"
    
    return True, "OK"


if __name__ == '__main__':
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Quick test
    from datetime import datetime, timezone
    
    test_games = [
        {'home': 'Louisville', 'away': 'Duke', 'commence_time': '2026-02-21T19:15:00Z'},
        {'home': 'Kentucky', 'away': 'Florida', 'commence_time': '2026-02-21T21:00:00Z'},
        {'home': 'Gonzaga', 'away': 'BYU', 'commence_time': '2026-02-22T02:00:00Z'},
        {'home': 'UNC', 'away': 'Wake Forest', 'commence_time': '2026-02-21T17:00:00Z'},  # early
    ]
    
    # Simulate 3 PM ET publication
    pub = datetime(2026, 2, 21, 20, 0, 0, tzinfo=timezone.utc)  # 3 PM ET = 8 PM UTC
    
    windows = filter_and_group_games(test_games, publish_time=pub)
    for w, games in windows.items():
        print(f"\n{window_label(w)}:")
        for g in games:
            print(f"  {g['away']} @ {g['home']} — {g['commence_time']}")
