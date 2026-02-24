#!/usr/bin/env python3
"""Debug script to see ALL available ESPN stats."""

import json
from totals_model import fetch_team_stats, find_team_id

# Test with Lakers
team_id = find_team_id("Los Angeles Lakers", "nba")
print(f"Lakers team ID: {team_id}")

if team_id:
    raw_stats = fetch_team_stats(team_id, "nba")
    categories = raw_stats['results']['stats'].get('categories', [])
    
    print(f"\nALL AVAILABLE STATS:")
    print("=" * 60)
    
    for cat in categories:
        print(f"\nCATEGORY: {cat.get('displayName')} ({cat.get('name')})")
        print("-" * 40)
        
        stats = cat.get('stats', [])
        for stat in stats:
            name = stat.get('name', '')
            display = stat.get('displayName', '')
            value = stat.get('displayValue', '')
            raw_val = stat.get('value', 0)
            
            print(f"  {name:<25} | {display:<35} | {value} ({raw_val})")