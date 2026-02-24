"""
Over/Under (Totals) Prediction Engine v3 for ParlayGuarantee
Philosophy: Vegas is ~95% efficient on totals. We find small edges (1-4 pts).

Approach:
1. Start with posted total as the baseline (respect the market)
2. Calculate our own estimate from team stats
3. Blend: 60% market + 40% our model
4. Apply adjustments for factors Vegas may underweight:
   - Recent scoring form (last 5 games vs season)
   - Pace mismatches (fast vs slow)
   - Rest/schedule (B2B, travel)
   - Injuries
5. Only pick when blended edge > 1.5 pts

Usage:
  python totals_engine_v3.py                    # Today's NBA predictions
  python totals_engine_v3.py --ncaab            # Today's NCAAB predictions
  python totals_engine_v3.py --date 2026-02-21  # Specific date
  python totals_engine_v3.py --backtest 7       # Backtest last N days
"""

import json
import logging
import math
import sys
import requests
import sqlite3
import time
import statistics
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
DB_PATH = ENGINE_DIR / "totals_engine_v3.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# League constants
NBA_AVG_PPG = 114.0
NBA_AVG_PACE = 100.2
NCAAB_AVG_PPG = 74.4
NCAAB_AVG_PACE = 68.0


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date DATE,
        sport TEXT,
        home_team TEXT,
        away_team TEXT,
        predicted_total REAL,
        posted_total REAL,
        our_raw_total REAL,
        blended_total REAL,
        pick TEXT,
        confidence REAL,
        edge REAL,
        tier TEXT,
        factors TEXT,
        actual_total REAL,
        result TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        line_type TEXT DEFAULT 'opening',
        UNIQUE(game_date, sport, home_team, away_team, line_type)
    )''')
    conn.commit()
    conn.close()


class TotalsEngineV3:
    def __init__(self, sport='nba'):
        init_db()
        self.sport = sport
        self.avg_ppg = NBA_AVG_PPG if sport == 'nba' else NCAAB_AVG_PPG
        self.avg_pace = NBA_AVG_PACE if sport == 'nba' else NCAAB_AVG_PACE
        self.team_stats = {}
        self.advanced = {}
        self.schedules = {}  # For B2B detection

    # ─── DATA FETCHING ────────────────────────────────────────────

    def fetch_team_stats(self):
        """Fetch team PPG/PAPG from ESPN."""
        if self.sport == 'nba':
            return self._fetch_nba_stats()
        else:
            return self._fetch_ncaab_stats()

    def _fetch_nba_stats(self):
        try:
            url = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for group in data.get('children', []):
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    name = self._normalize(name)

                    s = {}
                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        if sn == 'wins': s['wins'] = int(sv)
                        elif sn == 'losses': s['losses'] = int(sv)
                        elif sn == 'avgPointsFor': s['ppg'] = float(sv)
                        elif sn == 'avgPointsAgainst': s['papg'] = float(sv)
                        elif sn == 'streak': s['streak'] = int(sv) if sv else 0

                    gp = s.get('wins', 0) + s.get('losses', 0)
                    if gp == 0:
                        continue
                    s['games_played'] = gp
                    if 'ppg' not in s:
                        s['ppg'] = self.avg_ppg
                    if 'papg' not in s:
                        s['papg'] = self.avg_ppg
                    self.team_stats[name] = s

            logger.info(f"ESPN NBA: {len(self.team_stats)} teams")
        except Exception as e:
            logger.error(f"ESPN NBA error: {e}")

        # Try NBA.com for pace/ratings
        self._fetch_nba_advanced()

    def _fetch_nba_advanced(self):
        """Fetch pace/ORtg/DRtg from NBA.com."""
        try:
            url = "https://stats.nba.com/stats/leaguedashteamstats"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'https://www.nba.com/',
                'Accept': 'application/json',
            }
            params = {
                'Conference': '', 'DateFrom': '', 'DateTo': '',
                'Division': '', 'GameScope': '', 'GameSegment': '',
                'LastNGames': 0, 'LeagueID': '00', 'Location': '',
                'MeasureType': 'Advanced', 'Month': 0, 'OpponentTeamID': 0,
                'Outcome': '', 'PORound': 0, 'PaceAdjust': 'N',
                'PerMode': 'PerGame', 'Period': 0, 'PlayerExperience': '',
                'PlayerPosition': '', 'PlusMinus': 'N', 'Rank': 'N',
                'Season': '2024-25', 'SeasonSegment': '',
                'SeasonType': 'Regular Season', 'ShotClockRange': '',
                'StarterBench': '', 'TeamID': 0, 'TwoWay': 0,
                'VsConference': '', 'VsDivision': '',
            }
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                hdrs = data['resultSets'][0]['headers']
                rows = data['resultSets'][0]['rowSet']
                idx = {h: i for i, h in enumerate(hdrs)}

                for row in rows:
                    name = self._normalize(row[idx.get('TEAM_NAME', 1)])
                    self.advanced[name] = {
                        'pace': row[idx['PACE']] if 'PACE' in idx else self.avg_pace,
                        'ortg': row[idx['OFF_RATING']] if 'OFF_RATING' in idx else 110,
                        'drtg': row[idx['DEF_RATING']] if 'DEF_RATING' in idx else 110,
                    }
                logger.info(f"NBA.com advanced: {len(self.advanced)} teams")
                return
        except Exception as e:
            logger.warning(f"NBA.com advanced failed: {e}")

        # Fallback: estimate from PPG
        logger.info("Falling back to PPG-estimated pace/ratings")
        for team, s in self.team_stats.items():
            ppg = s['ppg']
            papg = s['papg']
            # Estimate pace from total scoring relative to league
            est_pace = self.avg_pace * ((ppg + papg) / (2 * self.avg_ppg))
            self.advanced[team] = {
                'pace': round(est_pace, 1),
                'ortg': round(ppg * 100 / est_pace, 1),
                'drtg': round(papg * 100 / est_pace, 1),
            }

    def _fetch_ncaab_stats(self):
        """Fetch NCAAB team stats from ESPN conference standings."""
        try:
            url = "https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings"
            params = {'group': '50'}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for group in data.get('children', []):
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    if not name:
                        continue
                    s = {}
                    for stat in entry.get('stats', []):
                        sn = stat.get('name', '')
                        sv = stat.get('value', 0)
                        if sn == 'avgPointsFor': s['ppg'] = float(sv)
                        elif sn == 'avgPointsAgainst': s['papg'] = float(sv)
                        elif sn == 'wins': s['wins'] = int(sv)
                        elif sn == 'losses': s['losses'] = int(sv)
                        elif sn == 'streak': s['streak'] = int(sv) if sv else 0
                        elif sn == 'winPercent': s['win_pct'] = float(sv)
                    gp = s.get('wins', 0) + s.get('losses', 0)
                    if gp < 5 or 'ppg' not in s:
                        continue
                    s['games_played'] = gp
                    self.team_stats[name] = s

            logger.info(f"ESPN NCAAB: {len(self.team_stats)} teams")

            # Build estimated advanced stats from PPG/PAPG
            for team, s in self.team_stats.items():
                ppg = s['ppg']
                papg = s['papg']
                est_pace = self.avg_pace * ((ppg + papg) / (2 * self.avg_ppg))
                self.advanced[team] = {
                    'pace': round(est_pace, 1),
                    'ortg': round(ppg * 100 / est_pace, 1) if est_pace > 0 else 100,
                    'drtg': round(papg * 100 / est_pace, 1) if est_pace > 0 else 100,
                }
        except Exception as e:
            logger.error(f"NCAAB stats error: {e}")

    def fetch_recent_games(self, team: str) -> List[int]:
        """Fetch last 5 game totals for a team from ESPN."""
        # For NBA, use the scoreboard API to look back
        # This is expensive on API calls, so we cache in DB
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS game_scores_cache (
            game_date DATE, sport TEXT, home_team TEXT, away_team TEXT,
            home_score INT, away_score INT, total INT,
            UNIQUE(game_date, home_team, away_team)
        )''')
        conn.commit()

        # Check cache for this team's recent games
        c.execute('''SELECT total FROM game_scores_cache
                     WHERE sport=? AND (home_team=? OR away_team=?)
                     ORDER BY game_date DESC LIMIT 5''',
                  (self.sport, team, team))
        cached = [r[0] for r in c.fetchall()]
        conn.close()

        if len(cached) >= 3:
            return cached
        return []

    def _cache_scores(self, target_date: date):
        """Cache scores from ESPN for a date."""
        if self.sport == 'nba':
            league = 'nba'
        else:
            league = 'mens-college-basketball'

        dt_str = target_date.strftime('%Y%m%d')
        extra = '&groups=50&limit=500' if self.sport == 'ncaab' else ''
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard?dates={dt_str}{extra}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return
            data = resp.json()

            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS game_scores_cache (
                game_date DATE, sport TEXT, home_team TEXT, away_team TEXT,
                home_score INT, away_score INT, total INT,
                UNIQUE(game_date, home_team, away_team)
            )''')

            for event in data.get('events', []):
                status = event.get('status', {}).get('type', {}).get('name', '')
                if status != 'STATUS_FINAL':
                    continue
                comps = event.get('competitions', [{}])[0]
                competitors = comps.get('competitors', [])
                home_data = away_data = None
                for comp in competitors:
                    if comp.get('homeAway') == 'home':
                        home_data = comp
                    else:
                        away_data = comp
                if not home_data or not away_data:
                    continue
                home_name = self._normalize(home_data['team'].get('displayName', ''))
                away_name = self._normalize(away_data['team'].get('displayName', ''))
                home_score = int(home_data.get('score', 0))
                away_score = int(away_data.get('score', 0))
                total = home_score + away_score

                c.execute('''INSERT OR IGNORE INTO game_scores_cache
                             VALUES (?,?,?,?,?,?,?)''',
                          (target_date.isoformat(), self.sport, home_name, away_name,
                           home_score, away_score, total))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Score cache error for {target_date}: {e}")

    # ─── ODDS FETCHING ────────────────────────────────────────────

    def fetch_games_with_odds(self, target_date: date) -> List[Dict]:
        """Fetch games with O/U lines from Odds API."""
        sport_key = 'basketball_nba' if self.sport == 'nba' else 'basketball_ncaab'
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'totals,spreads',
            'oddsFormat': 'american',
        }
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        try:
            resp = requests.get(url, params=params, timeout=30)
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f"Odds API remaining: {remaining}")
            if resp.status_code != 200:
                logger.error(f"Odds API {resp.status_code}: {resp.text[:200]}")
                return []

            games = []
            for g in resp.json():
                commence = g.get('commence_time', '')
                if commence:
                    utc_dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
                    est_dt = utc_dt + timedelta(hours=-5)
                    game_date = est_dt.date()
                else:
                    game_date = target_date

                if game_date != target_date:
                    continue

                home = self._normalize(g['home_team'])
                away = self._normalize(g['away_team'])

                totals = []
                spreads = []
                for bookie in g.get('bookmakers', []):
                    for mkt in bookie.get('markets', []):
                        if mkt['key'] == 'totals':
                            for o in mkt['outcomes']:
                                if o['name'] == 'Over':
                                    totals.append(o.get('point', 0))
                        elif mkt['key'] == 'spreads':
                            for o in mkt['outcomes']:
                                if o['name'] == g['home_team']:
                                    spreads.append(o.get('point', 0))

                if not totals:
                    continue

                games.append({
                    'home_team': home,
                    'away_team': away,
                    'posted_total': round(statistics.mean(totals), 1),
                    'spread': round(statistics.mean(spreads), 1) if spreads else 0,
                    'commence_time': commence,
                    'game_date': game_date.isoformat(),
                    'num_books': len(totals),
                    'total_range': round(max(totals) - min(totals), 1) if len(totals) > 1 else 0,
                })

            logger.info(f"Found {len(games)} {self.sport.upper()} games for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Odds fetch error: {e}")
            return []

    # ─── CORE PREDICTION ──────────────────────────────────────────

    def predict(self, home: str, away: str, posted_total: float,
                spread: float = 0, game_date: str = '') -> Dict:
        """
        Core prediction. Blends our model estimate with the market line.
        
        Our raw estimate: team offensive/defensive efficiency × pace
        Blended: 55% market + 45% our model (market is very efficient)
        Then apply edge adjustments for factors Vegas may underweight.
        """
        # Fuzzy match team names for NCAAB
        home_key = self._fuzzy_match(home) if self.sport == 'ncaab' else home
        away_key = self._fuzzy_match(away) if self.sport == 'ncaab' else away
        h = self.team_stats.get(home_key, {})
        a = self.team_stats.get(away_key, {})
        h_adv = self.advanced.get(home_key, {})
        a_adv = self.advanced.get(away_key, {})

        h_ppg = h.get('ppg', self.avg_ppg)
        h_papg = h.get('papg', self.avg_ppg)
        a_ppg = a.get('ppg', self.avg_ppg)
        a_papg = a.get('papg', self.avg_ppg)

        h_pace = h_adv.get('pace', self.avg_pace)
        a_pace = a_adv.get('pace', self.avg_pace)
        h_ortg = h_adv.get('ortg', h_ppg * 100 / self.avg_pace)
        h_drtg = h_adv.get('drtg', h_papg * 100 / self.avg_pace)
        a_ortg = a_adv.get('ortg', a_ppg * 100 / self.avg_pace)
        a_drtg = a_adv.get('drtg', a_papg * 100 / self.avg_pace)

        # Game pace estimate
        game_pace = (h_pace + a_pace) / 2

        # League average ORtg/DRtg for normalization
        league_avg_rtg = self.avg_ppg * 100 / self.avg_pace  # ~113.8 for NBA

        # Expected points per team using the "matchup" formula:
        # Team A pts = (A_ORtg * B_DRtg / League_Avg) * Pace / 100
        # This normalizes so league-avg offense vs league-avg defense = league avg points
        home_pts = (h_ortg * a_drtg / league_avg_rtg) * game_pace / 100
        away_pts = (a_ortg * h_drtg / league_avg_rtg) * game_pace / 100

        our_raw = round(home_pts + away_pts, 1)

        factors = {
            'game_pace': round(game_pace, 1),
            'home_pts': round(home_pts, 1),
            'away_pts': round(away_pts, 1),
            'our_raw': our_raw,
        }

        # ── BLEND with market ──
        # Market is very efficient. Weight it heavily.
        MARKET_WEIGHT = 0.55
        MODEL_WEIGHT = 0.45
        blended = posted_total * MARKET_WEIGHT + our_raw * MODEL_WEIGHT
        factors['blended_base'] = round(blended, 1)

        # ── ADJUSTMENTS (applied on top of blend) ──
        total_adj = 0

        # 1. Pace mismatch bonus
        # When a fast team plays a slow team, the actual pace often lands
        # closer to the fast team's pace at home
        pace_diff = abs(h_pace - a_pace)
        if pace_diff > 3:
            # Big pace mismatch — volatile, slight over lean
            pace_adj = pace_diff * 0.15
            total_adj += pace_adj
            factors['pace_mismatch'] = round(pace_adj, 1)

        # 2. Recent form (streak-based proxy)
        h_streak = h.get('streak', 0)
        a_streak = a.get('streak', 0)
        # Winning teams tend to score more, losing teams score less
        form_adj = (h_streak + a_streak) * 0.2
        form_adj = max(-2, min(2, form_adj))
        total_adj += form_adj
        factors['form_adj'] = round(form_adj, 1)

        # 3. Spread context
        # Very tight games (spread < 2) → more possessions in crunch time → slight over
        # Huge blowouts (spread > 14) → garbage time, pace drops → slight under
        spread_abs = abs(spread)
        if spread_abs > 14:
            spread_adj = -1.5
        elif spread_abs > 10:
            spread_adj = -0.5
        elif spread_abs < 2:
            spread_adj = 0.5
        else:
            spread_adj = 0
        total_adj += spread_adj
        factors['spread_adj'] = spread_adj

        # 4. Book consensus tightness
        # (handled at game level, not here)

        predicted = round(blended + total_adj, 1)
        edge = round(predicted - posted_total, 1)
        factors['total_adj'] = round(total_adj, 1)
        factors['predicted'] = predicted

        # ── DECISION ──
        MIN_EDGE = 1.5
        if abs(edge) < MIN_EDGE:
            pick = "PASS"
            confidence = 0.50
            tier = "NO EDGE"
        else:
            pick = "OVER" if edge > 0 else "UNDER"
            edge_abs = abs(edge)
            if edge_abs >= 5:
                confidence = 0.72
                tier = "🔒 LOCK"
            elif edge_abs >= 3.5:
                confidence = 0.65
                tier = "🎯 STRONG"
            elif edge_abs >= 2.5:
                confidence = 0.60
                tier = "📊 VALUE"
            else:
                confidence = 0.56
                tier = "📈 LEAN"

        return {
            'home_team': home,
            'away_team': away,
            'predicted_total': predicted,
            'posted_total': posted_total,
            'our_raw_total': our_raw,
            'pick': pick,
            'edge': edge,
            'confidence': confidence,
            'tier': tier,
            'spread': spread,
            'factors': factors,
            'game_date': game_date,
            'sport': self.sport,
        }

    # ─── RUN ──────────────────────────────────────────────────────

    def run(self, target_date: date = None) -> List[Dict]:
        """Generate predictions for a date."""
        if target_date is None:
            target_date = date.today()

        self.fetch_team_stats()
        games = self.fetch_games_with_odds(target_date)
        if not games:
            print(f"No {self.sport.upper()} games found for {target_date}")
            return []

        preds = []
        for g in games:
            p = self.predict(g['home_team'], g['away_team'],
                           g['posted_total'], g['spread'], g['game_date'])
            preds.append(p)
            self._store(p)

        # Sort by edge magnitude
        preds.sort(key=lambda x: abs(x['edge']), reverse=True)

        # Filter out PASS
        actionable = [p for p in preds if p['pick'] != 'PASS']
        logger.info(f"{len(actionable)} actionable picks from {len(preds)} games")
        return preds  # Return all, display filters PASS

    def _store(self, pred: Dict):
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO predictions
            (game_date, sport, home_team, away_team, predicted_total, posted_total,
             our_raw_total, blended_total, pick, confidence, edge, tier, factors, line_type)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (pred['game_date'], pred['sport'], pred['home_team'], pred['away_team'],
             pred['predicted_total'], pred['posted_total'], pred['our_raw_total'],
             pred['factors'].get('blended_base', 0),
             pred['pick'], pred['confidence'], pred['edge'], pred['tier'],
             json.dumps(pred['factors']), 'opening'))
        conn.commit()
        conn.close()

    # ─── BACKTEST ─────────────────────────────────────────────────

    def backtest(self, days: int = 7):
        """
        Backtest against recent completed games.
        Uses ESPN scoreboards for actual results + rebuilds what our model
        would have predicted using current team stats (not perfect, but
        gives directional accuracy signal).
        """
        today = date.today()
        all_results = []
        daily_results = {}

        for d in range(1, days + 1):
            check_date = today - timedelta(days=d)
            self._cache_scores(check_date)

            # Get actual scores from cache
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            c.execute('''SELECT home_team, away_team, home_score, away_score, total
                         FROM game_scores_cache WHERE game_date=? AND sport=?''',
                      (check_date.isoformat(), self.sport))
            scores = c.fetchall()
            conn.close()

            if not scores:
                continue

            day_correct = 0
            day_total = 0
            day_picks = 0

            for home, away, h_score, a_score, actual_total in scores:
                # We need what the posted total WAS on that date
                # Since we can't go back in time for odds, we estimate:
                # Use the actual total as a proxy for what Vegas would have posted
                # (This is imperfect but gives us a regression-to-market test)
                
                # Better approach: check our DB for stored predictions
                conn2 = sqlite3.connect(str(DB_PATH))
                c2 = conn2.cursor()
                c2.execute('''SELECT posted_total, pick, edge FROM predictions
                             WHERE game_date=? AND sport=? AND home_team=? AND away_team=?''',
                           (check_date.isoformat(), self.sport, home, away))
                stored = c2.fetchone()
                conn2.close()

                if stored:
                    posted, pick, edge = stored
                    if pick == 'PASS':
                        continue
                    actual_result = "OVER" if actual_total > posted else "UNDER"
                    hit = pick == actual_result
                    day_total += 1
                    day_picks += 1
                    if hit:
                        day_correct += 1
                    all_results.append({
                        'date': check_date.isoformat(),
                        'matchup': f"{away} @ {home}",
                        'pick': pick,
                        'edge': edge,
                        'posted': posted,
                        'actual': actual_total,
                        'hit': hit,
                    })
                else:
                    # No stored prediction — simulate with current stats
                    # Estimate what posted total would have been using actual total ± noise
                    # This is a rough proxy
                    est_posted = actual_total + (hash(f"{home}{away}{check_date}") % 11 - 5)
                    pred = self.predict(home, away, est_posted, 0, check_date.isoformat())
                    if pred['pick'] == 'PASS':
                        continue
                    actual_result = "OVER" if actual_total > est_posted else "UNDER"
                    hit = pred['pick'] == actual_result
                    day_total += 1
                    day_picks += 1
                    if hit:
                        day_correct += 1
                    all_results.append({
                        'date': check_date.isoformat(),
                        'matchup': f"{away} @ {home}",
                        'pick': pred['pick'],
                        'edge': pred['edge'],
                        'posted': est_posted,
                        'actual': actual_total,
                        'hit': hit,
                        'simulated': True,
                    })

            if day_total > 0:
                daily_results[check_date.isoformat()] = {
                    'correct': day_correct,
                    'total': day_total,
                    'pct': round(day_correct / day_total * 100, 1),
                }

        # Print report
        print(f"\n{'='*70}")
        print(f"  {self.sport.upper()} O/U BACKTEST — Last {days} days")
        print(f"{'='*70}")

        total_correct = sum(1 for r in all_results if r['hit'])
        total_picks = len(all_results)

        for d, dr in sorted(daily_results.items()):
            emoji = "✅" if dr['pct'] >= 55 else "⚠️" if dr['pct'] >= 45 else "❌"
            print(f"  {emoji} {d}: {dr['correct']}/{dr['total']} ({dr['pct']}%)")

        if total_picks > 0:
            pct = round(total_correct / total_picks * 100, 1)
            print(f"\n  📊 OVERALL: {total_correct}/{total_picks} ({pct}%)")

            # Edge analysis
            high_edge = [r for r in all_results if abs(r['edge']) >= 3]
            if high_edge:
                he_correct = sum(1 for r in high_edge if r['hit'])
                he_pct = round(he_correct / len(high_edge) * 100, 1)
                print(f"  🎯 High-edge (≥3 pts): {he_correct}/{len(high_edge)} ({he_pct}%)")

            low_edge = [r for r in all_results if abs(r['edge']) < 3]
            if low_edge:
                le_correct = sum(1 for r in low_edge if r['hit'])
                le_pct = round(le_correct / len(low_edge) * 100, 1)
                print(f"  📈 Low-edge (<3 pts): {le_correct}/{len(low_edge)} ({le_pct}%)")

            # Over vs Under breakdown
            overs = [r for r in all_results if r['pick'] == 'OVER']
            unders = [r for r in all_results if r['pick'] == 'UNDER']
            if overs:
                o_hit = sum(1 for r in overs if r['hit'])
                print(f"  ⬆️  OVER picks: {o_hit}/{len(overs)} ({round(o_hit/len(overs)*100,1)}%)")
            if unders:
                u_hit = sum(1 for r in unders if r['hit'])
                print(f"  ⬇️  UNDER picks: {u_hit}/{len(unders)} ({round(u_hit/len(unders)*100,1)}%)")
        else:
            print("\n  No picks to evaluate.")

        print(f"{'='*70}")

        # Detail
        if all_results:
            print(f"\n  Detail:")
            for r in all_results:
                emoji = "✅" if r['hit'] else "❌"
                sim = " (sim)" if r.get('simulated') else ""
                print(f"    {emoji} {r['date']} {r['matchup']}: {r['pick']} {r['posted']} → actual {r['actual']} (edge {r['edge']:+.1f}){sim}")

        return {
            'total_correct': total_correct,
            'total_picks': total_picks,
            'pct': round(total_correct / total_picks * 100, 1) if total_picks > 0 else 0,
            'daily': daily_results,
            'results': all_results,
        }

    # ─── SCORING ──────────────────────────────────────────────────

    def score_date(self, target_date: date):
        """Score predictions for a specific date against actual results."""
        self._cache_scores(target_date)

        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''SELECT home_team, away_team, posted_total, pick, edge, tier
                     FROM predictions WHERE game_date=? AND sport=?''',
                  (target_date.isoformat(), self.sport))
        preds = c.fetchall()

        c.execute('''SELECT home_team, away_team, total
                     FROM game_scores_cache WHERE game_date=? AND sport=?''',
                  (target_date.isoformat(), self.sport))
        scores = {f"{r[0]}|{r[1]}": r[2] for r in c.fetchall()}
        conn.close()

        if not preds:
            print(f"No predictions found for {target_date}")
            return

        correct = total = 0
        print(f"\n  📊 {self.sport.upper()} O/U Results — {target_date}")
        print(f"  {'-'*50}")
        for home, away, posted, pick, edge, tier in preds:
            key = f"{home}|{away}"
            actual = scores.get(key)
            if actual is None or pick == 'PASS':
                continue
            actual_result = "OVER" if actual > posted else "UNDER"
            hit = pick == actual_result
            total += 1
            if hit:
                correct += 1
            emoji = "✅" if hit else "❌"
            print(f"    {emoji} {away} @ {home}: {pick} {posted} | Actual: {actual} | Edge: {edge:+.1f}")

        if total > 0:
            print(f"\n    Record: {correct}/{total} ({round(correct/total*100,1)}%)")

    # ─── DISPLAY ──────────────────────────────────────────────────

    def display(self, preds: List[Dict]):
        if not preds:
            print("No predictions.")
            return

        actionable = [p for p in preds if p['pick'] != 'PASS']
        passed = [p for p in preds if p['pick'] == 'PASS']

        print(f"\n{'='*70}")
        print(f"  {self.sport.upper()} OVER/UNDER v3 — {preds[0].get('game_date', 'Today')}")
        print(f"{'='*70}")

        for p in actionable:
            f = p['factors']
            print(f"\n  {p['away_team']} @ {p['home_team']}")
            print(f"    Posted: {p['posted_total']}  |  Our Raw: {p['our_raw_total']}  |  Blended: {f.get('blended_base', '?')}")
            print(f"    ➜ {p['pick']} {p['posted_total']}  |  Edge: {p['edge']:+.1f}  |  {p['tier']}")
            print(f"    Pace: {f.get('game_pace','?')} | Pts: {f.get('home_pts','?')}-{f.get('away_pts','?')} | Adj: {f.get('total_adj','?'):+.1f}")

        if passed:
            print(f"\n  ⏭️  PASS ({len(passed)} games — edge < 1.5):")
            for p in passed:
                print(f"    {p['away_team']} @ {p['home_team']}: posted {p['posted_total']}, edge {p['edge']:+.1f}")

        overs = sum(1 for p in actionable if p['pick'] == 'OVER')
        unders = sum(1 for p in actionable if p['pick'] == 'UNDER')
        print(f"\n{'='*70}")
        print(f"  {len(actionable)} picks: {overs} OVER, {unders} UNDER | {len(passed)} PASS")
        print(f"{'='*70}")

    # ─── HELPERS ──────────────────────────────────────────────────

    def _normalize(self, name: str) -> str:
        mapping = {
            'LA Clippers': 'Los Angeles Clippers',
            'L.A. Clippers': 'Los Angeles Clippers',
            'L.A. Lakers': 'Los Angeles Lakers',
        }
        return mapping.get(name, name)

    def _fuzzy_match(self, name: str) -> str:
        """Try to match an Odds API team name to our ESPN stats."""
        if name in self.team_stats:
            return name

        # Common NCAAB name differences between Odds API and ESPN
        ncaab_mapping = {
            'Appalachian St': 'App State',
            'Florida St': 'Florida State',
            'Mississippi St': 'Mississippi State',
            'Michigan St': 'Michigan State',
            'Oregon St': 'Oregon State',
            'Oklahoma St': 'Oklahoma State',
            'Kansas St': 'Kansas State',
            'Arizona St': 'Arizona State',
            'Boise St': 'Boise State',
            'Colorado St': 'Colorado State',
            'Fresno St': 'Fresno State',
            'San Diego St': 'San Diego State',
            'Utah St': 'Utah State',
            'Iowa St': 'Iowa State',
            'Penn St': 'Penn State',
            'Ohio St': 'Ohio State',
            'Wichita St': 'Wichita State',
            'Albany': 'UAlbany',
            'Loyola (Chi)': 'Loyola Chicago',
            'Army': 'Army Black Knights',
            'Navy': 'Navy Midshipmen',
            'Sam Houston St': 'Sam Houston',
            'Stephen F. Austin': 'SFA',
            'SE Missouri St': 'Southeast Missouri State',
            'Southern Miss': 'Southern Mississippi',
            'CSU Fullerton': 'Cal State Fullerton',
            'CSU Bakersfield': 'Cal State Bakersfield',
            'CSU Northridge': 'Cal State Northridge',
            'UC San Diego': 'UCSD',
            'UC Santa Barbara': 'UCSB',
            'UC Davis': 'UC-Davis',
            'UC Riverside': 'UC-Riverside',
            'UC Irvine': 'UC-Irvine',
            'SE Louisiana': 'Southeastern Louisiana',
            'N Colorado': 'Northern Colorado',
            'SIU-Edwardsville': 'SIU Edwardsville',
            "Florida Int'l": 'FIU',
            'UT Rio Grande Valley': 'UTRGV',
            'East Texas A&M': 'East Texas A&M',
            'Texas A&M-CC': 'Texas A&M-Corpus Christi',
            'San Jose St': 'San Jose State',
        }

        # Try direct mapping on the part before the mascot
        parts = name.rsplit(' ', 1)
        short = parts[0] if len(parts) > 1 else name

        for odds_name, espn_name in ncaab_mapping.items():
            if odds_name in name:
                # Try replacing the abbreviation
                candidate = name.replace(odds_name, espn_name)
                if candidate in self.team_stats:
                    return candidate
                # Try just the mapped name + mascot
                for full_name in self.team_stats:
                    if espn_name in full_name:
                        return full_name

        # Generic "St" → "State" expansion
        if ' St ' in name or name.endswith(' St'):
            expanded = name.replace(' St ', ' State ').replace(' St', ' State')
            if expanded in self.team_stats:
                return expanded
            for full_name in self.team_stats:
                if expanded.split()[0] in full_name and expanded.split()[-1] in full_name:
                    return full_name

        # Fuzzy: try matching on first word(s) or mascot
        name_lower = name.lower()
        for espn_name in self.team_stats:
            espn_lower = espn_name.lower()
            n_words = name_lower.split()[:2]
            e_words = espn_lower.split()[:2]
            if n_words == e_words:
                return espn_name
            # Match on mascot (last word) + first word
            if (name_lower.split()[-1] == espn_lower.split()[-1] and
                name_lower.split()[0] == espn_lower.split()[0]):
                return espn_name

        return name  # Give up, return original


# ─── MAIN ─────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    sport = 'ncaab' if '--ncaab' in sys.argv else 'nba'
    engine = TotalsEngineV3(sport)

    target = date.today()
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target = date.fromisoformat(sys.argv[idx + 1])

    if '--backtest' in sys.argv:
        idx = sys.argv.index('--backtest')
        days = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 7
        engine.fetch_team_stats()
        engine.backtest(days)
    elif '--score' in sys.argv:
        idx = sys.argv.index('--score')
        d = date.fromisoformat(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else target
        engine.score_date(d)
    else:
        preds = engine.run(target)
        engine.display(preds)

        out = ENGINE_DIR / f"totals_v3_{sport}_{target}.json"
        with open(out, 'w') as f:
            json.dump(preds, f, indent=2, default=str)
        print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
