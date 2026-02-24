"""
ParlayGuarantee Mix E Backtest v5
Mix E: 4x2-leg, 2x3-leg, 1x4-leg, 1x5-leg, 1x6-leg, 1x7-leg = 10 picks
Period: Oct 22, 2024 - Jan 15, 2025
Reuses v4 logic (Log5, same keep condition).
"""
import sys, json, time, logging
from datetime import timedelta, date
from typing import Dict, List, Tuple
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('backtest_v5_mixE.log', encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}
PAYOUT_MULT = {2: 2.5, 3: 5.0, 4: 10.0, 5: 20.0, 6: 40.0, 7: 80.0}

MIX_E = [(2,4), (3,2), (4,1), (5,1), (6,1), (7,1)]  # 10 picks


class MixEBacktester:
    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.team_stats = {}
        self.games_cache = {}

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
        n = len(preds)
        parlays = []
        for leg_count, num_parlays in mix_spec:
            group_usage = defaultdict(int)
            for _ in range(num_parlays):
                if n < 2:
                    continue
                actual_legs = min(leg_count, n)
                scored = [(group_usage[i], -preds[i]['confidence'], i) for i in range(n)]
                scored.sort()
                indices = [s[2] for s in scored[:actual_legs]]
                for idx in indices:
                    group_usage[idx] += 1
                legs = [preds[i] for i in indices]
                parlays.append({'target_legs': leg_count, 'actual_legs': actual_legs, 'legs': legs})
        return parlays

    def evaluate_parlays(self, parlays: List[Dict]) -> Dict:
        hits_by_legs = defaultdict(lambda: {'total': 0, 'hits': 0})
        total_hits = 0
        big_hit = False
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
        logger.info(f"Mix E Backtest: {self.start_date} to {self.end_date}")
        self.fetch_team_stats()

        dates_data = []
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

        nightly = []
        for dt, preds, n_games in dates_data:
            parlays = self.build_parlays(preds, MIX_E)
            ev = self.evaluate_parlays(parlays)
            ev['date'] = dt.isoformat()
            ev['games'] = n_games
            nightly.append(ev)

        total_nights = len(nightly)
        kept_nights = sum(1 for n in nightly if n['kept'])
        keep_rate = kept_nights / total_nights * 100 if total_nights else 0
        avg_hits = sum(n['total_hits'] for n in nightly) / total_nights if total_nights else 0
        big_hit_nights = sum(1 for n in nightly if n['big_hit'])

        max_streak = cur_streak = 0
        for n in nightly:
            if not n['kept']:
                cur_streak += 1
                max_streak = max(max_streak, cur_streak)
            else:
                cur_streak = 0

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

        zero_dates = [n['date'] for n in nightly if not n['kept']]

        # Print results
        print("\n" + "=" * 70)
        print("PARLAY MIX E BACKTEST RESULTS")
        print(f"Period: {self.start_date} to {self.end_date}")
        spec_str = " + ".join(f"{np}x{lc}-leg" for lc, np in MIX_E)
        print(f"Mix E: {spec_str} = 10 picks/night")
        print("=" * 70)
        print(f"  Total nights tested:        {total_nights}")
        print(f"  Nights kept (1+ hit):       {kept_nights}")
        print(f"  Nights refunded (0 hits):   {total_nights - kept_nights}")
        print(f"  Keep rate:                  {keep_rate:.1f}%")
        print(f"  Avg hits/night:             {avg_hits:.2f}")
        print(f"  Big hit nights (4-leg+):    {big_hit_nights}")
        print(f"  Worst zero-hit streak:      {max_streak}")
        print()
        print("  Hit Rate by Leg Count:")
        print("  " + "-" * 50)
        for legs in sorted(leg_rates.keys()):
            lr = leg_rates[legs]
            mult = PAYOUT_MULT.get(legs, '?')
            print(f"    {legs}-leg ({mult}x payout):  {lr['hits']}/{lr['total']} = {lr['rate']}%")
        print()
        print(f"  Zero-hit dates ({len(zero_dates)}):")
        for d in zero_dates:
            print(f"    {d}")
        print("=" * 70)

        # Save results
        output = {
            'mix': 'E',
            'spec': [(lc, np) for lc, np in MIX_E],
            'spec_str': spec_str,
            'total_nights': total_nights,
            'kept_nights': kept_nights,
            'keep_rate': round(keep_rate, 1),
            'avg_hits_per_night': round(avg_hits, 2),
            'big_hit_nights': big_hit_nights,
            'worst_zero_streak': max_streak,
            'leg_rates': {str(k): v for k, v in leg_rates.items()},
            'payout_multipliers': PAYOUT_MULT,
            'zero_hit_dates': zero_dates,
            '_meta': {
                'period': f"{self.start_date} to {self.end_date}",
                'method': 'Log5 with home court advantage',
                'keep_condition': '1+ parlay hit',
            }
        }
        out_path = 'backtest_v5_mixE_results.json'
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to {out_path}")


def main():
    bt = MixEBacktester(date(2024, 10, 22), date(2025, 1, 15))
    bt.run()

if __name__ == '__main__':
    main()
