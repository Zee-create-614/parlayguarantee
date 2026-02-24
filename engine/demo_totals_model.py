#!/usr/bin/env python3
"""Demo script showing the working totals model."""

import json
from totals_model import predict_total, enhance_games_with_totals_model
from datetime import datetime, timezone, timedelta

print("=" * 60)
print("TOTALS MODEL DEMO - PARLAYGUARANTEE")
print("=" * 60)

# Test individual predictions
print("\n1. INDIVIDUAL PREDICTIONS:")
print("-" * 40)

test_games = [
    ("Los Angeles Lakers", "Boston Celtics", 225.5, "nba", "High-scoring teams"),
    ("Dallas Mavericks", "Indiana Pacers", 233.5, "nba", "Today's actual game"),
    ("Orlando Magic", "Los Angeles Clippers", 215.5, "nba", "Up-tempo matchup"), 
    ("Houston Cougars", "Kansas Jayhawks", 136.5, "ncaab", "Big 12 showdown"),
]

for home, away, line, sport, note in test_games:
    print(f"\n{away} @ {home} ({note})")
    print(f"Vegas Line: {line}")
    
    result = predict_total(home, away, line, sport)
    
    if result.get('error'):
        print(f"Error: {result['error']}")
        continue
        
    proj = result['projected_total']
    delta = result['delta']
    pick = result['pick']
    conf = result['confidence']
    
    print(f"Model Projection: {proj}")
    print(f"Delta: {delta:+.1f}")
    print(f"Pick: {pick if pick else 'PASS'}")
    print(f"Confidence: {conf:.0%}" if conf > 0 else "Confidence: SKIP")
    
    factors = result.get('factors', {})
    home_ppg = factors.get('home_ppg', 0)
    away_ppg = factors.get('away_ppg', 0)
    pace_f = factors.get('pace_factor', 1)
    
    print(f"Factors: Home {home_ppg:.1f}ppg, Away {away_ppg:.1f}ppg, Pace {pace_f:.2f}")

print("\n" + "=" * 60)
print("2. MODEL COMPARISON VS OLD METHOD:")
print("-" * 40)

# Load today's analyzed games if available
today = datetime.now(timezone(timedelta(hours=-5))).strftime('%Y-%m-%d')
games_file = "analyzed_games.json"

try:
    with open(games_file) as f:
        games = json.load(f)
    
    # Get first 5 games with totals
    total_games = [g for g in games if g.get('total_line') and g.get('total_line') > 0][:5]
    
    print(f"\nFound {len(total_games)} games with totals from today's data:")
    
    for i, game in enumerate(total_games, 1):
        home = game.get('home', '')
        away = game.get('away', '') 
        vegas_line = game.get('total_line', 0)
        sport = 'nba' if game.get('sport') == 'NBA' else 'ncaab'
        
        # Get old devigged prediction
        old_pick = game.get('ou_pick', 'None')
        old_prob = game.get('ou_prob', 0)
        
        # Get new model prediction
        model_result = predict_total(home, away, vegas_line, sport)
        new_pick = model_result.get('pick', 'None')
        new_conf = model_result.get('confidence', 0)
        new_proj = model_result.get('projected_total', vegas_line)
        
        print(f"\n{i}. {away} @ {home}")
        print(f"   Vegas: {vegas_line}")
        print(f"   Old Method: {old_pick} ({old_prob:.0%})")
        print(f"   New Model: {new_pick} ({new_conf:.0%}) - Projects {new_proj}")
        
        agreement = "AGREE" if old_pick == new_pick else "DISAGREE"
        print(f"   Agreement: {agreement}")

except FileNotFoundError:
    print("No analyzed_games.json found - run autopilot first")

print("\n" + "=" * 60)
print("3. KEY IMPROVEMENTS:")
print("-" * 40)
print("+ Uses REAL team statistics from ESPN API")
print("+ Calculates pace-adjusted offensive/defensive efficiency") 
print("+ Factors in venue, rest, and recent trends")
print("+ Compares our projection vs Vegas line for true edge")
print("+ Confidence based on projection delta (not just devigged odds)")
print("+ Supports both NBA and NCAAB with different pace profiles")
print("+ Integrated into autopilot.py pipeline")
print("+ Replaces the old 'devigged consensus' method")

print("\n" + "=" * 60)
print("MODEL IS READY FOR PRODUCTION!")
print("=" * 60)