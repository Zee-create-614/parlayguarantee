#!/usr/bin/env python3
"""Debug script to check ESPN stats parsing."""

import json
import requests
from totals_model import fetch_team_stats, parse_team_stats, find_team_id

# Test with Lakers
team_id = find_team_id("Los Angeles Lakers", "nba")
print(f"Lakers team ID: {team_id}")

if team_id:
    raw_stats = fetch_team_stats(team_id, "nba")
    print(f"\nRaw stats keys: {list(raw_stats.keys())}")
    
    if 'results' in raw_stats:
        print(f"Results keys: {list(raw_stats['results'].keys())}")
        
        if 'stats' in raw_stats['results']:
            print(f"Stats keys: {list(raw_stats['results']['stats'].keys())}")
            
            categories = raw_stats['results']['stats'].get('categories', [])
            print(f"\nFound {len(categories)} stat categories:")
            
            for cat in categories[:3]:  # First 3 categories
                print(f"Category: {cat.get('name')} - {cat.get('displayName')}")
                stats = cat.get('stats', [])
                print(f"  Stats count: {len(stats)}")
                
                for stat in stats[:5]:  # First 5 stats
                    print(f"    {stat.get('name')}: {stat.get('displayValue')} ({stat.get('value')})")
    
    # Test parsing
    parsed = parse_team_stats(raw_stats)
    print(f"\nParsed stats: {json.dumps(parsed, indent=2)}")