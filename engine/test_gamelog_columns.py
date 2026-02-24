"""
Quick test to see LeagueGameLog column names
"""

import time
from nba_api.stats.endpoints import leaguegamelog

try:
    print("Testing LeagueGameLog API...")
    
    # Get just a small sample - last few days only
    gamelog = leaguegamelog.LeagueGameLog(
        season='2024-25',
        player_or_team_abbreviation='P',
        date_from_nullable='01/10/2025',  # Just last few days
        date_to_nullable='01/15/2025'
    )
    time.sleep(2)
    
    df = gamelog.get_data_frames()[0]
    
    print(f"Found {len(df)} records")
    print("Available columns:")
    for i, col in enumerate(df.columns):
        print(f"  {i+1:2d}. {col}")
    
    if len(df) > 0:
        print("\nFirst record sample:")
        first_row = df.iloc[0]
        for col, val in first_row.items():
            print(f"  {col}: {val}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()