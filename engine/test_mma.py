"""Quick test of MMA Engine — matchups + picks generation."""
import json
import sys
from mma_engine import MMAEngine

engine = MMAEngine()

# Test 1: Specific matchup
print("=" * 60)
print("TEST 1: Islam Makhachev vs Charles Oliveira")
print("=" * 60)
r = engine.calculate_matchup("Islam Makhachev", "Charles Oliveira", is_title=True)
print(f"  Winner: {r['predicted_winner']} ({r['confidence']}%)")
print(f"  Method: {r['method_prediction']}")
print(f"  Probs: {r['fighter1']} {r['f1_probability']:.1%} | {r['fighter2']} {r['f2_probability']:.1%}")
print(f"  Method Dist: KO {r['method_probs']['KO/TKO']:.0%} | SUB {r['method_probs']['Submission']:.0%} | DEC {r['method_probs']['Decision']:.0%}")
print()

# Test 2: Another matchup
print("=" * 60)
print("TEST 2: Jon Jones vs Stipe Miocic")
print("=" * 60)
r2 = engine.calculate_matchup("Jon Jones", "Stipe Miocic")
print(f"  Winner: {r2['predicted_winner']} ({r2['confidence']}%)")
print(f"  Method: {r2['method_prediction']}")
print(f"  Probs: {r2['fighter1']} {r2['f1_probability']:.1%} | {r2['fighter2']} {r2['f2_probability']:.1%}")
print()

# Test 3: Generate picks from odds API (limited)
print("=" * 60)
print("TEST 3: Generate picks from Odds API")
print("=" * 60)
odds = engine.get_odds()
ufc_events = [e for e in odds if "UFC" in e.get("sport_title", "")]
print(f"  Total MMA events: {len(odds)}")
print(f"  UFC events: {len(ufc_events)}")
if ufc_events:
    print(f"  Next UFC event fights:")
    for e in ufc_events[:3]:
        print(f"    {e.get('home_team')} vs {e.get('away_team')} ({e.get('commence_time', '')[:10]})")

print("\nDone!")
