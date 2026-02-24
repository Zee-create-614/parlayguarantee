"""
ParlayGuarantee Mix Optimization Backtest v4
Tests 4 different parlay mix configurations over 79-night window.
All parlays-only (no straight bets). 10 picks per night. Keep = 1+ hit.
Period: Oct 22, 2024 - Jan 15, 2025
"""
import sys, json, time, logging
from datetime import timedelta, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('backtest_v4.log', encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}

# Rough implied payout multipliers
PAYOUT_MULT = {2: 2.5, 3: 5.0, 4: 10.0, 5: 20.0, 6: 40.0, 7: 80.0}

# Mix definitions: list of (leg_count, num_parlays)
MIXES = {
    'A': [(2,4), (3,2), (4,2), (5,1), (6,1)],
    'B': [(2,3), (3,3), (4,2), (5,1), (6,1)],
    'C': [(2,3), (3,2), (4,2), (5,2), (6,1)],
    'D': [(2,5), (3,1), (4,1), (5,1), (6,1), (7,1)],
}


class MixOptimizationBacktester:
    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.team_stats = {}
        self.games_cache = {}  # date -> games list

    def fetch_team_stats(self):
        logger.info("Fetching 2024-25 team stats...")
        try:
            stats = leaguedashteamstats.LeagueDashTeamStats(season='2024-25')
            df = stats.get_data_frames()[0]
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                gp = max(row['GP'], 1)
                self.team_stats[name] = {'win_pct': row['W_PCT'], 'ppg': row['PTS'] / gp}
            logger.info(f"Loaded stats for {len(self.team_stats)} teams")
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"Error: {e}, trying 2023-24")
            stats = leaguedashteamstats.LeagueDashTeamStats(season='2023-24')
            df = stats.get_data_frames()[0]
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                gp = max(row['GP'], 1)
                self.team_stats[name] = {'win_pct': row['W_PCT'], 'ppg': row['PTS'] / gp}
            time.sleep(1.5)

    def get_games(self, target_date: date) -> List[Dict]:
        if target_date in self.games_cache:
            return self.games_cache[target_date]
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            time.sleep(0.7)
            sb = scoreboardv2.ScoreboardV2(game_date=date_str)
            dfs = sb.get_data_frames()
            header, line_score = dfs[0], dfs[1]
            if header.empty:
                self.games_cache[target_date] = []
                return []
            games = []
            for _, game in header.iterrows():
                if game['GAME_STATUS_TEXT'] != 'Final':
                    continue
                home_id, away_id = game['HOME_TEAM_ID'], game['VISITOR_TEAM_ID']
                home_team = TEAM_ID_MAP.get(home_id, f"Team_{home_id}")
                away_team = TEAM_ID_MAP.get(away_id, f"Team_{away_id}")
                home_score = away_score = 0
                gl = line_score[line_score['GAME_ID'] == game['GAME_ID']]
                for _, tl in gl.iterrows():
                    pts = int(tl['PTS']) if tl['PTS'] is not None else 0
                    if tl['TEAM_ID'] == home_id: home_score = pts
                    elif tl['TEAM_ID'] == away_id: away_score = pts
                if home_score > 0 and away_score > 0:
                    games.append({'home_team': home_team, 'away_team': away_team,
                                  'home_score': home_score, 'away_score': away_score})
            self.games_cache[target_date] = games
            return games
        except Exception as e:
            logger.error(f"Error fetching games for {target_date}: {e}")
            self.games_cache[target_date] = []
            return []

    def predict_winner(self, home_team: str, away_team: str) -> Tuple[str, float]:
        home_wp = self.team_stats.get(home_team, {}).get('win_pct', 0.5)
        away_wp = self.team_stats.get(away_team, {}).get('win_pct', 0.5)
        denom = home_wp + away_wp - 2 * home_wp * away_wp
        if denom <= 0:
            home_prob = 0.58
        else:
            home_prob = (home_wp - home_wp * away_wp) / denom
            home_prob = home_prob * 0.92 + 0.08
        home_prob = max(0.25, min(0.85, home_prob))
        if home_prob >= 0.5:
            return home_team, home_prob
        else:
            return away_team, 1 - home_prob

    def get_predictions(self, games: List[Dict]) -> List[Dict]:
        preds = []
        for g in games:
            winner, conf = self.predict_winner(g['home_team'], g['away_team'])
            actual_winner = g['home_team'] if g['home_score'] > g['away_score'] else g['away_team']
            preds.append({'game': g, 'pick_team': winner, 'confidence': conf,
                          'correct': winner == actual_winner})
        preds.sort(key=lambda x: x['confidence'], reverse=True)
        return preds

    def build_parlays(self, preds: List[Dict], mix_spec: List[Tuple[int, int]]) -> List[Dict]:
        """Build parlays for a given mix spec. Diversify game usage within each leg-count group."""
        n = len(preds)
        parlays = []

        for leg_count, num_parlays in mix_spec:
            # Track game usage within this leg-count group
            group_usage = defaultdict(int)
            for _ in range(num_parlays):
                if n < 2:
                    continue
                actual_legs = min(leg_count, n)
                # Score: prioritize least-used in this group, then highest confidence
                scored = [(group_usage[i], -preds[i]['confidence'], i) for i in range(n)]
                scored.sort()
                indices = [s[2] for s in scored[:actual_legs]]
                for idx in indices:
                    group_usage[idx] += 1
                legs = [preds[i] for i in indices]
                parlays.append({'target_legs': leg_count, 'actual_legs': actual_legs, 'legs': legs})

        return parlays

    def evaluate_parlays(self, parlays: List[Dict]) -> Dict:
        """Evaluate parlays and return nightly stats."""
        hits_by_legs = defaultdict(lambda: {'total': 0, 'hits': 0})
        total_hits = 0
        big_hit = False  # 4-leg+ hit

        for p in parlays:
            all_correct = all(leg['correct'] for leg in p['legs'])
            legs = p['target_legs']
            hits_by_legs[legs]['total'] += 1
            if all_correct:
                hits_by_legs[legs]['hits'] += 1
                total_hits += 1
                if legs >= 4:
                    big_hit = True

        return {
            'total_hits': total_hits,
            'kept': total_hits >= 1,
            'big_hit': big_hit,
            'by_legs': {k: dict(v) for k, v in hits_by_legs.items()},
        }

    def run(self):
        logger.info(f"Mix Optimization Backtest: {self.start_date} to {self.end_date}")
        self.fetch_team_stats()

        # Collect all dates and predictions first
        dates_data = []  # list of (date, preds)
        current = self.start_date
        while current <= self.end_date:
            games = self.get_games(current)
            if len(games) >= 2:
                preds = self.get_predictions(games)
                dates_data.append((current, preds, len(games)))
                if len(dates_data) % 10 == 0:
                    logger.info(f"  Fetched {len(dates_data)} nights...")
            current += timedelta(days=1)

        logger.info(f"Total nights with 2+ games: {len(dates_data)}")

        # Now evaluate each mix
        mix_results = {}
        for mix_name, mix_spec in MIXES.items():
            nightly = []
            for dt, preds, n_games in dates_data:
                parlays = self.build_parlays(preds, mix_spec)
                ev = self.evaluate_parlays(parlays)
                ev['date'] = dt.isoformat()
                ev['games'] = n_games
                nightly.append(ev)

            # Aggregate
            total_nights = len(nightly)
            kept_nights = sum(1 for n in nightly if n['kept'])
            keep_rate = kept_nights / total_nights * 100 if total_nights else 0
            avg_hits = sum(n['total_hits'] for n in nightly) / total_nights if total_nights else 0
            big_hit_nights = sum(1 for n in nightly if n['big_hit'])

            # Worst consecutive zero-hit streak
            max_streak = 0
            cur_streak = 0
            for n in nightly:
                if not n['kept']:
                    cur_streak += 1
                    max_streak = max(max_streak, cur_streak)
                else:
                    cur_streak = 0

            # Hit rate by leg count
            agg_legs = defaultdict(lambda: {'total': 0, 'hits': 0})
            for n in nightly:
                for legs_str, data in n['by_legs'].items():
                    legs = int(legs_str)
                    agg_legs[legs]['total'] += data['total']
                    agg_legs[legs]['hits'] += data['hits']

            leg_rates = {}
            for legs in sorted(agg_legs.keys()):
                d = agg_legs[legs]
                pct = d['hits'] / d['total'] * 100 if d['total'] else 0
                leg_rates[legs] = {'total': d['total'], 'hits': d['hits'], 'rate': round(pct, 1)}

            # Avg implied payout
            avg_payout_by_legs = {}
            for legs in sorted(agg_legs.keys()):
                avg_payout_by_legs[legs] = PAYOUT_MULT.get(legs, legs * 10)

            zero_dates = [n['date'] for n in nightly if not n['kept']]

            mix_results[mix_name] = {
                'spec': [(lc, np) for lc, np in mix_spec],
                'total_nights': total_nights,
                'kept_nights': kept_nights,
                'keep_rate': round(keep_rate, 1),
                'avg_hits_per_night': round(avg_hits, 2),
                'big_hit_nights': big_hit_nights,
                'worst_zero_streak': max_streak,
                'leg_rates': leg_rates,
                'payout_multipliers': avg_payout_by_legs,
                'zero_hit_dates': zero_dates,
                'nightly': nightly,
            }

            logger.info(f"Mix {mix_name}: Keep={keep_rate:.1f}%, AvgHits={avg_hits:.2f}, BigHits={big_hit_nights}, WorstStreak={max_streak}")

        self.print_comparison(mix_results)
        self.save_results(mix_results)
        return mix_results

    def print_comparison(self, mix_results: Dict):
        print("\n" + "=" * 90)
        print("PARLAY MIX OPTIMIZATION BACKTEST v4")
        print(f"Period: {self.start_date} to {self.end_date}")
        print("=" * 90)

        # Mix specs
        for name in ['A', 'B', 'C', 'D']:
            r = mix_results[name]
            spec_str = " + ".join(f"{np}x{lc}-leg" for lc, np in r['spec'])
            print(f"  Mix {name}: {spec_str}")
        print()

        # Comparison table
        header = f"  {'Metric':<35} {'Mix A':>10} {'Mix B':>10} {'Mix C':>10} {'Mix D':>10}"
        print(header)
        print("  " + "-" * 75)

        def row(label, key, fmt=None):
            vals = []
            for name in ['A', 'B', 'C', 'D']:
                v = mix_results[name][key]
                if fmt == 'pct':
                    vals.append(f"{v}%")
                elif fmt == 'f2':
                    vals.append(f"{v:.2f}" if isinstance(v, float) else str(v))
                else:
                    vals.append(str(v))
            print(f"  {label:<35} {vals[0]:>10} {vals[1]:>10} {vals[2]:>10} {vals[3]:>10}")

        row("Nights tested", "total_nights")
        row("Keep rate", "keep_rate", "pct")
        row("Nights kept", "kept_nights")
        vals = []
        for name in ['A', 'B', 'C', 'D']:
            r = mix_results[name]
            vals.append(str(r['total_nights'] - r['kept_nights']))
        print(f"  {'Nights refunded':<35} {vals[0]:>10} {vals[1]:>10} {vals[2]:>10} {vals[3]:>10}")

        row("Avg hits/night", "avg_hits_per_night", "f2")
        row("Big hit nights (4-leg+)", "big_hit_nights")
        row("Worst zero-hit streak", "worst_zero_streak")

        # Hit rates by leg count
        print(f"\n  {'Hit Rate by Leg Count':<35} {'Mix A':>10} {'Mix B':>10} {'Mix C':>10} {'Mix D':>10}")
        print("  " + "-" * 75)
        for legs in [2, 3, 4, 5, 6, 7]:
            vals = []
            for name in ['A', 'B', 'C', 'D']:
                lr = mix_results[name]['leg_rates'].get(legs)
                if lr:
                    vals.append(f"{lr['hits']}/{lr['total']} ({lr['rate']}%)")
                else:
                    vals.append("--")
            print(f"  {f'{legs}-leg parlays':<35} {vals[0]:>18} {vals[1]:>18} {vals[2]:>18} {vals[3]:>18}")

        # Payout analysis
        print(f"\n  {'Implied Payout Multipliers':<35} {'Mix A':>10} {'Mix B':>10} {'Mix C':>10} {'Mix D':>10}")
        print("  " + "-" * 75)
        for legs in [2, 3, 4, 5, 6, 7]:
            mult = PAYOUT_MULT.get(legs, 0)
            if mult == 0:
                continue
            vals = []
            for name in ['A', 'B', 'C', 'D']:
                lr = mix_results[name]['leg_rates'].get(legs)
                if lr and lr['total'] > 0:
                    vals.append(f"{mult}x")
                else:
                    vals.append("--")
            print(f"  {f'{legs}-leg (~{mult}x)':<35} {vals[0]:>10} {vals[1]:>10} {vals[2]:>10} {vals[3]:>10}")

        # Zero-hit dates
        print(f"\n  Zero-hit (refund) dates per mix:")
        for name in ['A', 'B', 'C', 'D']:
            dates = mix_results[name]['zero_hit_dates']
            print(f"    Mix {name} ({len(dates)}): {', '.join(dates[:8])}{'...' if len(dates) > 8 else ''}")

        print("\n" + "=" * 90)

    def save_results(self, mix_results: Dict):
        # Strip nightly detail for cleaner JSON
        output = {}
        for name, r in mix_results.items():
            output[name] = {k: v for k, v in r.items() if k != 'nightly'}
            output[name]['spec_str'] = " + ".join(f"{np}x{lc}-leg" for lc, np in r['spec'])
        output['_meta'] = {
            'period': f"{self.start_date} to {self.end_date}",
            'method': 'Log5 with home court advantage',
            'keep_condition': '1+ parlay hit',
            'payout_multipliers': PAYOUT_MULT,
        }
        with open('backtest_v4_results.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        print("Results saved to backtest_v4_results.json")


def main():
    bt = MixOptimizationBacktester(date(2024, 10, 22), date(2025, 1, 15))
    bt.run()

if __name__ == '__main__':
    main()
