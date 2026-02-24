"""
DFS Fast Engine - Generates DraftKings/FanDuel NBA lineups using team-level stats
Instead of fetching 300+ individual player game logs (slow), this uses:
1. Scoreboard to get games for the target date
2. LeagueDashPlayerStats for bulk player stats (1 API call)
3. Smart salary estimation and lineup optimization
"""
import sys
import json
import time
import logging
import argparse
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from nba_api.stats.endpoints import (
    scoreboardv2, leaguedashplayerstats
)
from nba_api.stats.static import teams as nba_teams

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def safe_get_data_frames(endpoint_result):
    try:
        return endpoint_result.get_data_frames()
    except (IndexError, KeyError):
        data = endpoint_result.get_dict()
        frames = []
        for rs in data.get('resultSets', []):
            headers = rs.get('headers', [])
            rows = rs.get('rowSet', [])
            frames.append(pd.DataFrame(rows, columns=headers) if headers else pd.DataFrame())
        return frames


TEAM_ID_MAP = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}

# DraftKings scoring
def dk_score(row):
    pts = row.get('PTS', 0) or 0
    fg3m = row.get('FG3M', 0) or 0
    reb = row.get('REB', 0) or 0
    ast = row.get('AST', 0) or 0
    stl = row.get('STL', 0) or 0
    blk = row.get('BLK', 0) or 0
    tov = row.get('TOV', 0) or 0
    
    score = pts * 1.0 + fg3m * 0.5 + reb * 1.25 + ast * 1.5 + stl * 2.0 + blk * 2.0 + tov * (-0.5)
    
    # DD/TD bonus
    doubles = sum([pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10])
    if doubles >= 2:
        score += 1.5
    if doubles >= 3:
        score += 3.0
    return score

# FanDuel scoring
def fd_score(row):
    pts = row.get('PTS', 0) or 0
    reb = row.get('REB', 0) or 0
    ast = row.get('AST', 0) or 0
    stl = row.get('STL', 0) or 0
    blk = row.get('BLK', 0) or 0
    tov = row.get('TOV', 0) or 0
    return pts * 1.0 + reb * 1.2 + ast * 1.5 + stl * 3.0 + blk * 3.0 + tov * (-1.0)


@dataclass
class DFSPlayer:
    name: str
    player_id: int
    team: str
    position: str
    minutes: float
    dk_proj: float
    fd_proj: float
    dk_salary: int
    fd_salary: int
    dk_value: float  # pts per $1K
    fd_value: float


@dataclass 
class DFSLineup:
    platform: str
    strategy: str
    players: List[Dict]
    total_salary: int
    salary_cap: int
    projected_points: float


class DFSFastEngine:
    def __init__(self):
        self.player_pool: List[DFSPlayer] = []
    
    def get_games_for_date(self, target_date: date) -> List[Dict]:
        """Get scheduled games"""
        date_str = target_date.strftime('%m/%d/%Y')
        time.sleep(0.7)
        sb = scoreboardv2.ScoreboardV2(game_date=date_str)
        dfs = safe_get_data_frames(sb)
        header = dfs[0]
        if header.empty:
            return []
        
        games = []
        for _, row in header.iterrows():
            games.append({
                'home': TEAM_ID_MAP.get(row['HOME_TEAM_ID'], '???'),
                'away': TEAM_ID_MAP.get(row['VISITOR_TEAM_ID'], '???'),
                'home_id': row['HOME_TEAM_ID'],
                'away_id': row['VISITOR_TEAM_ID'],
            })
        return games
    
    def get_player_stats(self, playing_team_ids: set) -> pd.DataFrame:
        """Bulk fetch all player stats in ONE API call"""
        time.sleep(1.0)
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season='2024-25',
            per_mode_detailed='PerGame'
        )
        df = safe_get_data_frames(stats)[0]
        # Filter to players on teams playing today
        df = df[df['TEAM_ID'].isin(playing_team_ids)]
        # Filter to players with meaningful minutes
        df = df[df['MIN'] >= 15.0]
        return df
    
    def estimate_salary(self, proj: float, platform: str) -> int:
        """Estimate DFS salary from projection"""
        if platform == 'draftkings':
            if proj >= 50: return 10500
            elif proj >= 45: return 9500
            elif proj >= 40: return 8500
            elif proj >= 35: return 7500
            elif proj >= 30: return 6500
            elif proj >= 25: return 5500
            elif proj >= 20: return 4500
            else: return 3500
        else:  # fanduel
            if proj >= 50: return 11000
            elif proj >= 45: return 10000
            elif proj >= 40: return 9000
            elif proj >= 35: return 8000
            elif proj >= 30: return 7000
            elif proj >= 25: return 6000
            elif proj >= 20: return 5000
            else: return 4000

    def build_player_pool(self, target_date: date) -> List[DFSPlayer]:
        """Build player pool from teams playing on target date"""
        games = self.get_games_for_date(target_date)
        if not games:
            logger.error(f"No games found for {target_date}")
            return []
        
        logger.info(f"Found {len(games)} games for {target_date}")
        
        team_ids = set()
        for g in games:
            team_ids.add(g['home_id'])
            team_ids.add(g['away_id'])
        
        df = self.get_player_stats(team_ids)
        logger.info(f"Got stats for {len(df)} players on playing teams")
        
        pool = []
        for _, row in df.iterrows():
            # Calculate per-game DFS projections from season averages
            stats = {
                'PTS': row.get('PTS', 0),
                'FG3M': row.get('FG3M', 0),
                'REB': row.get('REB', 0),
                'AST': row.get('AST', 0),
                'STL': row.get('STL', 0),
                'BLK': row.get('BLK', 0),
                'TOV': row.get('TOV', 0),
            }
            
            dk_proj = dk_score(stats)
            fd_proj = fd_score(stats)
            
            dk_sal = self.estimate_salary(dk_proj, 'draftkings')
            fd_sal = self.estimate_salary(fd_proj, 'fanduel')
            
            # Infer position from stats (no position column in LeagueDashPlayerStats)
            ast = row.get('AST', 0) or 0
            reb = row.get('REB', 0) or 0
            blk = row.get('BLK', 0) or 0
            fg3a = row.get('FG3A', 0) or 0
            
            if ast >= 5:
                position = 'PG'
            elif fg3a >= 4 and reb < 5:
                position = 'SG'
            elif blk >= 1.0 and reb >= 6:
                position = 'C'
            elif reb >= 5.5:
                position = 'PF'
            elif fg3a >= 2.5:
                position = 'SG'
            else:
                position = 'SF'
            
            pool.append(DFSPlayer(
                name=row['PLAYER_NAME'],
                player_id=row['PLAYER_ID'],
                team=TEAM_ID_MAP.get(row['TEAM_ID'], '???'),
                position=position,
                minutes=row.get('MIN', 0),
                dk_proj=round(dk_proj, 1),
                fd_proj=round(fd_proj, 1),
                dk_salary=dk_sal,
                fd_salary=fd_sal,
                dk_value=round(dk_proj / (dk_sal / 1000), 2) if dk_sal > 0 else 0,
                fd_value=round(fd_proj / (fd_sal / 1000), 2) if fd_sal > 0 else 0,
            ))
        
        # Sort by DK projection descending
        pool.sort(key=lambda p: p.dk_proj, reverse=True)
        self.player_pool = pool
        logger.info(f"Player pool: {len(pool)} players")
        return pool
    
    def _fill_lineup(self, sorted_players: List[DFSPlayer], positions: List[str],
                     salary_cap: int, platform: str, strategy: str) -> Optional[DFSLineup]:
        """Greedy lineup filler"""
        pos_groups = {
            'PG': ['PG'], 'SG': ['SG'], 'SF': ['SF'], 'PF': ['PF'], 'C': ['C'],
            'G': ['PG', 'SG'], 'F': ['SF', 'PF'],
            'UTIL': ['PG', 'SG', 'SF', 'PF', 'C']
        }
        
        lineup = []
        used = set()
        total_sal = 0
        
        for i, pos in enumerate(positions):
            remaining = len(positions) - i
            remaining_sal = salary_cap - total_sal
            min_sal = 3500 if platform == 'draftkings' else 4000
            max_for_pos = remaining_sal - (min_sal * (remaining - 1)) if remaining > 1 else remaining_sal
            
            eligible = [
                p for p in sorted_players
                if p.player_id not in used
                and p.position in pos_groups.get(pos, [pos])
            ]
            
            selected = None
            for p in eligible:
                sal = p.dk_salary if platform == 'draftkings' else p.fd_salary
                if sal <= max_for_pos:
                    selected = p
                    break
            
            if not selected:
                return None
            
            sal = selected.dk_salary if platform == 'draftkings' else selected.fd_salary
            lineup.append(selected)
            used.add(selected.player_id)
            total_sal += sal
        
        proj = sum(p.dk_proj if platform == 'draftkings' else p.fd_proj for p in lineup)
        
        return DFSLineup(
            platform=platform,
            strategy=strategy,
            players=[{
                'name': p.name,
                'team': p.team,
                'position': p.position,
                'salary': p.dk_salary if platform == 'draftkings' else p.fd_salary,
                'projected': p.dk_proj if platform == 'draftkings' else p.fd_proj,
                'value': p.dk_value if platform == 'draftkings' else p.fd_value,
            } for p in lineup],
            total_salary=total_sal,
            salary_cap=salary_cap,
            projected_points=round(proj, 1),
        )
    
    def generate(self, target_date: date) -> Dict:
        """Generate all lineups for both platforms"""
        pool = self.build_player_pool(target_date)
        if not pool:
            return {}
        
        results = {}
        
        for platform in ['draftkings', 'fanduel']:
            config = {
                'draftkings': {'positions': ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL'], 'cap': 50000},
                'fanduel': {'positions': ['PG', 'PG', 'SG', 'SG', 'SF', 'SF', 'PF', 'PF', 'C'], 'cap': 60000},
            }[platform]
            
            lineups = []
            
            # Strategy 1: Max projection
            by_proj = sorted(pool, key=lambda p: p.dk_proj if platform == 'draftkings' else p.fd_proj, reverse=True)
            lu = self._fill_lineup(by_proj, config['positions'], config['cap'], platform, 'Max Projection')
            if lu: lineups.append(lu)
            
            # Strategy 2: Max value
            by_val = sorted(pool, key=lambda p: p.dk_value if platform == 'draftkings' else p.fd_value, reverse=True)
            lu = self._fill_lineup(by_val, config['positions'], config['cap'], platform, 'Value Play')
            if lu: lineups.append(lu)
            
            # Strategy 3: Balanced (top 50% by proj, sorted by value)
            top_half = sorted(pool, key=lambda p: p.dk_proj if platform == 'draftkings' else p.fd_proj, reverse=True)[:len(pool)//2]
            balanced = sorted(top_half, key=lambda p: p.dk_value if platform == 'draftkings' else p.fd_value, reverse=True)
            lu = self._fill_lineup(balanced, config['positions'], config['cap'], platform, 'Balanced')
            if lu: lineups.append(lu)
            
            # Strategy 4: Minutes-weighted (high minutes = more opportunity)
            by_min = sorted(pool, key=lambda p: p.minutes * (p.dk_proj if platform == 'draftkings' else p.fd_proj), reverse=True)
            lu = self._fill_lineup(by_min, config['positions'], config['cap'], platform, 'Usage Heavy')
            if lu: lineups.append(lu)
            
            # Strategy 5: Contrarian (high value, lower ownership — use lower-salary high-value)
            contrarian = sorted(pool, key=lambda p: (p.dk_value if platform == 'draftkings' else p.fd_value) * (1.0 / max(p.dk_proj if platform == 'draftkings' else p.fd_proj, 1)), reverse=True)
            lu = self._fill_lineup(contrarian, config['positions'], config['cap'], platform, 'Contrarian')
            if lu: lineups.append(lu)
            
            results[platform] = [asdict(lu) for lu in lineups]
            logger.info(f"{platform}: {len(lineups)} lineups generated")
        
        return results


def main():
    parser = argparse.ArgumentParser(description='DFS Fast Engine')
    parser.add_argument('--date', help='Target date YYYY-MM-DD', default=None)
    parser.add_argument('--output', default='dfs_output.json')
    args = parser.parse_args()
    
    target = datetime.strptime(args.date, '%Y-%m-%d').date() if args.date else date.today()
    
    engine = DFSFastEngine()
    results = engine.generate(target)
    
    if results:
        output = {
            'date': target.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'lineups': results,
        }
        
        with open(args.output, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n✅ DFS lineups saved to {args.output}")
        for platform, lineups in results.items():
            print(f"\n{platform.upper()}:")
            for lu in lineups:
                print(f"  {lu['strategy']}: {lu['projected_points']} pts | ${lu['total_salary']:,}/{lu['salary_cap']:,}")
                for p in lu['players']:
                    print(f"    {p['position']:4} {p['name']:25} ${p['salary']:,}  {p['projected']:.1f}pts  ({p['value']:.1f}x)")
    else:
        print("❌ No lineups generated")
        sys.exit(1)


if __name__ == '__main__':
    main()
