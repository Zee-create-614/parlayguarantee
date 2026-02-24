"""
Demo script for ParlayGuarantee Engine
Demonstrates the engine with sample data when live NBA games aren't available
"""
import sys
import os
import json
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from analyzer import GameAnalyzer, GameAnalysis
from parlay_generator import ParlayGenerator
from config import *

def create_demo_data():
    """Create sample data for demonstration"""
    
    # Sample games for today
    games = [
        {
            'game_id': 'demo_1',
            'home_team': 'Boston Celtics',
            'away_team': 'Los Angeles Lakers',
            'game_time': '2026-02-15T20:00:00',
            'home_team_id': 1610612738,
            'away_team_id': 1610612747
        },
        {
            'game_id': 'demo_2', 
            'home_team': 'Golden State Warriors',
            'away_team': 'Denver Nuggets',
            'game_time': '2026-02-15T22:00:00',
            'home_team_id': 1610612744,
            'away_team_id': 1610612743
        },
        {
            'game_id': 'demo_3',
            'home_team': 'Miami Heat',
            'away_team': 'Milwaukee Bucks',
            'game_time': '2026-02-15T19:30:00',
            'home_team_id': 1610612748,
            'away_team_id': 1610612749
        },
        {
            'game_id': 'demo_4',
            'home_team': 'Phoenix Suns',
            'away_team': 'Dallas Mavericks',
            'game_time': '2026-02-15T21:00:00',
            'home_team_id': 1610612756,
            'away_team_id': 1610612742
        }
    ]
    
    # Sample team stats
    team_stats = {
        'Boston Celtics': {
            'team_id': 1610612738,
            'games_played': 55,
            'wins': 36,
            'losses': 19,
            'win_pct': 0.655,
            'offensive_rating': 118.5,
            'defensive_rating': 110.2,
            'pace': 98.5,
            'points_per_game': 118.2,
            'opp_points_per_game': 110.8
        },
        'Los Angeles Lakers': {
            'team_id': 1610612747,
            'games_played': 54,
            'wins': 30,
            'losses': 24,
            'win_pct': 0.556,
            'offensive_rating': 115.3,
            'defensive_rating': 112.8,
            'pace': 101.2,
            'points_per_game': 115.7,
            'opp_points_per_game': 113.1
        },
        'Golden State Warriors': {
            'team_id': 1610612744,
            'games_played': 55,
            'wins': 31,
            'losses': 24,
            'win_pct': 0.564,
            'offensive_rating': 114.8,
            'defensive_rating': 113.5,
            'pace': 102.1,
            'points_per_game': 117.2,
            'opp_points_per_game': 115.8
        },
        'Denver Nuggets': {
            'team_id': 1610612743,
            'games_played': 54,
            'wins': 34,
            'losses': 20,
            'win_pct': 0.630,
            'offensive_rating': 117.2,
            'defensive_rating': 111.8,
            'pace': 99.3,
            'points_per_game': 116.4,
            'opp_points_per_game': 111.0
        },
        'Miami Heat': {
            'team_id': 1610612748,
            'games_played': 55,
            'wins': 28,
            'losses': 27,
            'win_pct': 0.509,
            'offensive_rating': 112.1,
            'defensive_rating': 113.2,
            'pace': 97.8,
            'points_per_game': 109.6,
            'opp_points_per_game': 110.7
        },
        'Milwaukee Bucks': {
            'team_id': 1610612749,
            'games_played': 55,
            'wins': 32,
            'losses': 23,
            'win_pct': 0.582,
            'offensive_rating': 116.8,
            'defensive_rating': 112.4,
            'pace': 100.2,
            'points_per_game': 117.0,
            'opp_points_per_game': 112.6
        },
        'Phoenix Suns': {
            'team_id': 1610612756,
            'games_played': 54,
            'wins': 29,
            'losses': 25,
            'win_pct': 0.537,
            'offensive_rating': 114.5,
            'defensive_rating': 113.8,
            'pace': 101.5,
            'points_per_game': 116.2,
            'opp_points_per_game': 115.4
        },
        'Dallas Mavericks': {
            'team_id': 1610612742,
            'games_played': 55,
            'wins': 33,
            'losses': 22,
            'win_pct': 0.600,
            'offensive_rating': 117.8,
            'defensive_rating': 112.9,
            'pace': 100.8,
            'points_per_game': 118.7,
            'opp_points_per_game': 113.8
        }
    }
    
    # Sample odds (simplified)
    odds = [
        {
            'teams': ['Los Angeles Lakers', 'Boston Celtics'],
            'bookmakers': [{
                'markets': [
                    {
                        'key': 'h2h',
                        'outcomes': [
                            {'name': 'Boston Celtics', 'price': -165},
                            {'name': 'Los Angeles Lakers', 'price': 140}
                        ]
                    },
                    {
                        'key': 'spreads',
                        'outcomes': [
                            {'name': 'Boston Celtics', 'price': -110, 'point': -4.5},
                            {'name': 'Los Angeles Lakers', 'price': -110, 'point': 4.5}
                        ]
                    },
                    {
                        'key': 'totals',
                        'outcomes': [
                            {'name': 'Over', 'price': -110, 'point': 228.5},
                            {'name': 'Under', 'price': -110, 'point': 228.5}
                        ]
                    }
                ]
            }]
        },
        {
            'teams': ['Denver Nuggets', 'Golden State Warriors'],
            'bookmakers': [{
                'markets': [
                    {
                        'key': 'h2h',
                        'outcomes': [
                            {'name': 'Golden State Warriors', 'price': 105},
                            {'name': 'Denver Nuggets', 'price': -125}
                        ]
                    },
                    {
                        'key': 'spreads',
                        'outcomes': [
                            {'name': 'Golden State Warriors', 'price': -110, 'point': 2.5},
                            {'name': 'Denver Nuggets', 'price': -110, 'point': -2.5}
                        ]
                    },
                    {
                        'key': 'totals',
                        'outcomes': [
                            {'name': 'Over', 'price': -108, 'point': 233.5},
                            {'name': 'Under', 'price': -112, 'point': 233.5}
                        ]
                    }
                ]
            }]
        }
    ]
    
    # Sample injury data
    injuries = {
        'Boston Celtics': {
            'out': [],
            'doubtful': ['Kristaps Porzingis'],
            'questionable': [],
            'probable': []
        },
        'Los Angeles Lakers': {
            'out': [],
            'doubtful': [],
            'questionable': ['Anthony Davis'],
            'probable': []
        },
        'Golden State Warriors': {
            'out': ['Draymond Green'],
            'doubtful': [],
            'questionable': [],
            'probable': ['Andrew Wiggins']
        },
        'Denver Nuggets': {
            'out': [],
            'doubtful': [],
            'questionable': [],
            'probable': []
        },
        'Miami Heat': {
            'out': ['Jimmy Butler'],
            'doubtful': [],
            'questionable': ['Tyler Herro'],
            'probable': []
        },
        'Milwaukee Bucks': {
            'out': [],
            'doubtful': [],
            'questionable': [],
            'probable': []
        },
        'Phoenix Suns': {
            'out': [],
            'doubtful': ['Bradley Beal'],
            'questionable': [],
            'probable': []
        },
        'Dallas Mavericks': {
            'out': [],
            'doubtful': [],
            'questionable': [],
            'probable': []
        }
    }
    
    return {
        'timestamp': datetime.now().isoformat(),
        'sport': 'NBA',
        'games': games,
        'team_stats': team_stats,
        'odds': odds,
        'injuries': injuries,
        'api_usage': {'remaining': 450, 'used': 50}
    }

def run_demo():
    """Run the complete engine demo"""
    print("ParlayGuarantee Engine Demo")
    print("=" * 50)
    
    # Create demo data
    print("Creating sample NBA data...")
    demo_data = create_demo_data()
    print(f"   - {len(demo_data['games'])} games")
    print(f"   - {len(demo_data['team_stats'])} teams with stats")
    print(f"   - {len(demo_data['odds'])} games with odds")
    
    # Analyze games
    print("\nAnalyzing games...")
    analyzer = GameAnalyzer(demo_data)
    analyses = analyzer.analyze_all_games()
    
    print(f"   >> Analyzed {len(analyses)} games")
    for analysis in analyses:
        print(f"   - {analysis.away_team} @ {analysis.home_team}")
        print(f"     Spread: {analysis.spread_pick} ({analysis.spread_confidence:.0f}%)")
        print(f"     ML: {analysis.moneyline_pick} ({analysis.moneyline_confidence:.0f}%)")
        print(f"     Total: {analysis.total_pick} ({analysis.total_confidence:.0f}%)")
    
    # Generate parlays
    print("\nGenerating parlays...")
    generator = ParlayGenerator(analyses)
    parlays = generator.generate_all_parlays()
    
    print(f"   >> Generated {len(parlays)} parlays")
    
    # Show parlay summary
    leg_counts = {}
    for parlay in parlays:
        legs = parlay.legs
        leg_counts[legs] = leg_counts.get(legs, 0) + 1
    
    for legs, count in sorted(leg_counts.items()):
        print(f"   - {legs}-leg parlays: {count}")
    
    # Export results
    print("\nExporting results...")
    output_file = "demo_picks.json"
    output_data = generator.export_to_json(parlays, output_file)
    
    print(f"   >> Exported to {output_file}")
    
    # Show detailed parlay breakdown
    print("\nGenerated Parlays:")
    print("-" * 50)
    
    for parlay in parlays[:5]:  # Show first 5 parlays
        print(f"\nParlay {parlay.id}: {parlay.type}")
        print(f"Combined Odds: {parlay.combined_odds} (Confidence: {parlay.confidence:.0f}%)")
        print("Picks:")
        
        for pick in parlay.picks:
            print(f"  >> {pick.game}")
            print(f"    {pick.pick} ({pick.odds})")
            print(f"    Reasoning: {pick.reasoning}")
        
        print(f"Potential Payout: $100 -> {parlay.potential_payout['$100']}")
    
    if len(parlays) > 5:
        print(f"\n... and {len(parlays) - 5} more parlays")
    
    # Summary
    print("\nSummary:")
    print(f"   - Total Games Analyzed: {len(analyses)}")
    print(f"   - Total Parlays Generated: {len(parlays)}")
    print(f"   - Confidence Range: {min(p.confidence for p in parlays):.0f}% - {max(p.confidence for p in parlays):.0f}%")
    print(f"   - Output File: {output_file}")
    
    print("\n>> Demo Complete!")
    print("The engine is ready for production use with real NBA data.")
    
    return output_file

if __name__ == "__main__":
    output_file = run_demo()
    
    # Show final JSON structure
    print(f"\nSample Output Structure ({output_file}):")
    print("-" * 50)
    
    try:
        with open(output_file, 'r') as f:
            data = json.load(f)
        
        # Show structure without full content
        sample_structure = {
            "generated_at": data["generated_at"],
            "date": data["date"],
            "sport": data["sport"],
            "games_analyzed": data["games_analyzed"],
            "parlays": f"[{len(data['parlays'])} parlay objects]",
            "track_record_entry": data["track_record_entry"]
        }
        
        print(json.dumps(sample_structure, indent=2))
        
        print(f"\n>> This JSON can be consumed directly by your website frontend!")
        
    except Exception as e:
        print(f"Error reading output file: {e}")