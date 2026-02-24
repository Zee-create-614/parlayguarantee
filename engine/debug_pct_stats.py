#!/usr/bin/env python3
"""Debug script to see percentage stats."""

from totals_model import fetch_team_stats, find_team_id

team_id = find_team_id("Los Angeles Lakers", "nba")

if team_id:
    raw_stats = fetch_team_stats(team_id, "nba")
    categories = raw_stats['results']['stats'].get('categories', [])
    
    print("PERCENTAGE STATS:")
    print("=" * 50)
    
    for cat in categories:
        stats = cat.get('stats', [])
        for stat in stats:
            name = stat.get('name', '').lower()
            display = stat.get('displayName', '')
            value = stat.get('value', 0)
            
            if 'pct' in name or 'percentage' in display.lower():
                print(f"'{name}' -> {display} = {value}")