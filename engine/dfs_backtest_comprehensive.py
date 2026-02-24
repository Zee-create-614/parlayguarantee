#!/usr/bin/env python3
"""
Comprehensive DFS Backtest - Oct 22 2024 to Jan 15 2025
Generates dates every 2-3 days to maximize coverage while respecting rate limits.
"""

import json
import time
import random
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from nba_api.stats.endpoints import boxscoretraditionalv2
from nba_api.stats.library.http import NBAStatsHTTP


def generate_test_dates(start_date: str, end_date: str, interval_days: int = 2) -> List[str]:
    """Generate test dates every N days within range."""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=interval_days)
    return dates


@dataclass
class Player:
    person_id: str
    name: str
    position: str
    team: str
    stats: Dict[str, Any]
    dk_score: float = 0.0
    fd_score: float = 0.0
    projected_dk: float = 0.0
    projected_fd: float = 0.0
    estimated_salary: int = 0

    def __post_init__(self):
        self.calculate_scores()
        self.generate_projections()
        self.estimate_salary()

    def calculate_scores(self):
        s = self.stats
        pts = s.get('PTS', 0) or 0
        tpm = s.get('FG3M', 0) or 0
        reb = s.get('REB', 0) or 0
        ast = s.get('AST', 0) or 0
        stl = s.get('STL', 0) or 0
        blk = s.get('BLK', 0) or 0
        to = s.get('TO', 0) or 0

        self.dk_score = pts + tpm*0.5 + reb*1.25 + ast*1.5 + stl*2 + blk*2 + to*(-0.5)
        dd_cats = [pts >= 10, reb >= 10, ast >= 10, stl >= 10, blk >= 10]
        dd_count = sum(dd_cats)
        if dd_count >= 2:
            self.dk_score += 1.5
        if dd_count >= 3:
            self.dk_score += 3.0

        self.fd_score = pts + reb*1.2 + ast*1.5 + stl*3 + blk*3 + to*(-1)

    def generate_projections(self):
        self.projected_dk = self.dk_score * random.uniform(0.7, 1.3)
        self.projected_fd = self.fd_score * random.uniform(0.7, 1.3)

    def estimate_salary(self):
        # Scale so avg 8-player lineup ~$40-45k of $50k cap
        base = int(self.projected_dk * 60 + 3500)
        self.estimated_salary = max(3500, min(8500, base))

    def get_position_eligibility(self) -> List[str]:
        pos = (self.position or '').upper().strip()
        if pos in ['G', 'G-F', 'PG', 'SG']:
            return ['PG', 'SG', 'G', 'UTIL']
        elif pos in ['F', 'F-G', 'SF', 'PF']:
            return ['SF', 'PF', 'F', 'UTIL']
        elif pos in ['C', 'C-F', 'F-C']:
            return ['C', 'PF', 'F', 'UTIL']
        # Bench players - assign based on nothing, give all
        return ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL']


class DFSBacktester:
    def __init__(self, test_dates: List[str]):
        self.test_dates = test_dates
        self.dk_config = {
            'positions': ['PG', 'SG', 'SF', 'PF', 'C', 'G', 'F', 'UTIL'],
            'salary_cap': 50000, 'num_players': 8
        }
        self.fd_config = {
            'positions': ['PG', 'PG', 'SG', 'SG', 'SF', 'SF', 'PF', 'PF', 'C'],
            'salary_cap': 60000, 'num_players': 9
        }
        self.results = {p: {
            'nights': 0, 'itm_nights': 0, 'total_lineups': 0,
            'successful_lineups': 0, 'scores': [], 'best_scores': [],
            'strategy_hits': {'value_greedy': 0, 'stars_first': 0, 'randomized': 0}
        } for p in ['draftkings', 'fanduel']}
        self.nightly_details = []

    def api_call(self, fn, max_retries=4):
        for attempt in range(max_retries):
            try:
                time.sleep(1.5 + random.uniform(0, 1))  # 1.5-2.5s between calls
                return fn()
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 10 * (attempt + 1) + random.uniform(0, 5)
                    print(f"    Retry {attempt+1} in {wait:.0f}s: {e}")
                    time.sleep(wait)
                else:
                    print(f"    Failed after {max_retries} attempts: {e}")
                    return None

    def get_games(self, date_str):
        def _fetch():
            http = NBAStatsHTTP()
            resp = http.send_api_request(
                endpoint='scoreboardv2',
                parameters={'GameDate': date_str, 'LeagueID': '00', 'DayOffset': '0'}
            )
            data = resp.get_dict()
            for rs in data.get('resultSets', []):
                if rs.get('name') == 'GameHeader':
                    headers = rs['headers']
                    rows = rs['rowSet']
                    gid_idx = headers.index('GAME_ID')
                    return [row[gid_idx] for row in rows]
            return []
        result = self.api_call(_fetch)
        return result if result else []

    def get_players(self, game_id):
        data = self.api_call(lambda: boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id).get_normalized_dict())
        if not data:
            return []
        players = []
        for pd in data.get('PlayerStats', []):
            mins = pd.get('MIN', '')
            if not mins or mins == '0:00' or mins is None:
                continue
            # Build stats dict from flat row
            stats = {k: pd.get(k, 0) for k in ['PTS','FG3M','REB','AST','STL','BLK','TO']}
            p = Player(
                person_id=str(pd.get('PLAYER_ID', '')),
                name=pd.get('PLAYER_NAME', ''),
                position=pd.get('START_POSITION', '') or '',
                team=pd.get('TEAM_ABBREVIATION', ''),
                stats=stats
            )
            if p.name and p.dk_score > 0:
                players.append(p)
        return players

    def get_all_players(self, date_str):
        games = self.get_games(date_str)
        if not games:
            return []
        all_p = []
        for i, gid in enumerate(games):
            print(f"    Game {i+1}/{len(games)}: {gid}")
            all_p.extend(self.get_players(gid))
        return all_p

    def build_lineup(self, players, positions, salary_cap, sort_key):
        available = sorted(players, key=sort_key, reverse=True)
        lineup, used, remaining = [], set(), salary_cap
        # Use actual min salary from pool, sorted ascending
        sorted_salaries = sorted(p.estimated_salary for p in players)
        # Use 10th percentile salary as reserve estimate
        min_salary = sorted_salaries[min(len(sorted_salaries)//10 + 1, len(sorted_salaries)-1)] if sorted_salaries else 4000
        for i, pos in enumerate(positions):
            slots_left = len(positions) - i - 1
            max_for_this_slot = remaining - (slots_left * min_salary)
            best = None
            for p in available:
                if p.person_id in used or p.estimated_salary > max_for_this_slot:
                    continue
                if pos in p.get_position_eligibility():
                    best = p
                    break
            if best:
                lineup.append(best)
                used.add(best.person_id)
                remaining -= best.estimated_salary
            else:
                return None
        return lineup

    def generate_lineups(self, players, platform):
        cfg = self.dk_config if platform == 'draftkings' else self.fd_config
        positions, cap = cfg['positions'], cfg['salary_cap']
        score_attr = 'projected_dk' if platform == 'draftkings' else 'projected_fd'
        lineups = []
        strategies = []

        # Strategy 1: Value greedy
        lu = self.build_lineup(players, positions, cap,
                               lambda p: getattr(p, score_attr) / p.estimated_salary if p.estimated_salary > 0 else 0)
        if lu:
            lineups.append(lu)
            strategies.append('value_greedy')

        # Strategy 2: Stars first
        sorted_p = sorted(players, key=lambda p: getattr(p, score_attr), reverse=True)
        for top in sorted_p[:10]:
            if top.estimated_salary <= cap:
                temp_pos = positions.copy()
                elig = top.get_position_eligibility()
                for pos in temp_pos:
                    if pos in elig:
                        temp_pos.remove(pos)
                        break
                rest = [p for p in players if p.person_id != top.person_id]
                partial = self.build_lineup(rest, temp_pos, cap - top.estimated_salary,
                    lambda p: getattr(p, score_attr) / p.estimated_salary if p.estimated_salary > 0 else 0)
                if partial:
                    lineups.append([top] + partial)
                    strategies.append('stars_first')
                    break

        # Strategies 3-5: Randomized
        for _ in range(3):
            rp = positions.copy()
            random.shuffle(rp)
            lu = self.build_lineup(players, rp, cap,
                lambda p: getattr(p, score_attr) / p.estimated_salary if p.estimated_salary > 0 else 0)
            if lu:
                lineups.append(lu)
                strategies.append('randomized')

        return lineups, strategies

    def score_lineup(self, lineup, platform):
        return sum(p.dk_score if platform == 'draftkings' else p.fd_score for p in lineup)

    def run_date(self, date_str):
        print(f"\n{'='*40} {date_str} {'='*40}")
        players = self.get_all_players(date_str)
        if not players:
            print("  No players found, skipping.")
            return

        night_detail = {'date': date_str, 'num_players': len(players), 'num_games': 0}

        top5 = sorted(players, key=lambda p: p.dk_score, reverse=True)[:3]
        print(f"  {len(players)} players | Top DK: {', '.join(f'{p.name} {p.dk_score:.0f}' for p in top5)}")

        for platform in ['draftkings', 'fanduel']:
            lineups, strategies = self.generate_lineups(players, platform)
            res = self.results[platform]
            if not lineups:
                continue

            res['nights'] += 1
            res['total_lineups'] += len(lineups)
            best_score = 0
            night_itm = False
            itm_threshold = 100 if platform == 'draftkings' else 120

            for i, (lu, strat) in enumerate(zip(lineups, strategies)):
                score = self.score_lineup(lu, platform)
                res['successful_lineups'] += 1
                res['scores'].append(score)
                best_score = max(best_score, score)
                if score >= itm_threshold:
                    night_itm = True
                    res['strategy_hits'][strat] = res['strategy_hits'].get(strat, 0) + 1

            if night_itm:
                res['itm_nights'] += 1
            res['best_scores'].append(best_score)
            print(f"  {platform.upper()}: best={best_score:.1f}, ITM={'✅' if night_itm else '❌'}")

        self.nightly_details.append(night_detail)

    def run(self):
        print(f"DFS Comprehensive Backtest | {len(self.test_dates)} dates")
        start = time.time()
        for i, d in enumerate(self.test_dates):
            print(f"\n[{i+1}/{len(self.test_dates)}]", end='')
            try:
                self.run_date(d)
            except Exception as e:
                print(f"  ERROR on {d}: {e}")
                traceback.print_exc()

        self.finalize()
        elapsed = time.time() - start
        print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f}min)")

    def finalize(self):
        print(f"\n{'='*60}\nFINAL RESULTS\n{'='*60}")
        output = {'meta': {'start_date': self.test_dates[0], 'end_date': self.test_dates[-1],
                           'total_dates_attempted': len(self.test_dates)}}

        for platform in ['draftkings', 'fanduel']:
            r = self.results[platform]
            if r['nights'] > 0:
                itm_rate = r['itm_nights'] / r['nights'] * 100
                avg_best = sum(r['best_scores']) / len(r['best_scores'])
                avg_all = sum(r['scores']) / len(r['scores']) if r['scores'] else 0
                max_score = max(r['best_scores']) if r['best_scores'] else 0
                min_score = min(r['best_scores']) if r['best_scores'] else 0

                output[platform] = {
                    'nights_tested': r['nights'],
                    'itm_nights': r['itm_nights'],
                    'itm_rate_pct': round(itm_rate, 1),
                    'avg_best_score': round(avg_best, 1),
                    'avg_all_scores': round(avg_all, 1),
                    'max_best_score': round(max_score, 1),
                    'min_best_score': round(min_score, 1),
                    'total_lineups': r['total_lineups'],
                    'successful_lineups': r['successful_lineups'],
                    'strategy_hits': r['strategy_hits']
                }
                print(f"\n{platform.upper()}:")
                print(f"  Nights: {r['nights']} | ITM: {r['itm_nights']} ({itm_rate:.1f}%)")
                print(f"  Avg best: {avg_best:.1f} | Avg all: {avg_all:.1f}")
                print(f"  Max: {max_score:.1f} | Min: {min_score:.1f}")
                print(f"  Strategy hits: {r['strategy_hits']}")
            else:
                output[platform] = {'nights_tested': 0, 'error': 'No successful nights'}

        with open('dfs_backtest_comprehensive_results.json', 'w') as f:
            json.dump(output, f, indent=2)
        print("\nSaved to dfs_backtest_comprehensive_results.json")


if __name__ == '__main__':
    dates = generate_test_dates('2024-10-22', '2025-01-15', interval_days=2)
    print(f"Generated {len(dates)} test dates")
    bt = DFSBacktester(dates)
    bt.run()
