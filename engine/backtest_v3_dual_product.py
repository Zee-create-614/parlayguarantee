"""
ParlayGuarantee Dual Product Backtest v3
Product A: 10 Straight Picks (keep if 5+ hit)
Product B: 9 Parlays - 5x2-leg, 2x3-leg, 1x4-leg, 1x6-leg (keep if 1+ hit)
Period: Oct 22, 2024 - Jan 15, 2025
"""
import sys, json, time, logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import random

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('backtest_v3.log', encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}


class DualProductBacktester:
    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.team_stats = {}
        self.straight_results = []
        self.parlay_results = []

    def fetch_team_stats(self):
        logger.info("Fetching 2024-25 team stats...")
        try:
            stats = leaguedashteamstats.LeagueDashTeamStats(season='2024-25')
            df = stats.get_data_frames()[0]
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                gp = row['GP'] if row['GP'] > 0 else 1
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
                gp = row['GP'] if row['GP'] > 0 else 1
                self.team_stats[name] = {'win_pct': row['W_PCT'], 'ppg': row['PTS'] / gp}
            time.sleep(1.5)

    def get_games(self, target_date: date) -> List[Dict]:
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            time.sleep(0.7)
            sb = scoreboardv2.ScoreboardV2(game_date=date_str)
            dfs = sb.get_data_frames()
            header, line_score = dfs[0], dfs[1]
            if header.empty:
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
            return games
        except Exception as e:
            logger.error(f"Error fetching games for {target_date}: {e}")
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

    def check_pick(self, pick_team: str, game: Dict) -> bool:
        if pick_team == game['home_team']:
            return game['home_score'] > game['away_score']
        return game['away_score'] > game['home_score']

    def get_predictions(self, games: List[Dict]) -> List[Dict]:
        preds = []
        for g in games:
            winner, conf = self.predict_winner(g['home_team'], g['away_team'])
            preds.append({'game': g, 'pick_team': winner, 'confidence': conf})
        preds.sort(key=lambda x: x['confidence'], reverse=True)
        return preds

    def backtest_straight(self, target_date: date, games: List[Dict], preds: List[Dict]) -> Optional[Dict]:
        if len(preds) < 2:
            return None
        n = min(10, len(preds))
        picks = preds[:n]
        hits = sum(1 for p in picks if self.check_pick(p['pick_team'], p['game']))
        kept = hits >= 5
        return {'date': target_date.isoformat(), 'games': len(games), 'picks': n,
                'hits': hits, 'kept': kept}

    def backtest_parlay(self, target_date: date, games: List[Dict], preds: List[Dict]) -> Optional[Dict]:
        if len(preds) < 2:
            return None

        # Build parlays: 5x2-leg, 2x3-leg, 1x4-leg, 1x6-leg = 9 parlays
        # Use highest confidence picks, diversify game usage
        n = len(preds)
        
        # Structure: list of (leg_count, count)
        parlay_specs = [(2, 5), (3, 2), (4, 1), (5, 1), (6, 1)]
        
        parlays = []
        game_usage = defaultdict(int)  # track how many times each game index used
        
        for leg_count, num_parlays in parlay_specs:
            for _ in range(num_parlays):
                if n < leg_count:
                    # Not enough games, use what we have
                    if n >= 2:
                        indices = list(range(min(n, leg_count)))
                    else:
                        continue
                else:
                    # Pick legs prioritizing least-used games, then by confidence
                    scored = [(game_usage[i], -preds[i]['confidence'], i) for i in range(n)]
                    scored.sort()
                    indices = [s[2] for s in scored[:leg_count]]
                
                for idx in indices:
                    game_usage[idx] += 1
                
                parlay = [{'pick_team': preds[i]['pick_team'], 'game': preds[i]['game']} for i in indices]
                parlays.append({'legs': leg_count, 'picks': parlay})

        # Check results
        parlay_hits = []
        for p in parlays:
            hit = all(self.check_pick(leg['pick_team'], leg['game']) for leg in p['picks'])
            parlay_hits.append({'legs': p['legs'], 'hit': hit})

        total_hits = sum(1 for h in parlay_hits if h['hit'])
        kept = total_hits >= 1

        # Hit rate by leg count
        by_legs = defaultdict(lambda: {'total': 0, 'hits': 0})
        for h in parlay_hits:
            by_legs[h['legs']]['total'] += 1
            if h['hit']:
                by_legs[h['legs']]['hits'] += 1

        return {'date': target_date.isoformat(), 'games': len(games), 'num_parlays': len(parlays),
                'total_hits': total_hits, 'kept': kept,
                'by_legs': {k: dict(v) for k, v in by_legs.items()}}

    def run(self):
        logger.info(f"Dual Product Backtest: {self.start_date} to {self.end_date}")
        self.fetch_team_stats()

        current = self.start_date
        while current <= self.end_date:
            games = self.get_games(current)
            if len(games) >= 2:
                preds = self.get_predictions(games)
                sr = self.backtest_straight(current, games, preds)
                pr = self.backtest_parlay(current, games, preds)
                if sr: self.straight_results.append(sr)
                if pr: self.parlay_results.append(pr)

                if len(self.straight_results) % 10 == 0:
                    sn = len(self.straight_results)
                    sk = sum(1 for r in self.straight_results if r['kept'])
                    pn = len(self.parlay_results)
                    pk = sum(1 for r in self.parlay_results if r['kept'])
                    logger.info(f"  [CP] {sn} nights | Straight keep: {sk}/{sn} | Parlay keep: {pk}/{pn}")

            current += timedelta(days=1)

        self.print_summary()

    def print_summary(self):
        print("\n" + "=" * 70)
        print("DUAL PRODUCT BACKTEST RESULTS")
        print(f"Period: {self.start_date} to {self.end_date}")
        print("=" * 70)

        # === STRAIGHT PICKS ===
        sr = self.straight_results
        sn = len(sr)
        sk = sum(1 for r in sr if r['kept'])
        s_rate = sk / sn * 100 if sn else 0
        all_hits = [r['hits'] for r in sr]
        avg_hits = sum(all_hits) / sn if sn else 0
        worst = min(all_hits) if all_hits else 0

        # Distribution
        dist = defaultdict(int)
        for h in all_hits:
            dist[h] += 1

        print(f"\n{'─' * 70}")
        print("PRODUCT A: STRAIGHT PICKS (10 picks/night, keep if 5+ hit)")
        print(f"{'─' * 70}")
        print(f"  Total nights:      {sn}")
        print(f"  Keep rate:         {s_rate:.1f}% ({sk}/{sn})")
        print(f"  Avg wins/night:    {avg_hits:.2f}")
        print(f"  Worst night:       {worst} wins")
        print(f"  Win distribution:")
        for k in sorted(dist.keys()):
            bar = "█" * dist[k]
            pct = dist[k] / sn * 100
            marker = " ← KEEP" if k >= 5 else " ← REFUND"
            print(f"    {k:2d} wins: {dist[k]:3d} nights ({pct:5.1f}%) {bar}{marker}")

        # Loss nights detail
        loss_dates = [r['date'] for r in sr if not r['kept']]
        if loss_dates:
            print(f"  Refund dates ({len(loss_dates)}):")
            for d in loss_dates[:10]:
                r = next(x for x in sr if x['date'] == d)
                print(f"    {d}: {r['hits']}/{r['picks']} hits ({r['games']} games)")
            if len(loss_dates) > 10:
                print(f"    ... and {len(loss_dates) - 10} more")

        # === PARLAY PICKS ===
        pr = self.parlay_results
        pn = len(pr)
        pk = sum(1 for r in pr if r['kept'])
        p_rate = pk / pn * 100 if pn else 0
        p_all_hits = [r['total_hits'] for r in pr]
        p_avg = sum(p_all_hits) / pn if pn else 0
        p_worst = min(p_all_hits) if p_all_hits else 0

        # By leg count aggregated
        agg_legs = defaultdict(lambda: {'total': 0, 'hits': 0})
        for r in pr:
            for legs_str, data in r['by_legs'].items():
                legs = int(legs_str)
                agg_legs[legs]['total'] += data['total']
                agg_legs[legs]['hits'] += data['hits']

        print(f"\n{'─' * 70}")
        print("PRODUCT B: PARLAY PICKS (5×2-leg, 2×3-leg, 1×4-leg, 1×5-leg, 1×6-leg = 10/night, keep if 1+ hit)")
        print(f"{'─' * 70}")
        print(f"  Total nights:      {pn}")
        print(f"  Keep rate:         {p_rate:.1f}% ({pk}/{pn})")
        print(f"  Avg hits/night:    {p_avg:.2f}")
        print(f"  Worst night:       {p_worst} hits")
        print(f"  Hit rate by leg count:")
        for legs in sorted(agg_legs.keys()):
            d = agg_legs[legs]
            pct = d['hits'] / d['total'] * 100 if d['total'] else 0
            print(f"    {legs}-leg: {d['hits']}/{d['total']} ({pct:.1f}%)")

        # Parlay hits distribution
        p_dist = defaultdict(int)
        for h in p_all_hits:
            p_dist[h] += 1
        print(f"  Nightly hits distribution:")
        for k in sorted(p_dist.keys()):
            bar = "█" * p_dist[k]
            pct = p_dist[k] / pn * 100
            marker = " ← REFUND" if k == 0 else ""
            print(f"    {k} parlays hit: {p_dist[k]:3d} nights ({pct:5.1f}%) {bar}{marker}")

        zero_dates = [r['date'] for r in pr if not r['kept']]
        if zero_dates:
            print(f"  Zero-hit (refund) dates ({len(zero_dates)}):")
            for d in zero_dates:
                r = next(x for x in pr if x['date'] == d)
                print(f"    {d}: 0/{r['num_parlays']} parlays ({r['games']} games)")

        # === COMPARISON ===
        print(f"\n{'=' * 70}")
        print("COMPARISON")
        print(f"{'=' * 70}")
        print(f"  {'Metric':<30} {'Straight':>15} {'Parlay':>15}")
        print(f"  {'─' * 60}")
        print(f"  {'Keep rate':<30} {f'{s_rate:.1f}%':>15} {f'{p_rate:.1f}%':>15}")
        print(f"  {'Nights tested':<30} {sn:>15} {pn:>15}")
        print(f"  {'Nights kept':<30} {sk:>15} {pk:>15}")
        print(f"  {'Nights refunded':<30} {sn-sk:>15} {pn-pk:>15}")
        print(f"  {'Avg hits/night':<30} {f'{avg_hits:.2f}':>15} {f'{p_avg:.2f}':>15}")
        print(f"  {'Worst night':<30} {f'{worst} wins':>15} {f'{p_worst} hits':>15}")
        print(f"{'=' * 70}")

        # Save JSON
        output = {
            'period': f"{self.start_date} to {self.end_date}",
            'straight': {'nights': sn, 'kept': sk, 'keep_rate': round(s_rate, 1),
                         'avg_wins': round(avg_hits, 2), 'worst': worst,
                         'distribution': dict(dist), 'results': sr},
            'parlay': {'nights': pn, 'kept': pk, 'keep_rate': round(p_rate, 1),
                       'avg_hits': round(p_avg, 2), 'worst': p_worst,
                       'by_legs': {str(k): dict(v) for k, v in agg_legs.items()},
                       'distribution': dict(p_dist), 'results': pr}
        }
        with open('backtest_v3_results.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to backtest_v3_results.json")


def main():
    bt = DualProductBacktester(date(2024, 10, 22), date(2025, 1, 15))
    bt.run()

if __name__ == '__main__':
    main()
