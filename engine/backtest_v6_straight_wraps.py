"""
ParlayGuarantee Backtest v6 - Straight Pick Wraps
Two multi-night straight pick products over Oct 22 2024 - Jan 15 2025:
  Weekday Pack (Mon-Fri): top 10 ML picks across the week, keep if 7+ correct
  Weekend Pack (Fri-Sun): top 10 ML picks across the weekend, keep if 7+ correct
Uses Log5 with home court advantage (same as v2).
"""
import sys, json, time, logging, math
from datetime import timedelta, date
from typing import Dict, List, Tuple
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('backtest_v6.log', encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}

START = date(2024, 10, 22)
END = date(2025, 1, 15)
WRAP_SIZE = 10
KEEP_THRESHOLD = 7


class StraightWrapsBacktester:
    def __init__(self):
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
                self.team_stats[name] = {'win_pct': row['W_PCT']}
            logger.info(f"Loaded stats for {len(self.team_stats)} teams")
            time.sleep(1.5)
        except Exception as e:
            logger.error(f"Error: {e}, trying 2023-24")
            stats = leaguedashteamstats.LeagueDashTeamStats(season='2023-24')
            df = stats.get_data_frames()[0]
            for _, row in df.iterrows():
                tid = row['TEAM_ID']
                name = TEAM_ID_MAP.get(tid, row['TEAM_NAME'])
                self.team_stats[name] = {'win_pct': row['W_PCT']}
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
                    games.append({
                        'date': target_date.isoformat(),
                        'home_team': home_team, 'away_team': away_team,
                        'home_score': home_score, 'away_score': away_score,
                    })
            self.games_cache[target_date] = games
            return games
        except Exception as e:
            logger.error(f"Error fetching {target_date}: {e}")
            self.games_cache[target_date] = []
            return []

    def predict(self, home_team: str, away_team: str) -> Tuple[str, float]:
        """Log5 with home court advantage, same as v2."""
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

    def score_and_pick(self, games: List[Dict], n: int) -> List[Dict]:
        """Pick top-n games by Log5 confidence. Returns list of pick dicts."""
        preds = []
        for g in games:
            winner, conf = self.predict(g['home_team'], g['away_team'])
            actual = g['home_team'] if g['home_score'] > g['away_score'] else g['away_team']
            preds.append({
                'date': g['date'],
                'home_team': g['home_team'],
                'away_team': g['away_team'],
                'pick': winner,
                'confidence': conf,
                'actual_winner': actual,
                'correct': winner == actual,
            })
        preds.sort(key=lambda x: x['confidence'], reverse=True)
        return preds[:n]

    def build_weekday_wraps(self) -> List[Dict]:
        """Group games into Mon-Fri weeks."""
        # Find first Monday on or after START
        d = START
        while d.weekday() != 0:  # 0=Monday
            d += timedelta(days=1)

        wraps = []
        while d + timedelta(days=4) <= END:
            week_end = d + timedelta(days=4)  # Friday
            week_games = []
            for i in range(5):
                day = d + timedelta(days=i)
                if day > END:
                    break
                week_games.extend(self.get_games(day))

            label = f"{d.isoformat()} to {week_end.isoformat()}"
            if len(week_games) == 0:
                logger.info(f"Weekday wrap {label}: no games, skipping")
                d += timedelta(days=7)
                continue

            pick_count = min(WRAP_SIZE, len(week_games))
            picks = self.score_and_pick(week_games, pick_count)
            wins = sum(1 for p in picks if p['correct'])

            # Proportional threshold if < 10 games
            if pick_count < WRAP_SIZE:
                threshold = max(1, round(KEEP_THRESHOLD * pick_count / WRAP_SIZE))
                note = f"Only {pick_count} games available, threshold adjusted to {threshold}"
            else:
                threshold = KEEP_THRESHOLD
                note = None

            kept = wins >= threshold
            wrap = {
                'label': label,
                'total_games_available': len(week_games),
                'picks': pick_count,
                'wins': wins,
                'threshold': threshold,
                'kept': kept,
                'note': note,
            }
            wraps.append(wrap)
            status = 'KEPT' if kept else 'LOST'
            logger.info(f"Weekday {label}: {wins}/{pick_count} (thresh {threshold}) -> {status}")
            d += timedelta(days=7)

        return wraps

    def build_weekend_wraps(self) -> List[Dict]:
        """Group games into Fri-Sun weekends."""
        # Find first Friday on or after START
        d = START
        while d.weekday() != 4:  # 4=Friday
            d += timedelta(days=1)

        wraps = []
        while d <= END:
            weekend_end = d + timedelta(days=2)  # Sunday
            weekend_games = []
            for i in range(3):
                day = d + timedelta(days=i)
                if day > END:
                    break
                weekend_games.extend(self.get_games(day))

            label = f"{d.isoformat()} to {min(weekend_end, END).isoformat()}"
            if len(weekend_games) == 0:
                logger.info(f"Weekend wrap {label}: no games, skipping")
                d += timedelta(days=7)
                continue

            pick_count = min(WRAP_SIZE, len(weekend_games))
            picks = self.score_and_pick(weekend_games, pick_count)
            wins = sum(1 for p in picks if p['correct'])

            if pick_count < WRAP_SIZE:
                threshold = max(1, round(KEEP_THRESHOLD * pick_count / WRAP_SIZE))
                note = f"Only {pick_count} games available, threshold adjusted to {threshold}"
            else:
                threshold = KEEP_THRESHOLD
                note = None

            kept = wins >= threshold
            wrap = {
                'label': label,
                'total_games_available': len(weekend_games),
                'picks': pick_count,
                'wins': wins,
                'threshold': threshold,
                'kept': kept,
                'note': note,
            }
            wraps.append(wrap)
            status = 'KEPT' if kept else 'LOST'
            logger.info(f"Weekend {label}: {wins}/{pick_count} (thresh {threshold}) -> {status}")
            d += timedelta(days=7)

        return wraps

    def summarize(self, wraps: List[Dict], name: str) -> Dict:
        total = len(wraps)
        if total == 0:
            return {'name': name, 'error': 'no wraps'}
        kept = sum(1 for w in wraps if w['kept'])
        keep_rate = kept / total * 100
        all_wins = [w['wins'] for w in wraps]
        avg_wins = sum(all_wins) / total
        worst = min(all_wins)
        best = max(all_wins)
        short_wraps = [w for w in wraps if w['picks'] < WRAP_SIZE]

        return {
            'name': name,
            'total_wraps': total,
            'kept': kept,
            'lost': total - kept,
            'keep_rate': round(keep_rate, 1),
            'avg_wins_per_wrap': round(avg_wins, 2),
            'worst_wrap': worst,
            'best_wrap': best,
            'short_wraps': len(short_wraps),
            'win_distribution': {str(i): sum(1 for w in wraps if w['wins'] == i) for i in range(WRAP_SIZE + 1) if any(w['wins'] == i for w in wraps)},
            'wraps': wraps,
        }

    def run(self):
        self.fetch_team_stats()

        # Fetch all dates first to populate cache
        logger.info("Pre-fetching all game dates...")
        d = START
        count = 0
        while d <= END:
            self.get_games(d)
            count += 1
            if count % 10 == 0:
                logger.info(f"  Fetched {count} dates...")
            d += timedelta(days=1)
        logger.info(f"Fetched {count} dates total")

        logger.info("\n=== Building Weekday Wraps ===")
        weekday_wraps = self.build_weekday_wraps()
        weekday_summary = self.summarize(weekday_wraps, "Weekday Pack (Mon-Fri)")

        logger.info("\n=== Building Weekend Wraps ===")
        weekend_wraps = self.build_weekend_wraps()
        weekend_summary = self.summarize(weekend_wraps, "Weekend Pack (Fri-Sun)")

        # Print results
        print("\n" + "=" * 70)
        print("STRAIGHT PICK WRAPS BACKTEST v6")
        print(f"Period: {START} to {END}")
        print(f"Method: Log5 + home court advantage | Pick top {WRAP_SIZE} by confidence")
        print(f"Keep condition: {KEEP_THRESHOLD}+ correct out of {WRAP_SIZE}")
        print("=" * 70)

        for s in [weekday_summary, weekend_summary]:
            print(f"\n  {s['name']}")
            print(f"  {'-'*40}")
            print(f"  Total wraps:        {s['total_wraps']}")
            print(f"  Keep rate:          {s['keep_rate']}% ({s['kept']}/{s['total_wraps']})")
            print(f"  Avg wins/wrap:      {s['avg_wins_per_wrap']}")
            print(f"  Best wrap:          {s['best_wrap']}/{WRAP_SIZE}")
            print(f"  Worst wrap:         {s['worst_wrap']}/{WRAP_SIZE}")
            if s['short_wraps'] > 0:
                print(f"  Short wraps (<10):  {s['short_wraps']}")
            print(f"  Win distribution:")
            for wins, count in sorted(s['win_distribution'].items(), key=lambda x: int(x[0])):
                bar = "█" * count
                print(f"    {wins:>2} wins: {count:>2} {bar}")

        print("\n" + "=" * 70)

        # Save results
        output = {
            '_meta': {
                'period': f"{START} to {END}",
                'method': 'Log5 with home court advantage',
                'wrap_size': WRAP_SIZE,
                'keep_threshold': KEEP_THRESHOLD,
            },
            'weekday_pack': {k: v for k, v in weekday_summary.items() if k != 'wraps'},
            'weekday_wraps': weekday_wraps,
            'weekend_pack': {k: v for k, v in weekend_summary.items() if k != 'wraps'},
            'weekend_wraps': weekend_wraps,
        }
        with open('backtest_v6_results.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        print("Results saved to backtest_v6_results.json")


if __name__ == '__main__':
    StraightWrapsBacktester().run()
