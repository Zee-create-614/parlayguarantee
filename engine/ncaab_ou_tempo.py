#!/usr/bin/env python3
"""
ParlayGuarantee NCAAB Over/Under Engine — "TEMPO"
===================================================
Self-learning O/U engine with 16 weighted factors (12 core + 4 NCAAB-specific).
Each factor produces a signed edge score (+ = over, - = under).
Weighted sum → final prediction. AdaptiveLearner("tempo") tunes weights daily.

Usage:
  python ncaab_ou_tempo.py                    # Today's picks
  python ncaab_ou_tempo.py --date 2026-02-25  # Specific date
  python ncaab_ou_tempo.py --backtest 7       # Backtest last N days
  python ncaab_ou_tempo.py --score 2026-02-24 # Score a past date
"""

import json, logging, math, os, sys, sqlite3, statistics, time, requests
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = Path(__file__).parent
DB_PATH = ENGINE_DIR / "tempo_engine.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(ENGINE_DIR / 'ncaab_ou_tempo.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

ENGINE_NAME = "Tempo"
ENGINE_VERSION = "1.0"
SPORT = "ncaab"
SPORT_KEY = "basketball_ncaab"

# ─── League Constants ────────────────────────────────────────────
NCAAB_AVG_PPG = 74.4
NCAAB_AVG_PACE = 68.0
NCAAB_AVG_RTG = NCAAB_AVG_PPG * 100 / NCAAB_AVG_PACE  # ~109.4

# ─── Conference pace/style profiles ─────────────────────────────
# Positive = faster than average, negative = slower
CONFERENCE_PACE_PROFILES = {
    'Big East': +2.0,
    'Big 12': +1.0,
    'SEC': +0.5,
    'ACC': +0.5,
    'Big Ten': -1.0,
    'Pac-12': +0.5,
    'American Athletic': +1.5,
    'Mountain West': -0.5,
    'West Coast': -1.0,
    'Atlantic 10': -0.5,
    'Missouri Valley': -1.5,
    'Colonial Athletic': +1.0,
    'Sun Belt': +1.5,
    'Conference USA': +0.5,
    'Mid-American': +0.5,
    'Ivy League': -2.0,
    'Patriot League': -2.0,
    'Southern': -1.0,
    'MEAC': +1.0,
    'SWAC': +1.0,
    'Horizon League': -0.5,
    'Summit League': +0.5,
    'Ohio Valley': +0.5,
}

# Known rivalries (tuple pairs) — these games go under more often
NCAAB_RIVALRIES = {
    frozenset({'Duke Blue Devils', 'North Carolina Tar Heels'}),
    frozenset({'Kentucky Wildcats', 'Louisville Cardinals'}),
    frozenset({'Kansas Jayhawks', 'Kansas State Wildcats'}),
    frozenset({'Michigan Wolverines', 'Michigan State Spartans'}),
    frozenset({'Indiana Hoosiers', 'Purdue Boilermakers'}),
    frozenset({'Georgetown Hoyas', 'Syracuse Orange'}),
    frozenset({'UCLA Bruins', 'USC Trojans'}),
    frozenset({'Gonzaga Bulldogs', 'Saint Mary\'s Gaels'}),
    frozenset({'Arizona Wildcats', 'Arizona State Sun Devils'}),
    frozenset({'North Carolina Tar Heels', 'NC State Wolfpack'}),
    frozenset({'Ohio State Buckeyes', 'Michigan Wolverines'}),
    frozenset({'Louisville Cardinals', 'Cincinnati Bearcats'}),
    frozenset({'Xavier Musketeers', 'Cincinnati Bearcats'}),
    frozenset({'Villanova Wildcats', 'Georgetown Hoyas'}),
}

# ─── Factor Weights (sum=1.0) — AdaptiveLearner overrides these ──
DEFAULT_WEIGHTS = {
    # Core factors (same concepts as Pulse)
    'pace_mismatch':      0.10,
    'ortg_matchup':       0.12,
    'drtg_matchup':       0.12,
    'recent_form':        0.07,
    'rest_b2b':           0.04,   # Less impactful in college (fewer B2Bs)
    'spread_context':     0.05,
    'home_away_splits':   0.04,
    'streak_momentum':    0.04,
    'referee_tendency':   0.02,   # Stub
    'injury_scoring':     0.04,
    'market_deviation':   0.08,
    'pace_trend':         0.03,
    # NCAAB-specific factors
    'tempo_variance':     0.06,
    'conference_style':   0.05,
    'home_court_college': 0.06,
    'three_pt_variance':  0.04,
    'rivalry_factor':     0.04,
}
assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001

MIN_EDGE = 1.5
CONFIDENCE_TIERS = [
    (5.0, 0.72, "🔒 LOCK"),
    (3.5, 0.65, "🎯 STRONG"),
    (2.5, 0.60, "📊 VALUE"),
    (MIN_EDGE, 0.56, "📈 LEAN"),
]

# ─── NCAAB Name Mapping ─────────────────────────────────────────
NCAAB_NAME_MAP = {
    'Appalachian St': 'App State', 'Florida St': 'Florida State',
    'Mississippi St': 'Mississippi State', 'Michigan St': 'Michigan State',
    'Oregon St': 'Oregon State', 'Oklahoma St': 'Oklahoma State',
    'Kansas St': 'Kansas State', 'Arizona St': 'Arizona State',
    'Boise St': 'Boise State', 'Colorado St': 'Colorado State',
    'Fresno St': 'Fresno State', 'San Diego St': 'San Diego State',
    'Utah St': 'Utah State', 'Iowa St': 'Iowa State',
    'Penn St': 'Penn State', 'Ohio St': 'Ohio State',
    'Wichita St': 'Wichita State', 'San Jose St': 'San Jose State',
}


def _normalize(name: str) -> str:
    return name


def _fuzzy_match(name: str, known: Dict) -> str:
    if name in known:
        return name
    for odds_n, espn_n in NCAAB_NAME_MAP.items():
        if odds_n in name:
            for full in known:
                if espn_n in full:
                    return full
    # "St" → "State"
    if ' St ' in name or name.endswith(' St'):
        expanded = name.replace(' St ', ' State ').replace(' St', ' State')
        if expanded in known:
            return expanded
        for full in known:
            if expanded.split()[0] in full:
                return full
    # First-two-words match
    name_lower = name.lower()
    for espn_name in known:
        espn_lower = espn_name.lower()
        nw = name_lower.split()[:2]
        ew = espn_lower.split()[:2]
        if nw == ew:
            return espn_name
    return name


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


# ─── Tempo Engine ────────────────────────────────────────────────
class TempoEngine:
    def __init__(self):
        init_db()
        self.team_stats: Dict[str, Dict] = {}
        self.advanced: Dict[str, Dict] = {}
        self.team_conferences: Dict[str, str] = {}
        self.weights = dict(DEFAULT_WEIGHTS)

        try:
            sys.path.insert(0, str(ENGINE_DIR))
            from adaptive_learner import AdaptiveLearner
            self.learner = AdaptiveLearner("tempo")
            self.weights = self.learner.get_weights(DEFAULT_WEIGHTS)
            logger.info(f"Tempo weights loaded (learned={self.learner.weights_file.exists()})")
        except Exception as e:
            logger.warning(f"Could not load adaptive learner: {e}")
            self.learner = None

    # ── Data Fetching ────────────────────────────────────────────

    def fetch_team_stats(self):
        """ESPN NCAAB standings."""
        try:
            url = "https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings"
            resp = requests.get(url, params={'group': '50'}, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for group in data.get('children', []):
                conf_name = group.get('name', group.get('abbreviation', ''))
                for entry in group.get('standings', {}).get('entries', []):
                    team_info = entry.get('team', {})
                    name = team_info.get('displayName', '')
                    if not name: continue
                    s = {}
                    for stat in entry.get('stats', []):
                        sn, sv = stat.get('name', ''), stat.get('value', 0)
                        if sn == 'avgPointsFor': s['ppg'] = float(sv)
                        elif sn == 'avgPointsAgainst': s['papg'] = float(sv)
                        elif sn == 'wins': s['wins'] = int(sv)
                        elif sn == 'losses': s['losses'] = int(sv)
                        elif sn == 'streak': s['streak'] = int(sv) if sv else 0
                    gp = s.get('wins', 0) + s.get('losses', 0)
                    if gp < 5 or 'ppg' not in s: continue
                    s['games_played'] = gp
                    self.team_stats[name] = s
                    self.team_conferences[name] = conf_name

            logger.info(f"ESPN NCAAB: {len(self.team_stats)} teams")

            # Build estimated advanced stats
            for team, s in self.team_stats.items():
                ppg, papg = s['ppg'], s['papg']
                est_pace = NCAAB_AVG_PACE * ((ppg + papg) / (2 * NCAAB_AVG_PPG))
                self.advanced[team] = {
                    'pace': round(est_pace, 1),
                    'ortg': round(ppg * 100 / est_pace, 1) if est_pace > 0 else 100,
                    'drtg': round(papg * 100 / est_pace, 1) if est_pace > 0 else 100,
                }
        except Exception as e:
            logger.error(f"NCAAB stats error: {e}")

    def fetch_games_with_odds(self, target_date: date) -> List[Dict]:
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

                home = g['home_team']
                away = g['away_team']
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
                if not totals: continue
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
            logger.info(f"Found {len(games)} NCAAB games for {target_date}")
            return games
        except Exception as e:
            logger.error(f"Odds fetch error: {e}")
            return []

    def _get_rest_info(self, team: str, target_date: date) -> Dict:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        yesterday = (target_date - timedelta(days=1)).isoformat()
        c.execute('SELECT COUNT(*) FROM game_scores_cache WHERE game_date=? AND (home_team=? OR away_team=?)',
                  (yesterday, team, team))
        played_yesterday = c.fetchone()[0] > 0
        conn.close()
        return {'is_b2b': played_yesterday}

    # ── Factor Scoring ───────────────────────────────────────────

    def _factor_pace_mismatch(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        h_pace = h_adv.get('pace', NCAAB_AVG_PACE)
        a_pace = a_adv.get('pace', NCAAB_AVG_PACE)
        avg = (h_pace + a_pace) / 2
        diff = avg - NCAAB_AVG_PACE
        score = diff * 1.0  # Each pace point ≈ 1 total point in college
        return round(max(-5, min(5, score)), 2), f"pace avg {avg:.1f} (h:{h_pace:.1f} a:{a_pace:.1f})"

    def _factor_ortg_matchup(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        h_ortg = h_adv.get('ortg', NCAAB_AVG_RTG)
        a_ortg = a_adv.get('ortg', NCAAB_AVG_RTG)
        a_drtg = a_adv.get('drtg', NCAAB_AVG_RTG)
        h_drtg = h_adv.get('drtg', NCAAB_AVG_RTG)
        home_matchup = (h_ortg - NCAAB_AVG_RTG) + (a_drtg - NCAAB_AVG_RTG)
        away_matchup = (a_ortg - NCAAB_AVG_RTG) + (h_drtg - NCAAB_AVG_RTG)
        score = (home_matchup + away_matchup) * 0.20
        return round(max(-5, min(5, score)), 2), f"ORtg matchup"

    def _factor_drtg_matchup(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        h_drtg = h_adv.get('drtg', NCAAB_AVG_RTG)
        a_drtg = a_adv.get('drtg', NCAAB_AVG_RTG)
        combined = ((NCAAB_AVG_RTG - h_drtg) + (NCAAB_AVG_RTG - a_drtg)) * 0.25
        score = -combined
        return round(max(-5, min(5, score)), 2), f"DRtg combined"

    def _factor_recent_form(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        score = (h_streak + a_streak) * 0.20
        return round(max(-2.5, min(2.5, score)), 2), f"streaks h:{h_streak:+d} a:{a_streak:+d}"

    def _factor_rest_b2b(self, h_rest: Dict, a_rest: Dict) -> Tuple[float, str]:
        score = 0
        notes = []
        for label, rest in [("H", h_rest), ("A", a_rest)]:
            if rest.get('is_b2b'):
                score -= 1.5
                notes.append(f"{label}:B2B")
        return round(score, 2), ' '.join(notes) if notes else "rested"

    def _factor_spread_context(self, spread: float) -> Tuple[float, str]:
        spread_abs = abs(spread)
        if spread_abs > 18:
            return -2.0, f"blowout {spread:+.1f}"
        elif spread_abs > 12:
            return -1.0, f"wide {spread:+.1f}"
        elif spread_abs < 3:
            return 0.5, f"tight {spread:+.1f}"
        return 0.0, f"neutral {spread:+.1f}"

    def _factor_home_away_splits(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        h_ppg = h_stats.get('ppg', NCAAB_AVG_PPG)
        a_ppg = a_stats.get('ppg', NCAAB_AVG_PPG)
        combined = ((h_ppg - NCAAB_AVG_PPG) + (a_ppg - NCAAB_AVG_PPG)) * 0.12
        return round(max(-2, min(2, combined)), 2), "scoring context"

    def _factor_streak_momentum(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        h_streak = h_stats.get('streak', 0)
        a_streak = a_stats.get('streak', 0)
        if h_streak > 4 and a_streak > 4:
            return 1.5, "both hot"
        elif h_streak < -4 and a_streak < -4:
            return -1.0, "both cold"
        return round(max(-2, min(2, (h_streak + a_streak) * 0.12)), 2), f"h:{h_streak:+d} a:{a_streak:+d}"

    def _factor_referee_tendency(self) -> Tuple[float, str]:
        return 0.0, "stub"

    def _factor_injury_scoring(self, home: str, away: str) -> Tuple[float, str]:
        # No reliable NCAAB injury source — stub with neutral
        return 0.0, "no data"

    def _factor_market_deviation(self, our_raw: float, posted: float) -> Tuple[float, str]:
        dev = our_raw - posted
        score = dev * 0.25
        return round(max(-3, min(3, score)), 2), f"raw={our_raw:.1f} vs posted={posted:.1f}"

    def _factor_pace_trend(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        # No L10 data for NCAAB by default — neutral
        return 0.0, "no trend data"

    # NCAAB-specific factors

    def _factor_tempo_variance(self, h_adv: Dict, a_adv: Dict) -> Tuple[float, str]:
        """NCAAB pace range is ~55-75, much wider than NBA ~95-105."""
        h_pace = h_adv.get('pace', NCAAB_AVG_PACE)
        a_pace = a_adv.get('pace', NCAAB_AVG_PACE)
        pace_spread = abs(h_pace - a_pace)
        # Big pace spread → more uncertainty → lean toward the faster team's pace at home
        if pace_spread > 8:
            # Huge mismatch — game pace unpredictable
            score = 0.5 if h_pace > a_pace else -0.5  # Home team sets pace
            return score, f"tempo variance {pace_spread:.1f} (h={h_pace:.1f} a={a_pace:.1f})"
        return 0.0, f"similar tempo"

    def _factor_conference_style(self, home: str, away: str) -> Tuple[float, str]:
        """Conference play style: some conferences consistently faster/slower."""
        h_conf = self.team_conferences.get(home, '')
        a_conf = self.team_conferences.get(away, '')
        h_pace_adj = CONFERENCE_PACE_PROFILES.get(h_conf, 0)
        a_pace_adj = CONFERENCE_PACE_PROFILES.get(a_conf, 0)
        combined = (h_pace_adj + a_pace_adj) * 0.3
        notes = []
        if h_conf: notes.append(f"H:{h_conf}({h_pace_adj:+.1f})")
        if a_conf: notes.append(f"A:{a_conf}({a_pace_adj:+.1f})")
        return round(max(-2, min(2, combined)), 2), ' '.join(notes) if notes else "unknown conf"

    def _factor_home_court_college(self, h_stats: Dict) -> Tuple[float, str]:
        """NCAAB home court is ~3-4 pts (much bigger than NBA). Affects total via energy/pace."""
        # Strong home teams play faster at home → slight over lean
        h_win_pct = h_stats.get('wins', 0) / max(1, h_stats.get('games_played', 1))
        if h_win_pct > 0.75:
            return 1.0, f"elite home team ({h_win_pct:.0%})"
        elif h_win_pct > 0.60:
            return 0.5, f"strong home ({h_win_pct:.0%})"
        elif h_win_pct < 0.35:
            return -0.5, f"weak home ({h_win_pct:.0%})"
        return 0.0, f"avg home ({h_win_pct:.0%})"

    def _factor_three_pt_variance(self, h_stats: Dict, a_stats: Dict) -> Tuple[float, str]:
        """College 3pt shooting is streakier. High-volume 3pt teams = more variance."""
        # Use PPG deviation from league avg as proxy for 3pt dependency
        h_ppg = h_stats.get('ppg', NCAAB_AVG_PPG)
        a_ppg = a_stats.get('ppg', NCAAB_AVG_PPG)
        # Teams scoring well above average likely rely on 3s
        above_avg = ((h_ppg - NCAAB_AVG_PPG) + (a_ppg - NCAAB_AVG_PPG))
        if above_avg > 15:
            return 0.5, "high-scoring (3pt-heavy?)"
        elif above_avg < -15:
            return -0.5, "low-scoring teams"
        return 0.0, "average"

    def _factor_rivalry(self, home: str, away: str) -> Tuple[float, str]:
        """Rivalry games tend to go under — tighter defense, more intensity."""
        matchup = frozenset({home, away})
        if matchup in NCAAB_RIVALRIES:
            return -1.5, "RIVALRY game — under lean"
        # Fuzzy: check if team names partially match any rivalry
        for rival_pair in NCAAB_RIVALRIES:
            for r in rival_pair:
                if (r.split()[0] in home and r.split()[-1] in home) or \
                   (r.split()[0] in away and r.split()[-1] in away):
                    # Partial match — check other side
                    other = [x for x in rival_pair if x != r][0]
                    other_parts = other.split()
                    if any(p in home or p in away for p in other_parts[:2]):
                        return -1.0, "likely rivalry"
        return 0.0, "non-rivalry"

    # ── Core Prediction ──────────────────────────────────────────

    def predict(self, game: Dict) -> Dict:
        home_raw = game['home_team']
        away_raw = game['away_team']
        posted = game['posted_total']
        spread = game.get('spread', 0)
        game_date_str = game.get('game_date', date.today().isoformat())
        game_date = date.fromisoformat(game_date_str)

        home = _fuzzy_match(home_raw, self.team_stats)
        away = _fuzzy_match(away_raw, self.team_stats)

        h_stats = self.team_stats.get(home, {})
        a_stats = self.team_stats.get(away, {})
        h_adv = self.advanced.get(home, {})
        a_adv = self.advanced.get(away, {})

        # Raw model total
        h_pace = h_adv.get('pace', NCAAB_AVG_PACE)
        a_pace = a_adv.get('pace', NCAAB_AVG_PACE)
        h_ortg = h_adv.get('ortg', NCAAB_AVG_RTG)
        h_drtg = h_adv.get('drtg', NCAAB_AVG_RTG)
        a_ortg = a_adv.get('ortg', NCAAB_AVG_RTG)
        a_drtg = a_adv.get('drtg', NCAAB_AVG_RTG)
        game_pace = (h_pace + a_pace) / 2
        home_pts = (h_ortg * a_drtg / NCAAB_AVG_RTG) * game_pace / 100
        away_pts = (a_ortg * h_drtg / NCAAB_AVG_RTG) * game_pace / 100
        our_raw = round(home_pts + away_pts, 1)

        h_rest = self._get_rest_info(home, game_date)
        a_rest = self._get_rest_info(away, game_date)

        # ── Compute all factor scores ──
        factor_scores = {}
        factor_details = {}

        factors = [
            ('pace_mismatch',      lambda: self._factor_pace_mismatch(h_adv, a_adv)),
            ('ortg_matchup',       lambda: self._factor_ortg_matchup(h_adv, a_adv)),
            ('drtg_matchup',       lambda: self._factor_drtg_matchup(h_adv, a_adv)),
            ('recent_form',        lambda: self._factor_recent_form(h_stats, a_stats)),
            ('rest_b2b',           lambda: self._factor_rest_b2b(h_rest, a_rest)),
            ('spread_context',     lambda: self._factor_spread_context(spread)),
            ('home_away_splits',   lambda: self._factor_home_away_splits(h_stats, a_stats)),
            ('streak_momentum',    lambda: self._factor_streak_momentum(h_stats, a_stats)),
            ('referee_tendency',   lambda: self._factor_referee_tendency()),
            ('injury_scoring',     lambda: self._factor_injury_scoring(home, away)),
            ('market_deviation',   lambda: self._factor_market_deviation(our_raw, posted)),
            ('pace_trend',         lambda: self._factor_pace_trend(h_adv, a_adv)),
            ('tempo_variance',     lambda: self._factor_tempo_variance(h_adv, a_adv)),
            ('conference_style',   lambda: self._factor_conference_style(home, away)),
            ('home_court_college', lambda: self._factor_home_court_college(h_stats)),
            ('three_pt_variance',  lambda: self._factor_three_pt_variance(h_stats, a_stats)),
            ('rivalry_factor',     lambda: self._factor_rivalry(home, away)),
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
        scale = n_factors  # undo the 1/N effect of normalized weights
        weighted_edge = sum(factor_scores[k] * self.weights.get(k, 0) for k in factor_scores) * scale
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
            'home_team_raw': home_raw,
            'away_team_raw': away_raw,
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
            'home_conference': self.team_conferences.get(home, ''),
            'away_conference': self.team_conferences.get(away, ''),
            # For learner
            'home': home,
            'away': away,
        }

    # ── Run ──────────────────────────────────────────────────────

    def run(self, target_date: date = None) -> List[Dict]:
        if target_date is None:
            target_date = date.today()

        logger.info(f"Tempo NCAAB O/U engine running for {target_date}")
        self.fetch_team_stats()

        for d in range(1, 4):
            self._cache_scores(target_date - timedelta(days=d))

        games = self.fetch_games_with_odds(target_date)
        if not games:
            print(f"No NCAAB games found for {target_date}")
            return []

        preds = []
        for g in games:
            p = self.predict(g)
            preds.append(p)
            self._store(p)

        preds.sort(key=lambda x: abs(x['edge']), reverse=True)

        picks_dir = ENGINE_DIR / f"picks_{target_date.isoformat()}"
        picks_dir.mkdir(exist_ok=True)
        picks_file = picks_dir / "ncaab_ou_tempo_picks.json"
        with open(picks_file, 'w') as f:
            json.dump(preds, f, indent=2, default=str)
        logger.info(f"Saved {len(preds)} picks to {picks_file}")

        actionable = [p for p in preds if p['pick'] != 'PASS']
        logger.info(f"{len(actionable)} actionable from {len(preds)} games")
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
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={dt_str}&groups=50&limit=500"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200: return
            data = resp.json()
            conn = sqlite3.connect(str(DB_PATH))
            c = conn.cursor()
            for event in data.get('events', []):
                status = event.get('status', {}).get('type', {}).get('name', '')
                if status != 'STATUS_FINAL': continue
                comps = event.get('competitions', [{}])[0]
                competitors = comps.get('competitors', [])
                home_data = away_data = None
                for comp in competitors:
                    if comp.get('homeAway') == 'home': home_data = comp
                    else: away_data = comp
                if not home_data or not away_data: continue
                home_name = home_data['team'].get('displayName', '')
                away_name = away_data['team'].get('displayName', '')
                home_score = int(home_data.get('score', 0))
                away_score = int(away_data.get('score', 0))
                c.execute('INSERT OR IGNORE INTO game_scores_cache VALUES (?,?,?,?,?,?)',
                          (target_date.isoformat(), home_name, away_name,
                           home_score, away_score, home_score + away_score))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Score cache error {target_date}: {e}")

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
            print(f"No Tempo predictions for {target_date}")
            return

        correct = total = 0
        print(f"\n  🎵 TEMPO NCAAB O/U Results — {target_date}")
        print(f"  {'─'*50}")
        for home, away, posted, pick, edge, tier in preds:
            key = f"{home}|{away}"
            actual = scores.get(key)
            if actual is None or pick == 'PASS': continue
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
        print(f"  🎵 TEMPO NCAAB O/U BACKTEST — Last {days} days")
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
        print(f"  🎵 TEMPO NCAAB O/U v{ENGINE_VERSION} — {preds[0].get('game_date', 'Today')}")
        print(f"  16-factor self-learning model | Weights: {'learned' if self.learner and self.learner.weights_file.exists() else 'default'}")
        print(f"{'='*70}")

        for p in actionable:
            fs = p['factor_scores']
            fd = p['factor_details']
            conf_info = ""
            if p.get('home_conference') or p.get('away_conference'):
                conf_info = f" | {p.get('away_conference','')} vs {p.get('home_conference','')}"
            print(f"\n  {p['away_team']} @ {p['home_team']}{conf_info}")
            print(f"    Posted: {p['posted_total']}  |  Raw: {p['our_raw_total']}  |  Predicted: {p['predicted_total']}")
            print(f"    ➜ {p['pick']} {p['posted_total']}  |  Edge: {p['edge']:+.1f}  |  {p['tier']}")
            print(f"    Pace: {p['game_pace']} | Est pts: {p['home_pts_est']}-{p['away_pts_est']}")
            sorted_f = sorted(fs.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            for name, score in sorted_f:
                if abs(score) > 0.1:
                    arrow = "⬆️" if score > 0 else "⬇️"
                    print(f"    {arrow} {name}: {score:+.2f} ({fd.get(name, '')})")

        if passed:
            print(f"\n  ⏭️ PASS ({len(passed)} games):")
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
            f"🎵 TEMPO NCAAB O/U — {gd}",
            f"16-factor self-learning | {len(actionable)} picks | {len(passed)} pass",
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
    parser = argparse.ArgumentParser(description='Tempo — NCAAB O/U Self-Learning Engine')
    parser.add_argument('--date', type=str, help='Target date YYYY-MM-DD')
    parser.add_argument('--backtest', type=int, help='Backtest last N days')
    parser.add_argument('--score', type=str, help='Score predictions for date')
    args = parser.parse_args()

    engine = TempoEngine()

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
            tg_path = ENGINE_DIR / f"picks_{target.isoformat()}" / "ncaab_ou_tempo_telegram.txt"
            tg_path.parent.mkdir(exist_ok=True)
            with open(tg_path, 'w', encoding='utf-8') as f:
                f.write(tg)
            print(f"\nTelegram: {tg_path}")


if __name__ == '__main__':
    main()
