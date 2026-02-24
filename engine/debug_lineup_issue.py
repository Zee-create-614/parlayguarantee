#!/usr/bin/env python3
"""
Debug lineup construction issues
"""

import json
import time
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# NBA API imports
from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv3

@dataclass
class Player:
    person_id: str
    name: str
    position: str
    team: str
    stats: Dict[str, Any]
    dk_score: float = 0.0
    projected_dk: float = 0.0
    estimated_salary: int = 0
    
    def __post_init__(self):
        self.calculate_scores()
        self.generate_projections()
        self.estimate_salary()
    
    def calculate_scores(self):
        stats = self.stats
        pts = stats.get('points', 0) or 0
        tpm = stats.get('threePointersMade', 0) or 0
        reb = stats.get('reboundsTotal', 0) or 0
        ast = stats.get('assists', 0) or 0
        stl = stats.get('steals', 0) or 0
        blk = stats.get('blocks', 0) or 0
        to = stats.get('turnovers', 0) or 0
        
        self.dk_score = (pts + tpm*0.5 + reb*1.25 + ast*1.5 + 
                        stl*2 + blk*2 + to*(-0.5))
        
        dd_categories = [pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10]
        dd_count = sum(dd_categories)
        
        if dd_count >= 2:
            self.dk_score += 1.5
        if dd_count >= 3:
            self.dk_score += 3.0
    
    def generate_projections(self):
        self.projected_dk = self.dk_score * random.uniform(0.7, 1.3)
    
    def estimate_salary(self):
        base_salary = int(self.projected_dk * 200 + 3000)
        self.estimated_salary = max(3500, min(12000, base_salary))
    
    def get_position_eligibility(self) -> List[str]:
        pos = (self.position or '').upper().strip()
        
        if pos in ['G', 'G-F']:
            return ['PG', 'SG', 'G', 'UTIL']
        elif pos in ['F', 'F-G']:
            return ['SF', 'PF', 'F', 'UTIL']
        elif pos in ['C', 'C-F', 'F-C']:
            return ['C', 'PF', 'F', 'UTIL']
        else:
            return ['UTIL']

def get_demo_players():
    """Get players from one game for testing"""
    print("Getting players from December 1, 2024...")
    
    # Get games
    time.sleep(2)
    sb = scoreboardv2.ScoreboardV2(game_date='2024-12-01')
    data = sb.get_normalized_dict()
    games = data.get('GameHeader', [])
    
    if not games:
        return []
    
    # Get first game
    game_id = games[0]['GAME_ID']
    print(f"Using game: {game_id}")
    
    time.sleep(2)
    bs = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
    box_data = bs.get_dict()
    
    players = []
    box_score = box_data.get('boxScoreTraditional', {})
    
    for team_key in ['homeTeam', 'awayTeam']:
        team = box_score.get(team_key, {})
        team_name = team.get('teamName', 'Unknown')
        team_players = team.get('players', [])
        
        for player_data in team_players:
            minutes = player_data.get('statistics', {}).get('minutes', '')
            if not minutes or minutes == '0:00':
                continue
            
            player = Player(
                person_id=str(player_data.get('personId', '')),
                name=f"{player_data.get('firstName', '')} {player_data.get('familyName', '')}".strip(),
                position=player_data.get('position', ''),
                team=team_name,
                stats=player_data.get('statistics', {})
            )
            
            if player.name:
                players.append(player)
    
    return players

def debug_lineup_construction():
    """Debug why lineup construction might fail"""
    players = get_demo_players()
    
    print(f"\nAnalyzing {len(players)} players...")
    
    # Check position distribution
    position_counts = {}
    for player in players:
        positions = player.get_position_eligibility()
        for pos in positions:
            position_counts[pos] = position_counts.get(pos, 0) + 1
    
    print(f"\nPosition eligibility counts:")
    for pos, count in sorted(position_counts.items()):
        print(f"  {pos}: {count} players")
    
    # Check salary distribution
    salaries = [p.estimated_salary for p in players]
    print(f"\nSalary distribution:")
    print(f"  Min: ${min(salaries):,}")
    print(f"  Max: ${max(salaries):,}")
    print(f"  Avg: ${sum(salaries)//len(salaries):,}")
    
    # Check if we can build a simple lineup
    dk_positions = ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']
    salary_cap = 50000
    
    print(f"\nTrying to build DraftKings lineup...")
    print(f"Need positions: {dk_positions}")
    
    # Try manual construction
    lineup = []
    used_players = set()
    remaining_salary = salary_cap
    
    # Sort by value
    sorted_players = sorted(players, 
                           key=lambda p: p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0,
                           reverse=True)
    
    print(f"\nTop 10 players by value:")
    for i, p in enumerate(sorted_players[:10], 1):
        value = p.projected_dk / p.estimated_salary if p.estimated_salary > 0 else 0
        print(f"  {i}. {p.name} - Value: {value:.3f} (${p.estimated_salary}, {p.projected_dk:.1f} proj)")
    
    # Try to fill each position
    for pos_needed in dk_positions:
        print(f"\nLooking for {pos_needed}...")
        found = False
        
        for player in sorted_players:
            if (player.person_id in used_players or 
                player.estimated_salary > remaining_salary):
                continue
            
            if pos_needed in player.get_position_eligibility():
                lineup.append(player)
                used_players.add(player.person_id)
                remaining_salary -= player.estimated_salary
                print(f"  Found: {player.name} (${player.estimated_salary}, {'/'.join(player.get_position_eligibility())})")
                print(f"  Remaining salary: ${remaining_salary:,}")
                found = True
                break
        
        if not found:
            print(f"  ERROR: Could not find player for {pos_needed}")
            print(f"  Available players for this position:")
            eligible_players = [p for p in sorted_players 
                              if p.person_id not in used_players 
                              and pos_needed in p.get_position_eligibility()]
            for p in eligible_players[:5]:
                print(f"    {p.name} - ${p.estimated_salary} (need ${remaining_salary:,})")
            break
    
    if len(lineup) == len(dk_positions):
        total_salary = sum(p.estimated_salary for p in lineup)
        total_score = sum(p.dk_score for p in lineup)
        print(f"\nSUCCESS! Built complete lineup:")
        print(f"  Players: {len(lineup)}")
        print(f"  Total salary: ${total_salary:,}")
        print(f"  Total actual score: {total_score:.1f}")
    else:
        print(f"\nFAILED: Only filled {len(lineup)}/{len(dk_positions)} positions")

if __name__ == "__main__":
    debug_lineup_construction()