"""
ParlayGuarantee Engine v3 - Combo Model Backtest
5 straight ML + 2x 2-leg + 2x 3-leg + 1x 4-leg parlay = 10 picks per night
Target: 80%+ deposit keep rate
"""
import sys
import json
import time
import logging
import traceback
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('backtest_v2.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}


class ComboModelBacktester:
    """
    Combo model: 5 straight ML bets + 5 parlays (2-3 legs each).
    Customer keeps deposit if ANY of the 10 picks hit.
    """

    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.team_stats = {}  # full_name -> {win_pct, ppg, opp_ppg, ...}
        self.results = []

    def fetch_team_stats(self):
        """Fetch team stats. Uses 2024-25 season."""
        logger.info("Fetching 2024-25 team stats...")
        try:
            stats = leaguedashteamstats.LeagueDashTeamStats(season='2024-25')
            df = stats.get_data_frames()[0]
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                gp = row['GP'] if row['GP'] > 0 else 1
                self.team_stats[name] = {
                    'win_pct': row['W_PCT'],
                    'ppg': row['PTS'] / gp,
                }
            logger.info(f"Loaded stats for {len(self.team_stats)} teams")
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")
            logger.info("Falling back to 2023-24 stats")
            try:
                stats = leaguedashteamstats.LeagueDashTeamStats(season='2023-24')
                df = stats.get_data_frames()[0]
                for _, row in df.iterrows():
                    tid = row['TEAM_ID']
                    name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                    gp = row['GP'] if row['GP'] > 0 else 1
                    self.team_stats[name] = {
                        'win_pct': row['W_PCT'],
                        'ppg': row['PTS'] / gp,
                    }
                logger.info(f"Loaded 2023-24 stats for {len(self.team_stats)} teams")
                time.sleep(1.5)
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")

    def get_games(self, target_date: date) -> List[Dict]:
        """Get completed games with scores for a date."""
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            time.sleep(0.7)
            sb = scoreboardv2.ScoreboardV2(game_date=date_str)
            dfs = sb.get_data_frames()
            header = dfs[0]
            line_score = dfs[1]

            if header.empty:
                return []

            games = []
            for _, game in header.iterrows():
                if game['GAME_STATUS_TEXT'] != 'Final':
                    continue

                home_id = game['HOME_TEAM_ID']
                away_id = game['VISITOR_TEAM_ID']
                home_team = TEAM_ID_MAP.get(home_id, f"Team_{home_id}")
                away_team = TEAM_ID_MAP.get(away_id, f"Team_{away_id}")

                home_score = 0
                away_score = 0
                gl = line_score[line_score['GAME_ID'] == game['GAME_ID']]
                for _, tl in gl.iterrows():
                    pts = tl['PTS']
                    if pts is None:
                        pts = 0
                    if tl['TEAM_ID'] == home_id:
                        home_score = int(pts)
                    elif tl['TEAM_ID'] == away_id:
                        away_score = int(pts)

                if home_score > 0 and away_score > 0:
                    games.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_score': home_score,
                        'away_score': away_score,
                        'total': home_score + away_score,
                        'margin': home_score - away_score,
                    })

            return games
        except Exception as e:
            logger.error(f"Error fetching games for {target_date}: {e}")
            return []

    def predict_winner(self, home_team: str, away_team: str) -> Tuple[str, float]:
        """
        Predict ML winner. Returns (team_name, win_probability).
        Uses win% differential + home court advantage (~58% base).
        """
        home_wp = self.team_stats.get(home_team, {}).get('win_pct', 0.5)
        away_wp = self.team_stats.get(away_team, {}).get('win_pct', 0.5)

        # Log5 method for head-to-head probability
        # P(home wins) = (home_wp - home_wp*away_wp) / (home_wp + away_wp - 2*home_wp*away_wp)
        # Then boost by home court advantage
        denom = home_wp + away_wp - 2 * home_wp * away_wp
        if denom <= 0:
            home_prob = 0.58  # default home advantage
        else:
            home_prob = (home_wp - home_wp * away_wp) / denom
            # Apply home court boost (~3-4% added to home team)
            home_prob = home_prob * 0.92 + 0.08  # shift toward home

        home_prob = max(0.25, min(0.85, home_prob))

        if home_prob >= 0.5:
            return home_team, home_prob
        else:
            return away_team, 1 - home_prob

    def generate_picks(self, games: List[Dict]) -> Tuple[List[Dict], List[List[Dict]]]:
        """
        Generate 5 straight ML bets + 5 parlays (2x 2-leg, 2x 3-leg, 1x 4-leg).
        Returns (straight_bets, parlays).
        """
        if len(games) < 2:
            return [], []

        # Predict all games
        preds = []
        for game in games:
            winner, conf = self.predict_winner(game['home_team'], game['away_team'])
            preds.append({
                'game': game,
                'pick_team': winner,
                'confidence': conf,
            })

        # Sort by confidence
        preds.sort(key=lambda x: x['confidence'], reverse=True)

        # STRAIGHT BETS: top 5 (or fewer if < 5 games)
        n_straight = min(5, len(preds))
        straight_bets = [
            {'type': 'moneyline', 'pick_team': p['pick_team'], 'game': p['game'], 'confidence': p['confidence']}
            for p in preds[:n_straight]
        ]

        # PARLAYS: 2x 2-leg + 2x 3-leg + 1x 4-leg = 5 parlays
        parlays = []
        n_games = len(preds)

        def make_parlay(indices):
            return [
                {'type': 'moneyline', 'pick_team': preds[i]['pick_team'], 'game': preds[i]['game']}
                for i in indices if i < n_games
            ]

        # 2-leg parlays (2x)
        if n_games >= 2:
            parlays.append(make_parlay([0, 1]))
            if n_games >= 4:
                parlays.append(make_parlay([2, 3]))
            else:
                parlays.append(make_parlay([0, min(2, n_games - 1)]))

        # 3-leg parlays (2x)
        if n_games >= 3:
            parlays.append(make_parlay([0, 1, 2]))
            if n_games >= 5:
                parlays.append(make_parlay([1, 2, 3]))
            elif n_games >= 4:
                parlays.append(make_parlay([0, 2, 3]))
            else:
                parlays.append(make_parlay([0, 1, 2]))
        else:
            # Fallback: add 2-leg parlays if not enough games
            while len(parlays) < 4 and n_games >= 2:
                parlays.append(make_parlay([0, 1]))

        # 4-leg parlay (1x) — the big one
        if n_games >= 4:
            parlays.append(make_parlay([0, 1, 2, 3]))
        elif n_games >= 3:
            # Fall back to 3-leg if only 3 games
            parlays.append(make_parlay([0, 1, 2]))
        elif n_games >= 2:
            parlays.append(make_parlay([0, 1]))

        # Ensure exactly 5 parlays
        while len(parlays) < 5 and n_games >= 2:
            parlays.append(make_parlay([0, 1]))

        return straight_bets, parlays[:5]

    def check_ml_bet(self, bet: Dict) -> bool:
        """Check if a ML bet hit."""
        game = bet['game']
        picked = bet['pick_team']
        if picked == game['home_team']:
            return game['home_score'] > game['away_score']
        else:
            return game['away_score'] > game['home_score']

    def check_parlay(self, parlay: List[Dict]) -> bool:
        """All legs must hit."""
        return all(self.check_ml_bet(leg) for leg in parlay)

    def backtest_date(self, target_date: date) -> Optional[Dict]:
        """Run backtest for one date."""
        games = self.get_games(target_date)
        if len(games) < 2:
            return None

        straight_bets, parlays = self.generate_picks(games)
        if not straight_bets:
            return None

        sb_hits = sum(1 for b in straight_bets if self.check_ml_bet(b))
        p_hits = sum(1 for p in parlays if self.check_parlay(p))
        total_hits = sb_hits + p_hits
        deposit_kept = total_hits >= 1

        result = {
            'date': target_date.isoformat(),
            'games': len(games),
            'straight_bets': len(straight_bets),
            'straight_hits': sb_hits,
            'parlays': len(parlays),
            'parlay_hits': p_hits,
            'total_picks': len(straight_bets) + len(parlays),
            'total_hits': total_hits,
            'deposit_kept': deposit_kept,
        }

        status = 'KEPT' if deposit_kept else 'LOST'
        logger.info(
            f"{target_date} | {len(games)}G | SB:{sb_hits}/{len(straight_bets)} "
            f"| P:{p_hits}/{len(parlays)} | {status}"
        )
        return result

    def run(self) -> Dict:
        """Run full backtest."""
        logger.info(f"Starting combo model backtest: {self.start_date} to {self.end_date}")
        self.fetch_team_stats()

        current = self.start_date
        while current <= self.end_date:
            result = self.backtest_date(current)
            if result:
                self.results.append(result)

                # Save intermediate every 10 nights
                if len(self.results) % 10 == 0:
                    self._save_intermediate()

            current += timedelta(days=1)

        return self.summarize()

    def _save_intermediate(self):
        n = len(self.results)
        kept = sum(1 for r in self.results if r['deposit_kept'])
        rate = kept / n * 100 if n > 0 else 0
        logger.info(f"  [Checkpoint] {n} nights processed, keep rate so far: {rate:.1f}%")
        with open('backtest_v2_intermediate.json', 'w', encoding='utf-8') as f:
            json.dump({'nights': n, 'keep_rate': f"{rate:.1f}%", 'results': self.results}, f, indent=2)

    def summarize(self) -> Dict:
        """Calculate and save final results."""
        if not self.results:
            return {'error': 'No results'}

        total_nights = len(self.results)
        kept = sum(1 for r in self.results if r['deposit_kept'])
        keep_rate = kept / total_nights * 100

        total_sb_hits = sum(r['straight_hits'] for r in self.results)
        total_sb = sum(r['straight_bets'] for r in self.results)
        total_p_hits = sum(r['parlay_hits'] for r in self.results)
        total_p = sum(r['parlays'] for r in self.results)

        # Nights where ALL picks missed
        zero_nights = [r for r in self.results if r['total_hits'] == 0]

        summary = {
            'model': 'Combo v3: 5 straight ML + 2x2-leg + 2x3-leg + 1x4-leg parlays',
            'test_period': f"{self.start_date} to {self.end_date}",
            'total_nights': total_nights,
            'deposit_kept_nights': kept,
            'deposit_keep_rate': f"{keep_rate:.1f}%",
            'deposit_keep_rate_num': round(keep_rate, 1),
            'straight_bet_record': f"{total_sb_hits}/{total_sb} ({total_sb_hits/total_sb*100:.1f}%)" if total_sb else "N/A",
            'straight_bet_pct': round(total_sb_hits / total_sb * 100, 1) if total_sb else 0,
            'parlay_record': f"{total_p_hits}/{total_p} ({total_p_hits/total_p*100:.1f}%)" if total_p else "N/A",
            'parlay_pct': round(total_p_hits / total_p * 100, 1) if total_p else 0,
            'zero_hit_nights': len(zero_nights),
            'zero_hit_dates': [r['date'] for r in zero_nights],
            'avg_straight_hits_per_night': round(total_sb_hits / total_nights, 2),
            'avg_parlay_hits_per_night': round(total_p_hits / total_nights, 2),
            'nightly_results': self.results,
        }

        # Save
        with open('comprehensive_backtest_results.json', 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"\n{'='*60}")
        logger.info(f"COMBO MODEL v2 FINAL RESULTS")
        logger.info(f"{'='*60}")
        logger.info(f"Deposit keep rate: {keep_rate:.1f}% ({kept}/{total_nights} nights)")
        logger.info(f"Straight bets: {total_sb_hits}/{total_sb} ({total_sb_hits/total_sb*100:.1f}%)")
        logger.info(f"Parlays: {total_p_hits}/{total_p} ({total_p_hits/total_p*100:.1f}%)")
        logger.info(f"Zero-hit nights: {len(zero_nights)}")
        if zero_nights:
            logger.info(f"Zero-hit dates: {[r['date'] for r in zero_nights]}")
        logger.info(f"{'='*60}")

        return summary


def main():
    start_date = date(2024, 10, 22)
    end_date = date(2025, 1, 15)

    print(f"Combo Model v2 Backtest: {start_date} to {end_date}")
    print("5 straight ML + 2x2-leg + 2x3-leg + 1x4-leg parlay = 10 picks/night")
    print("="*60)

    bt = ComboModelBacktester(start_date, end_date)
    results = bt.run()

    print(f"\n{'='*60}")
    print(f"DEPOSIT KEEP RATE: {results.get('deposit_keep_rate', 'N/A')}")
    print(f"Straight bets: {results.get('straight_bet_record', 'N/A')}")
    print(f"Parlays: {results.get('parlay_record', 'N/A')}")
    print(f"Zero-hit nights: {results.get('zero_hit_nights', 'N/A')}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
