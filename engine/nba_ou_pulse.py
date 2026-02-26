#!/usr/bin/env python3
"""
ParlayGuarantee NBA Over/Under Engine — "PULSE"
=================================================
Self-learning O/U engine with 12 weighted factors.
Each factor produces a signed edge score (+ = over, - = under).
Weighted sum → final prediction. AdaptiveLearner("pulse") tunes weights daily.

Usage:
  python nba_ou_pulse.py                    # Today's picks
  python nba_ou_pulse.py --date 2026-02-25  # Specific date
  python nba_ou_pulse.py --backtest 7       # Backtest last N days
  python nba_ou_pulse.py --score 2026-02-24 # Score a past date
"""

import json, logging, math, os, sys, sqlite3, statistics, time, requests
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = Path(__file__).parent
DB_PATH = ENGINE_DIR / "pulse_engine.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(ENGINE_DIR / 'nba_ou_pulse.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

ENGINE_NAME = "Pulse"
ENGINE_VERSION = "1.0"
SPORT = "nba"
SPORT_KEY = "basketball_nba"

# ─── League Constants ────────────────────────────────────────────
NBA_AVG_PPG = 114.0
NBA_AVG_PACE = 100.2
NBA_AVG_RTG = NBA_AVG_PPG * 100 / NBA_AVG_PACE  # ~113.8

# ─── Factor Weights (sum=1.0) — AdaptiveLearner overrides these ──
DEFAULT_WEIGHTS = {
    'pace_mismatch':      0.12,
    'ortg_matchup':       0.14,
    'drtg_matchup':       0.14,
    'recent_form':        0.10,
    'rest_b2b':           0.08,
    'spread_context':     0.06,
    'home_away_splits':   0.06,
    'streak_momentum':    0.05,
    'referee_tendency':   0.03,
    'injury_scoring':     0.08,
    'market_deviation':   0.10,
    'pace_trend':         0.04,
}
assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001

# Edge thresholds
MIN_EDGE = 1.5
CONFIDENCE_TIERS = [
    (5.0, 0.72, "🔒 LOCK"),
    (3.5, 0.65, "🎯 STRONG"),
    (2.5, 0.60, "📊 VALUE"),
    (MIN_EDGE, 0.56, "📈 LEAN"),
]

# ─── Name Normalization ─────────────────────────────────────────
TEAM_ALIASES = {
    'LA Clippers': 'Los Angeles Clippers',
    'L.A. Clippers': 'Los Angeles Clippers',
    'L.A. Lakers': 'Los Angeles Lakers',
}

def _normalize(name: str) -> str:
    return TEAM_ALIASES.get(name, name)


# ─── DB ──────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date DATE, home_team TEXT, away_team TEXT,
        predicted_total REAL, posted_total REAL, our_raw_total REAL,
        pick TEXT, confidence REAL, edge REAL, tier TEXT,
        factor_scores TEXT, factors_detail TEXT,
        actual_total REAL, result TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(game_date, home_team, away_team)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_scores_cache (
        game_date DATE, home_team TEXT, away_team TEXT,
        home_score INT, away_score INT, total INT,
        UNIQUE(game_date, home_team, away_team)
    )''')
    conn.commit()
    conn.close()


# ─── Pulse Engine ────────────────────────────────────────────────
class PulseEngine:
    def __init__(self):
        init_db()
        self.team_stats: Dict[str, Dict] = {}
        self.advanced: Dict[str, Dict] = {}
        self.recent_games: Dict[str, List[int]] = {}  # team → last N game totals
        self.weights = dict(DEFAULT_WEIGHTS)

        # Load learned weights
        try:
            sys.path.insert(0, str(ENGINE_DIR))
            from adaptive_learner import AdaptiveLearner
            self.learner = AdaptiveLearner("pulse")
            self.weights = self.learner.get_weights(DEFAULT_WEIGHTS)
            logger.info(f"Pulse weights loaded (learned={self.learner.weights_file.exists()})")
        except Exception as e:
            logger.warning(f"Could not load adaptive learner: {e}")
            self.learner = None

    # ── Data Fetching ────────────────────────────────────────────

    def fetch_team_stats(self):
        """ESPN standings for PPG/PAPG + NBA.com advanced stats."""
        try:
            resp = requests.get("https://site.api.espn.com/apis/v2/sports/basketball/nba/standings", timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for group in data.get('children', []):
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = _normalize(team_info.get('displayName', ''))
                    s = {}
                    for stat in entry.get('stats', []):
                        sn, sv = stat.get('name', ''), stat.get('value', 0)
                        if sn == 'wins': s['wins'] = int(sv)
                        elif sn == 'losses': s['losses'] = int(sv)
                        elif sn == 'avgPointsFor': s['ppg'] = float(sv)
                        elif sn == 'avgPointsAgainst': s['papg'] = float(sv)
                        elif sn == 'streak': s['streak'] = int(sv) if sv else 0
                    gp = s.get('wins', 0) + s.get('losses', 0)
                    if gp == 0: continue
                    s['games_played'] = gp
                    s.setdefault('ppg', NBA_AVG_PPG)
                    s.setdefault('papg', NBA_AVG_PPG)
                    self.team_stats[name] = s
            logger.info(f"ESPN NBA standings: {len(self.team_stats)} teams")
        except Exception as e:
            logger.error(f"ESPN standings error: {e}")

        self._fetch_advanced()

    def _fetch_advanced(self):
        """NBA.com advanced stats (pace, ORtg, DRtg) with fallback."""
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
                    name = _normalize(row[idx.get('TEAM_NAME', 1)])
                    self.advanced[name] = {
                        'pace': row[idx['PACE']] if 'PACE' in idx else NBA_AVG_PACE,
                        'ortg': row[idx['OFF_RATING']] if 'OFF_RATING' in idx else 110,
                        'drtg': row[idx['DEF_RATING']] if 'DEF_RATING' in idx else 110,
                    }
                logger.info(f"NBA.com advanced: {len(self.advanced)} teams")
                # Also fetch last-10 advanced for pace trend
                self._fetch_recent_advanced()
                return
        except Exception as e:
            logger.warning(f"NBA.com advanced failed: {e}")

        # Fallback: estimate from PPG
        for team, s in self.team_stats.items():
            ppg, papg = s['ppg'], s['papg']
            est_pace = NBA_AVG_PACE * ((ppg + papg) / (2 * NBA_AVG_PPG))
            self.advanced[team] = {
                'pace': round(est_pace, 1),
                'ortg': round(ppg * 100 / est_pace, 1),
                'drtg': round(papg * 100 / est_pace, 1),
            }

    def _fetch_recent_advanced(self):
        """Fetch last-10-game advanced stats for pace trend detection."""
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
                'LastNGames': 10, 'LeagueID': '00', 'Location': '',
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
                    name = _normalize(row[idx.get('TEAM_NAME', 1)])
                    if name in self.advanced:
                        self.advanced[name]['pace_l10'] = row[idx['PACE']] if 'PACE' in idx else self.advanced[name]['pace']
                        self.advanced[name]['ortg_l10'] = row[idx['OFF_RATING']] if 'OFF_RATING' in idx else self.advanced[name]['ortg']
                logger.info(f"NBA.com L10 advanced loaded")
        except Exception as e:
            logger.debug(f"L10 advanced fetch failed (non-critical): {e}")

    def fetch_games_with_odds(self, target_date: date) -> List[Dict]:
        """Fetch games + O/U and spread lines from Odds API."""
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': 'totals,spreads',
            'oddsFormat': 'american',
        }
        url = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
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

                home = _normalize(g['home_team'])
                away = _normalize(g['away_team'])
                totals, spreads = [], []
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
            logger.info(f"Found {len(games)} NBA games for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Odds fetch error: {e}")
            return []

    def _get_injuries(self) -> Dict[str, List[Dict]]:
        """Try to load injuries from injury_scraper."""
        try:
            from injury_scraper import get_injuries
            raw = get_injuries()
            # Restructure: {team_name: [player_dicts]}
            injuries = {}
            if isinstance(raw, dict):
                for team, players in raw.items():
                    norm = _normalize(team)
                    injuries[norm] = players if isinstance(players, list) else []
            return injuries
        except Exception as e:
            logger.debug(f"Injury scraper not available: {e}")
            return {}

    def _get_rest_info(self, team: str, target_date: date) -> Dict:
        """Check if team is on B2B or 3-in-4 using cached scores."""
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        yesterday = (target_date - timedelta(days=1)).isoformat()
        two_ago = (target_date - timedelta(days=2)).isoformat()
        three_ago = (target_date - timedelta(days=3)).isoformat()

        # Check yesterday
        c.execute('''SELECT COUNT(*) FROM game_scores_cache
                     WHERE game_date=? AND (home_team=? OR away_team=?)''',
                  (yesterday, team, team))
        played_yesterday = c.fetchone()[0] > 0

        # Check 3-in-4
        c.execute('''SELECT COUNT(*) FROM game_scores_cache
                     WHERE game_date IN (?,?,?) AND (home_team=? OR away_team=?)''',
                  (yesterday, two_ago, three_ago, team, team))
        games_last_3 = c.fetchone()[0]
        conn.close()

        return {
            'is_b2b': played_yesterday,
            'three_in_four': games_last_3 >= 2,
            'games_last_3_days': games_last_3,
        }

    # ── Factor Scoring ───────────────────────────────────────────
    # Each factor returns a signed float: + = over lean, - = under lean
    # Magnitude reflects conviction (typically -3 to +3 range)

    def _factor_pace_mismatch(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        """Fast vs slow matchups create scoring variance."""
        h_pace = h_adv.get('pace', NBA_AVG_PACE)
        a_pace = a_adv.get('pace', NBA_AVG_PACE)
        avg = (h_pace + a_pace) / 2
        diff = avg - NBA_AVG_PACE
        # Every 1 pace above avg ≈ +1.1 total points
        score = diff * 1.1
        note = f"pace avg {avg:.1f} (h:{h_pace:.1f} a:{a_pace:.1f})"
        return round(score, 2), note

    def _factor_ortg_matchup(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        """Good offense vs bad defense → over."""
        h_ortg = h_adv.get('ortg', NBA_AVG_RTG)
        a_ortg = a_adv.get('ortg', NBA_AVG_RTG)
        a_drtg = a_adv.get('drtg', NBA_AVG_RTG)
        h_drtg = h_adv.get('drtg', NBA_AVG_RTG)
        # Home offense vs away defense
        home_matchup = (h_ortg - NBA_AVG_RTG) + (a_drtg - NBA_AVG_RTG)
        # Away offense vs home defense
        away_matchup = (a_ortg - NBA_AVG_RTG) + (h_drtg - NBA_AVG_RTG)
        # Combined: positive = offenses win, negative = defenses win
        score = (home_matchup + away_matchup) * 0.25
        return round(max(-4, min(4, score)), 2), f"ORtg matchup {score:+.1f}"

    def _factor_drtg_matchup(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        """Elite defense matchup → under lean."""
        h_drtg = h_adv.get('drtg', NBA_AVG_RTG)
        a_drtg = a_adv.get('drtg', NBA_AVG_RTG)
        # Below-avg DRtg = good defense = under lean
        combined = ((NBA_AVG_RTG - h_drtg) + (NBA_AVG_RTG - a_drtg)) * 0.3
        score = -combined  # Good defense → negative (under)
        return round(max(-4, min(4, score)), 2), f"DRtg combined {score:+.1f}"

    def _factor_recent_form(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        """Teams scoring above/below season average recently."""
        # Use streak as proxy (positive = winning = scoring more)
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        combined = (h_streak + a_streak) * 0.25
        score = max(-2.5, min(2.5, combined))
        return round(score, 2), f"streaks h:{h_streak:+d} a:{a_streak:+d}"

    def _factor_rest_b2b(self, h_rest: Dict, a_rest: Dict) -> Tuple[float, str]:
        """B2B teams score ~3-4 fewer points. 3-in-4 = worse."""
        score = 0
        notes = []
        for label, rest in [("H", h_rest), ("A", a_rest)]:
            if rest.get('is_b2b'):
                score -= 2.0  # B2B → under lean
                notes.append(f"{label}:B2B")
            if rest.get('three_in_four'):
                score -= 1.0
                notes.append(f"{label}:3in4")
        return round(score, 2), ' '.join(notes) if notes else "both rested"

    def _factor_spread_context(self, spread: float) -> Tuple[float, str]:
        """Blowout potential → under (garbage time slows), tight → over (fouling)."""
        spread_abs = abs(spread)
        if spread_abs > 14:
            return -1.5, f"blowout spread {spread:+.1f}"
        elif spread_abs > 10:
            return -0.5, f"wide spread {spread:+.1f}"
        elif spread_abs < 2:
            return 0.5, f"tight spread {spread:+.1f}"
        return 0.0, f"neutral spread {spread:+.1f}"

    def _factor_home_away_splits(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        """Home teams score ~1-2 more at home in NBA."""
        # Simple: home court adds ~1.5 pts to total via better shooting
        h_ppg = h_stats.get('ppg', NBA_AVG_PPG)
        a_ppg = a_stats.get('ppg', NBA_AVG_PPG)
        # Strong home scorers + weak road scorers → slight under
        # Both high scorers → over
        combined = ((h_ppg - NBA_AVG_PPG) + (a_ppg - NBA_AVG_PPG)) * 0.15
        return round(max(-2, min(2, combined)), 2), f"scoring context"

    def _factor_streak_momentum(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        """Winning streaks correlate with higher scoring (confidence)."""
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        # Both on win streaks → over lean; both losing → under lean
        if h_streak > 3 and a_streak > 3:
            return 1.5, "both hot streaks"
        elif h_streak < -3 and a_streak < -3:
            return -1.0, "both cold streaks"
        score = (h_streak + a_streak) * 0.15
        return round(max(-2, min(2, score)), 2), f"momentum h:{h_streak:+d} a:{a_streak:+d}"

    def _factor_referee_tendency(self) -> Tuple[float, str]:
        """Stub: high-whistle crews → more FTs → over lean."""
        # No reliable ref data source yet — return neutral
        return 0.0, "no ref data (stub)"

    def _factor_injury_scoring(self, home: str, away: str, injuries: Dict) -> Tuple[float, str]:
        """Key scorers out → under lean."""
        score = 0
        notes = []
        for team_label, team_name in [("H", home), ("A", away)]:
            team_inj = injuries.get(team_name, [])
            out_count = sum(1 for p in team_inj
                          if isinstance(p, dict) and p.get('status', '').lower() in ('out', 'doubtful'))
            if out_count >= 2:
                score -= 1.5
                notes.append(f"{team_label}:{out_count}out")
            elif out_count == 1:
                score -= 0.5
                notes.append(f"{team_label}:1out")
        return round(score, 2), ' '.join(notes) if notes else "healthy"

    def _factor_market_deviation(self, our_raw: float, posted: float) -> Tuple[float, str]:
        """When our model diverges significantly from Vegas, track it."""
        dev = our_raw - posted
        # Dampen — we trust our model partially
        score = dev * 0.3
        return round(max(-3, min(3, score)), 2), f"raw={our_raw:.1f} vs posted={posted:.1f} (dev={dev:+.1f})"

    def _factor_pace_trend(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        """Is team's pace trending up or down vs season average?"""
        score = 0
        for adv in [h_adv, a_adv]:
            season_pace = adv.get('pace', NBA_AVG_PACE)
            recent_pace = adv.get('pace_l10', season_pace)
            trend = recent_pace - season_pace
            score += trend * 0.3
        return round(max(-2, min(2, score)), 2), "pace trend L10 vs season"

    # ── Core Prediction ──────────────────────────────────────────

    def predict(self, game: Dict, injuries: Dict) -> Dict:
        home = game['home_team']
        away = game['away_team']
        posted = game['posted_total']
        spread = game.get('spread', 0)
        game_date_str = game.get('game_date', date.today().isoformat())
        game_date = date.fromisoformat(game_date_str)

        h_stats = self.team_stats.get(home, {})
        a_stats = self.team_stats.get(away, {})
        h_adv = self.advanced.get(home, {})
        a_adv = self.advanced.get(away, {})

        # Raw model total (efficiency × pace)
        h_pace = h_adv.get('pace', NBA_AVG_PACE)
        a_pace = a_adv.get('pace', NBA_AVG_PACE)
        h_ortg = h_adv.get('ortg', NBA_AVG_RTG)
        h_drtg = h_adv.get('drtg', NBA_AVG_RTG)
        a_ortg = a_adv.get('ortg', NBA_AVG_RTG)
        a_drtg = a_adv.get('drtg', NBA_AVG_RTG)
        game_pace = (h_pace + a_pace) / 2
        home_pts = (h_ortg * a_drtg / NBA_AVG_RTG) * game_pace / 100
        away_pts = (a_ortg * h_drtg / NBA_AVG_RTG) * game_pace / 100
        our_raw = round(home_pts + away_pts, 1)

        # Rest info
        h_rest = self._get_rest_info(home, game_date)
        a_rest = self._get_rest_info(away, game_date)

        # ── Compute all factor scores ──
        factor_scores = {}
        factor_details = {}

        factors = [
            ('pace_mismatch',    lambda: self._factor_pace_mismatch(h_adv, a_adv)),
            ('ortg_matchup',     lambda: self._factor_ortg_matchup(h_adv, a_adv)),
            ('drtg_matchup',     lambda: self._factor_drtg_matchup(h_adv, a_adv)),
            ('recent_form',      lambda: self._factor_recent_form(h_stats, a_stats)),
            ('rest_b2b',         lambda: self._factor_rest_b2b(h_rest, a_rest)),
            ('spread_context',   lambda: self._factor_spread_context(spread)),
            ('home_away_splits', lambda: self._factor_home_away_splits(h_stats, a_stats)),
            ('streak_momentum',  lambda: self._factor_streak_momentum(h_stats, a_stats)),
            ('referee_tendency', lambda: self._factor_referee_tendency()),
            ('injury_scoring',   lambda: self._factor_injury_scoring(home, away, injuries)),
            ('market_deviation', lambda: self._factor_market_deviation(our_raw, posted)),
            ('pace_trend',       lambda: self._factor_pace_trend(h_adv, a_adv)),
        ]

        for name, fn in factors:
            try:
                score, note = fn()
            except Exception as e:
                score, note = 0.0, f"error: {e}"
            factor_scores[name] = score
            factor_details[name] = note

        # ── Weighted sum ──
        # Weights are relative importance (sum≈1). Scale up so factors contribute
        # their full point value weighted by relative importance.
        n_factors = len(factor_scores)
        weighted_edge = sum(factor_scores[k] * self.weights.get(k, 0) for k in factor_scores) * n_factors
        predicted = round(posted + weighted_edge, 1)
        edge = round(predicted - posted, 1)

        # ── Decision ──
        if abs(edge) < MIN_EDGE:
            pick = "PASS"
            confidence = 0.50
            tier = "⏭️ PASS"
        else:
            pick = "OVER" if edge > 0 else "UNDER"
            tier_found = False
            for threshold, conf, tier_label in CONFIDENCE_TIERS:
                if abs(edge) >= threshold:
                    confidence = conf
                    tier = tier_label
                    tier_found = True
                    break
            if not tier_found:
                confidence = 0.53
                tier = "📈 LEAN"

        return {
            'home_team': home,
            'away_team': away,
            'predicted_total': predicted,
            'posted_total': posted,
            'our_raw_total': our_raw,
            'pick': pick,
            'edge': edge,
            'confidence': confidence,
            'tier': tier,
            'spread': spread,
            'factor_scores': factor_scores,
            'factor_details': factor_details,
            'weighted_edge': round(weighted_edge, 2),
            'weights_used': dict(self.weights),
            'game_date': game_date_str,
            'sport': SPORT,
            'engine': ENGINE_NAME,
            'engine_version': ENGINE_VERSION,
            'game_pace': round(game_pace, 1),
            'home_pts_est': round(home_pts, 1),
            'away_pts_est': round(away_pts, 1),
            # For learner compatibility
            'home': home,
            'away': away,
        }

    # ── Run ──────────────────────────────────────────────────────

    def run(self, target_date: date = None) -> List[Dict]:
        if target_date is None:
            target_date = date.today()

        logger.info(f"Pulse NBA O/U engine running for {target_date}")
        self.fetch_team_stats()

        # Cache recent scores for B2B detection
        for d in range(1, 5):
            self._cache_scores(target_date - timedelta(days=d))

        games = self.fetch_games_with_odds(target_date)
        if not games:
            print(f"No NBA games found for {target_date}")
            return []

        injuries = self._get_injuries()

        preds = []
        for g in games:
            p = self.predict(g, injuries)
            preds.append(p)
            self._store(p)

        preds.sort(key=lambda x: abs(x['edge']), reverse=True)

        # Save picks JSON
        picks_dir = ENGINE_DIR / f"picks_{target_date.isoformat()}"
        picks_dir.mkdir(exist_ok=True)
        picks_file = picks_dir / "nba_ou_pulse_picks.json"
        with open(picks_file, 'w') as f:
            json.dump(preds, f, indent=2, default=str)
        logger.info(f"Saved {len(preds)} picks to {picks_file}")

        actionable = [p for p in preds if p['pick'] != 'PASS']
        logger.info(f"{len(actionable)} actionable picks from {len(preds)} games")
        return preds

    def _store(self, pred: Dict):
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO predictions
            (game_date, home_team, away_team, predicted_total, posted_total,
             our_raw_total, pick, confidence, edge, tier, factor_scores, factors_detail)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (pred['game_date'], pred['home_team'], pred['away_team'],
             pred['predicted_total'], pred['posted_total'], pred['our_raw_total'],
             pred['pick'], pred['confidence'], pred['edge'], pred['tier'],
             json.dumps(pred['factor_scores']), json.dumps(pred['factor_details'])))
        conn.commit()
        conn.close()

    def _cache_scores(self, target_date: date):
        dt_str = target_date.strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt_str}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                return
            data = resp.json()
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
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
                home_name = _normalize(home_data['team'].get('displayName', ''))
                away_name = _normalize(away_data['team'].get('displayName', ''))
                home_score = int(home_data.get('score', 0))
                away_score = int(away_data.get('score', 0))
                total = home_score + away_score
                c.execute('INSERT OR IGNORE INTO game_scores_cache VALUES (?,?,?,?,?,?)',
                          (target_date.isoformat(), home_name, away_name,
                           home_score, away_score, total))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Score cache error for {target_date}: {e}")

    # ── Scoring ──────────────────────────────────────────────────

    def score_date(self, target_date: date):
        self._cache_scores(target_date)
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('SELECT home_team, away_team, posted_total, pick, edge, tier FROM predictions WHERE game_date=?',
                  (target_date.isoformat(),))
        preds = c.fetchall()
        c.execute('SELECT home_team, away_team, total FROM game_scores_cache WHERE game_date=?',
                  (target_date.isoformat(),))
        scores = {f"{r[0]}|{r[1]}": r[2] for r in c.fetchall()}
        conn.close()

        if not preds:
            print(f"No Pulse predictions for {target_date}")
            return

        correct = total = 0
        print(f"\n  💓 PULSE NBA O/U Results — {target_date}")
        print(f"  {'─'*50}")
        for home, away, posted, pick, edge, tier in preds:
            key = f"{home}|{away}"
            actual = scores.get(key)
            if actual is None or pick == 'PASS':
                continue
            actual_result = "OVER" if actual > posted else "UNDER"
            hit = pick == actual_result
            total += 1
            if hit: correct += 1
            emoji = "✅" if hit else "❌"
            print(f"    {emoji} {away} @ {home}: {pick} {posted} | Actual: {actual} | Edge: {edge:+.1f}")
        if total > 0:
            print(f"\n    Record: {correct}/{total} ({round(correct/total*100,1)}%)")

    # ── Backtest ─────────────────────────────────────────────────

    def backtest(self, days: int = 7):
        today = date.today()
        all_results = []

        for d in range(1, days + 1):
            check_date = today - timedelta(days=d)
            self._cache_scores(check_date)

            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            c.execute('SELECT home_team, away_team, posted_total, pick, edge FROM predictions WHERE game_date=?',
                      (check_date.isoformat(),))
            preds = c.fetchall()
            c.execute('SELECT home_team, away_team, total FROM game_scores_cache WHERE game_date=?',
                      (check_date.isoformat(),))
            scores = {f"{r[0]}|{r[1]}": r[2] for r in c.fetchall()}
            conn.close()

            for home, away, posted, pick, edge in preds:
                if pick == 'PASS': continue
                key = f"{home}|{away}"
                actual = scores.get(key)
                if actual is None: continue
                actual_result = "OVER" if actual > posted else "UNDER"
                all_results.append({
                    'date': check_date.isoformat(),
                    'matchup': f"{away} @ {home}",
                    'pick': pick, 'edge': edge,
                    'posted': posted, 'actual': actual,
                    'hit': pick == actual_result,
                })

        total_correct = sum(1 for r in all_results if r['hit'])
        total_picks = len(all_results)
        print(f"\n{'='*60}")
        print(f"  💓 PULSE NBA O/U BACKTEST — Last {days} days")
        print(f"{'='*60}")
        if total_picks > 0:
            pct = round(total_correct / total_picks * 100, 1)
            print(f"  📊 OVERALL: {total_correct}/{total_picks} ({pct}%)")
            for r in all_results:
                emoji = "✅" if r['hit'] else "❌"
                print(f"    {emoji} {r['date']} {r['matchup']}: {r['pick']} {r['posted']} → {r['actual']} (edge {r['edge']:+.1f})")
        else:
            print("  No picks to evaluate.")
        print(f"{'='*60}")

    # ── Display ──────────────────────────────────────────────────

    def display(self, preds: List[Dict]):
        if not preds:
            print("No predictions.")
            return

        actionable = [p for p in preds if p['pick'] != 'PASS']
        passed = [p for p in preds if p['pick'] == 'PASS']

        print(f"\n{'='*70}")
        print(f"  💓 PULSE NBA O/U v{ENGINE_VERSION} — {preds[0].get('game_date', 'Today')}")
        print(f"  12-factor self-learning model | Weights: {'learned' if self.learner and self.learner.weights_file.exists() else 'default'}")
        print(f"{'='*70}")

        for p in actionable:
            fs = p['factor_scores']
            fd = p['factor_details']
            print(f"\n  {p['away_team']} @ {p['home_team']}")
            print(f"    Posted: {p['posted_total']}  |  Raw: {p['our_raw_total']}  |  Predicted: {p['predicted_total']}")
            print(f"    ➜ {p['pick']} {p['posted_total']}  |  Edge: {p['edge']:+.1f}  |  {p['tier']}")
            print(f"    Pace: {p['game_pace']} | Est pts: {p['home_pts_est']}-{p['away_pts_est']}")
            # Top factors
            sorted_f = sorted(fs.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            for name, score in sorted_f:
                if abs(score) > 0.1:
                    arrow = "⬆️" if score > 0 else "⬇️"
                    print(f"    {arrow} {name}: {score:+.2f} ({fd.get(name, '')})")

        if passed:
            print(f"\n  ⏭️ PASS ({len(passed)} games — edge < {MIN_EDGE}):")
            for p in passed:
                print(f"    {p['away_team']} @ {p['home_team']}: posted {p['posted_total']}, edge {p['edge']:+.1f}")

        overs = sum(1 for p in actionable if p['pick'] == 'OVER')
        unders = sum(1 for p in actionable if p['pick'] == 'UNDER')
        print(f"\n{'='*70}")
        print(f"  {len(actionable)} picks: {overs} OVER, {unders} UNDER | {len(passed)} PASS")
        print(f"{'='*70}")

    def telegram_summary(self, preds: List[Dict]) -> str:
        actionable = [p for p in preds if p['pick'] != 'PASS']
        passed = [p for p in preds if p['pick'] == 'PASS']
        gd = preds[0].get('game_date', '') if preds else ''

        lines = [
            f"💓 PULSE NBA O/U — {gd}",
            f"12-factor self-learning | {len(actionable)} picks | {len(passed)} pass",
            "",
        ]

        for i, p in enumerate(actionable, 1):
            lines.append(f"{i}. {p['away_team']} @ {p['home_team']}")
            lines.append(f"   {p['tier']} {p['pick']} {p['posted_total']} (edge {p['edge']:+.1f})")
            top_f = sorted(p['factor_scores'].items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            top_str = ' | '.join(f"{k}:{v:+.1f}" for k, v in top_f if abs(v) > 0.1)
            if top_str:
                lines.append(f"   → {top_str}")
            lines.append("")

        if passed:
            lines.append(f"⏭️ {len(passed)} PASS (edge < {MIN_EDGE})")

        return '\n'.join(lines)


# ─── CLI ─────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Pulse — NBA O/U Self-Learning Engine')
    parser.add_argument('--date', type=str, help='Target date YYYY-MM-DD')
    parser.add_argument('--backtest', type=int, help='Backtest last N days')
    parser.add_argument('--score', type=str, help='Score predictions for date')
    args = parser.parse_args()

    engine = PulseEngine()

    if args.backtest:
        engine.fetch_team_stats()
        engine.backtest(args.backtest)
    elif args.score:
        engine.score_date(date.fromisoformat(args.score))
    else:
        target = date.fromisoformat(args.date) if args.date else date.today()
        preds = engine.run(target)
        engine.display(preds)
        if preds:
            tg = engine.telegram_summary(preds)
            tg_path = ENGINE_DIR / f"picks_{target.isoformat()}" / "nba_ou_pulse_telegram.txt"
            tg_path.parent.mkdir(exist_ok=True)
            with open(tg_path, 'w', encoding='utf-8') as f:
                f.write(tg)
            print(f"\nTelegram: {tg_path}")


if __name__ == '__main__':
    main()
