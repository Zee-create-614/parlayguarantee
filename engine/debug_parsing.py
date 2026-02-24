#!/usr/bin/env python3
"""Debug the parsing logic step by step."""

import json
from totals_model import fetch_team_stats, find_team_id

def debug_parse_team_stats(stats_data):
    """Debug version of parse_team_stats with print statements."""
    parsed = {
        'points_per_game': 0,
        'points_allowed_per_game': 0,
        'field_goal_pct': 0,
        'three_point_pct': 0,
        'free_throw_pct': 0,
        'rebounds_per_game': 0,
        'assists_per_game': 0,
        'turnovers_per_game': 0,
        'steals_per_game': 0,
        'blocks_per_game': 0,
        'possessions_per_game': 0,
        'offensive_efficiency': 0,
        'defensive_efficiency': 0,
    }
    
    if not stats_data:
        return parsed
    
    try:
        splits = stats_data.get('results', {}).get('stats', {})
        categories = splits.get('categories', [])
        
        print(f"Processing {len(categories)} categories...")
        
        for category in categories:
            cat_name = category.get('name', '').lower()
            stats = category.get('stats', [])
            
            print(f"\nCategory: {cat_name} ({len(stats)} stats)")
            
            for stat in stats:
                stat_name = stat.get('name', '').lower()
                display_name = stat.get('displayName', '')
                value = stat.get('value', 0)
                
                try:
                    value = float(value) if value and value != '--' else 0
                except (ValueError, TypeError):
                    value = 0
                
                print(f"  Processing: '{stat_name}' = {value}")
                
                # Map ESPN stat names to our format (using exact lowercase names)
                if stat_name == 'avgpoints':
                    print(f"    -> Setting points_per_game = {value}")
                    parsed['points_per_game'] = value
                elif stat_name == 'fieldgoalpct':
                    pct_value = value / 100 if value > 1 else value
                    print(f"    -> Setting field_goal_pct = {pct_value}")
                    parsed['field_goal_pct'] = pct_value
                elif stat_name == 'threepointpct':
                    pct_value = value / 100 if value > 1 else value
                    print(f"    -> Setting three_point_pct = {pct_value}")
                    parsed['three_point_pct'] = pct_value
                elif stat_name == 'freethrowpct':
                    pct_value = value / 100 if value > 1 else value
                    print(f"    -> Setting free_throw_pct = {pct_value}")
                    parsed['free_throw_pct'] = pct_value
                elif stat_name == 'avgrebounds':
                    print(f"    -> Setting rebounds_per_game = {value}")
                    parsed['rebounds_per_game'] = value
                elif stat_name == 'avgassists':
                    print(f"    -> Setting assists_per_game = {value}")
                    parsed['assists_per_game'] = value
                elif stat_name == 'avgturnovers':
                    print(f"    -> Setting turnovers_per_game = {value}")
                    parsed['turnovers_per_game'] = value
                elif stat_name == 'avgsteals':
                    print(f"    -> Setting steals_per_game = {value}")
                    parsed['steals_per_game'] = value
                elif stat_name == 'avgblocks':
                    print(f"    -> Setting blocks_per_game = {value}")
                    parsed['blocks_per_game'] = value
        
        print(f"\nFinal parsed stats: {json.dumps(parsed, indent=2)}")
        
    except Exception as e:
        print(f"Error in parsing: {e}")
    
    return parsed

# Test with Lakers
team_id = find_team_id("Los Angeles Lakers", "nba")
print(f"Lakers team ID: {team_id}")

if team_id:
    raw_stats = fetch_team_stats(team_id, "nba")
    parsed = debug_parse_team_stats(raw_stats)