"""
Analyzer module for ParlayGuarantee Engine
Analyzes games and generates scoring/rankings based on multiple factors

v2.0 — Added upset detection, h2h, momentum, clutch, tank bowl, streak,
        3PT matchup, post-ASB, home record, star matchup factors (2026-02-20)
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from config import *

# Configure logging
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# New factor weights — tune these as we gather data
# ---------------------------------------------------------------------------
UPSET_WEIGHTS = {
    'h2h':              0.12,   # Head-to-head season series
    'momentum':         0.10,   # Last-10 form
    'clutch':           0.06,   # Record in close games
    'streak':           0.07,   # Win/loss streak inflation/deflation
    'three_pt_matchup': 0.08,   # 3PT shooting vs opponent 3PT defense
    'post_asb':         0.04,   # Post-All-Star-Break letdown
    'home_record':      0.08,   # Actual home/away record vs generic 60%
    'star_matchup':     0.10,   # Star player dominance vs specific team
}

# All-Star Break date for 2025-26 season (Sunday)
ASB_END_DATE = datetime(2026, 2, 16)
ASB_WINDOW_DAYS = 5  # games within this many days after ASB

TANK_THRESHOLD = 0.35  # win% below this = tanking team
TANK_MAX_CONFIDENCE = 52.0


@dataclass
class GameAnalysis:
    """Data class for storing game analysis results"""
    game_id: str
    home_team: str
    away_team: str
    home_score: float
    away_score: float
    spread_pick: str
    spread_confidence: float
    moneyline_pick: str
    moneyline_confidence: float
    total_pick: str
    total_confidence: float
    reasoning: Dict[str, str]
    factors: Dict[str, float]


class GameAnalyzer:
    """Main analyzer for NBA games"""
    
    def __init__(self, data: Dict):
        self.data = data
        self.games = data.get('games', [])
        self.team_stats = data.get('team_stats', {})
        self.odds_data = data.get('odds', [])
        self.injury_data = data.get('injuries', {})
        
        # Create odds lookup for quick access
        self.odds_lookup = self._create_odds_lookup()
        
        logger.info(f"GameAnalyzer initialized with {len(self.games)} games")
    
    # ------------------------------------------------------------------
    # Odds helpers
    # ------------------------------------------------------------------
    def _create_odds_lookup(self) -> Dict:
        """Create a lookup dictionary for odds by team matchup"""
        odds_lookup = {}
        for game_odds in self.odds_data:
            if 'teams' in game_odds and len(game_odds['teams']) == 2:
                home_team = game_odds['teams'][0]
                away_team = game_odds['teams'][1]
                matchup_key = f"{away_team} @ {home_team}"
                alt_key = f"{home_team} vs {away_team}"
                odds_lookup[matchup_key] = game_odds
                odds_lookup[alt_key] = game_odds
        return odds_lookup

    # ------------------------------------------------------------------
    # Original factors
    # ------------------------------------------------------------------
    def calculate_travel_distance(self, team1: str, team2: str) -> float:
        if team1 not in NBA_TEAM_COORDS or team2 not in NBA_TEAM_COORDS:
            return 1000
        lat1, lon1 = NBA_TEAM_COORDS[team1]
        lat2, lon2 = NBA_TEAM_COORDS[team2]
        R = 3959
        lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
        lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    
    def get_timezone_change(self, away_team: str, home_team: str) -> int:
        away_tz = home_tz = None
        for tz, teams in TEAM_TIMEZONES.items():
            if away_team in teams:
                away_tz = tz
            if home_team in teams:
                home_tz = tz
        if not away_tz or not home_tz:
            return 0
        tz_order = ['Pacific', 'Mountain', 'Central', 'Eastern']
        try:
            return tz_order.index(home_tz) - tz_order.index(away_tz)
        except ValueError:
            return 0
    
    def analyze_team_factors(self, team: str, is_home: bool) -> Dict[str, float]:
        factors = {}
        team_stats = self.team_stats.get(team, {})
        if not team_stats:
            logger.warning(f"No stats found for team: {team}")
            return factors
        win_pct = team_stats.get('win_pct', 0.5)
        factors['record_strength'] = win_pct
        if is_home:
            factors['home_advantage'] = 0.6
        else:
            factors['home_advantage'] = 0.4
        off_rating = team_stats.get('offensive_rating', 110)
        def_rating = team_stats.get('defensive_rating', 110)
        factors['offensive_efficiency'] = min(off_rating / 110, 1.3)
        factors['defensive_efficiency'] = min(110 / def_rating, 1.3)
        pace = team_stats.get('pace', 100)
        factors['pace'] = pace / 100
        return factors
    
    def analyze_situational_factors(self, game: Dict) -> Dict[str, float]:
        factors = {}
        home_team = game['home_team']
        away_team = game['away_team']
        distance = self.calculate_travel_distance(away_team, home_team)
        factors['travel_distance'] = min(distance / 2500, 1.0)
        tz_change = self.get_timezone_change(away_team, home_team)
        factors['timezone_change'] = abs(tz_change) / 3
        factors['altitude_advantage'] = 0.1 if home_team in HIGH_ALTITUDE_VENUES else 0.0
        factors['home_back_to_back'] = 0.0
        factors['away_back_to_back'] = 0.0
        return factors
    
    def analyze_injury_impact(self, team: str) -> float:
        team_injuries = self.injury_data.get(team, {})
        if not team_injuries:
            return 0.0
        impact_score = 0.0
        impact_score += len(team_injuries.get('out', [])) * 0.15
        impact_score += len(team_injuries.get('doubtful', [])) * 0.10
        impact_score += len(team_injuries.get('questionable', [])) * 0.05
        return min(impact_score, 0.5)

    # ------------------------------------------------------------------
    # NEW FACTORS (v2.0)
    # ------------------------------------------------------------------

    def analyze_h2h(self, home_team: str, away_team: str) -> Tuple[float, float, str]:
        """Head-to-head season series. Returns (home_adj, away_adj, reasoning)."""
        h2h = self.data.get('h2h_history', {})
        # Expected format: { "TeamA vs TeamB": { "team_a_wins": 3, "team_b_wins": 0,
        #   "avg_margin": 22.5, "games": [...] } }
        # Try both key orderings
        key1 = f"{home_team} vs {away_team}"
        key2 = f"{away_team} vs {home_team}"
        record = h2h.get(key1) or h2h.get(key2)
        if not record:
            return 0.0, 0.0, ""

        # Determine which side is which
        if key1 in h2h:
            home_wins = record.get('team_a_wins', 0)
            away_wins = record.get('team_b_wins', 0)
        else:
            home_wins = record.get('team_b_wins', 0)
            away_wins = record.get('team_a_wins', 0)

        total = home_wins + away_wins
        if total == 0:
            return 0.0, 0.0, ""

        home_h2h_pct = home_wins / total
        away_h2h_pct = away_wins / total
        avg_margin = record.get('avg_margin', 0)

        # Scale: 0.5 = even, 1.0 = sweep. Margin adds extra juice.
        margin_bonus = min(abs(avg_margin) / 40, 0.25)  # up to 0.25 extra
        home_adj = (home_h2h_pct - 0.5) + (margin_bonus if home_h2h_pct > 0.5 else -margin_bonus)
        away_adj = (away_h2h_pct - 0.5) + (margin_bonus if away_h2h_pct > 0.5 else -margin_bonus)

        dominant = home_team if home_h2h_pct > 0.5 else away_team
        reason = f"H2H: {home_team} {home_wins}-{away_wins} vs {away_team} (avg margin {avg_margin:+.1f}). {dominant} dominates this matchup."
        return home_adj, away_adj, reason

    def analyze_momentum(self, team: str) -> Tuple[float, str]:
        """Last-10 games form. Returns (adjustment, reasoning)."""
        recent = self.data.get('recent_form', {}).get(team)
        if not recent:
            return 0.0, ""
        wins = recent.get('wins', recent.get('last_10_wins', 5))
        losses = recent.get('losses', recent.get('last_10_losses', 5))
        total = wins + losses
        if total == 0:
            return 0.0, ""
        pct = wins / total
        # Center around 0.5 — hot team gets positive, cold gets negative
        adj = (pct - 0.5) * 2  # range roughly -1 to +1
        label = "🔥 HOT" if pct >= 0.7 else ("🧊 COLD" if pct <= 0.3 else "neutral")
        reason = f"{team} last {total}: {wins}-{losses} ({label})"
        return adj, reason

    def analyze_clutch(self, team: str) -> Tuple[float, str]:
        """Record in games decided by ≤5 pts. Returns (adjustment, reasoning)."""
        clutch = self.data.get('clutch_record', {}).get(team)
        if not clutch:
            return 0.0, ""
        wins = clutch.get('wins', 0)
        losses = clutch.get('losses', 0)
        total = wins + losses
        if total < 3:  # not enough sample
            return 0.0, ""
        pct = wins / total
        adj = (pct - 0.5) * 1.5  # amplify clutch signal
        reason = f"{team} clutch record: {wins}-{losses} in games decided by ≤5 pts"
        return adj, reason

    def detect_tank_bowl(self, home_team: str, away_team: str) -> Tuple[bool, str]:
        """Both teams tanking → NO-PICK."""
        home_wp = self.team_stats.get(home_team, {}).get('win_pct', 0.5)
        away_wp = self.team_stats.get(away_team, {}).get('win_pct', 0.5)
        if home_wp < TANK_THRESHOLD and away_wp < TANK_THRESHOLD:
            reason = (f"🚨 TANK BOWL: {home_team} ({home_wp:.3f}) vs {away_team} ({away_wp:.3f}). "
                      f"Both below {TANK_THRESHOLD} win%. Coin flip — NO EDGE.")
            return True, reason
        return False, ""

    def analyze_streak(self, team: str) -> Tuple[float, str]:
        """Win/loss streak analysis. Returns (opponent_adjustment, reasoning).
        A long win streak means the market overvalues this team → opponent gets value.
        """
        recent = self.data.get('recent_form', {}).get(team)
        if not recent:
            return 0.0, ""
        streak = recent.get('streak', 0)  # positive = wins, negative = losses
        if abs(streak) < 4:
            return 0.0, ""
        # Long win streak → opponent value (negative for this team)
        # Long lose streak → this team due for bounce (positive for this team)
        if streak >= 7:
            adj = -0.3  # big penalty — overvalued
            reason = f"{team} on {streak}-game WIN streak — market likely overvaluing"
        elif streak >= 4:
            adj = -0.15
            reason = f"{team} on {streak}-game WIN streak — slight overvaluation risk"
        elif streak <= -7:
            adj = 0.2  # due for bounce
            reason = f"{team} on {abs(streak)}-game LOSING streak — regression/bounce candidate"
        else:  # -4 to -6
            adj = 0.1
            reason = f"{team} on {abs(streak)}-game LOSING streak — slight bounce potential"
        return adj, reason

    def analyze_three_pt_matchup(self, home_team: str, away_team: str) -> Tuple[float, float, str]:
        """3PT shooting vs opponent 3PT defense mismatch. Returns (home_adj, away_adj, reasoning)."""
        shooting = self.data.get('shooting_stats', {})
        home_shoot = shooting.get(home_team)
        away_shoot = shooting.get(away_team)
        if not home_shoot or not away_shoot:
            return 0.0, 0.0, ""

        # Home team's 3PT% vs away team's opp_3pt_pct (how well opponents shoot 3s against them)
        home_3pct = home_shoot.get('three_pt_pct', 0.36)
        away_opp_3pct = away_shoot.get('opp_three_pt_pct', 0.36)
        # If home shoots well AND away allows good 3PT shooting → home exploit
        home_exploit = home_3pct - away_opp_3pct  # positive = home has edge

        away_3pct = away_shoot.get('three_pt_pct', 0.36)
        home_opp_3pct = home_shoot.get('opp_three_pt_pct', 0.36)
        away_exploit = away_3pct - home_opp_3pct

        # Also factor in volume (3PA per game)
        home_3pa = home_shoot.get('three_pt_attempts', 35)
        away_3pa = away_shoot.get('three_pt_attempts', 35)

        # Scale: if a team shoots 40% from 3 and opponent allows 38% → +0.02 raw
        # Multiply by volume factor to reward high-volume shooters
        home_vol = min(home_3pa / 35, 1.3)
        away_vol = min(away_3pa / 35, 1.3)

        home_adj = home_exploit * home_vol * 3  # scale up to meaningful range
        away_adj = away_exploit * away_vol * 3

        reasons = []
        if abs(home_adj) > 0.05:
            reasons.append(f"{home_team} 3PT {'exploit' if home_adj > 0 else 'mismatch'}: {home_3pct:.1%} vs {away_team} allows {away_opp_3pct:.1%}")
        if abs(away_adj) > 0.05:
            reasons.append(f"{away_team} 3PT {'exploit' if away_adj > 0 else 'mismatch'}: {away_3pct:.1%} vs {home_team} allows {home_opp_3pct:.1%}")

        return home_adj, away_adj, " | ".join(reasons) if reasons else ""

    def analyze_post_asb(self, game: Dict) -> Tuple[float, str]:
        """Post-All-Star Break letdown. Returns (favorite_penalty, reasoning)."""
        game_time = game.get('game_time', '')
        if not game_time:
            return 0.0, ""
        try:
            if isinstance(game_time, str):
                game_dt = datetime.fromisoformat(game_time.replace('Z', '+00:00'))
            else:
                game_dt = game_time
        except (ValueError, TypeError):
            return 0.0, ""

        # Make both naive for comparison
        game_date = game_dt.replace(tzinfo=None) if game_dt.tzinfo else game_dt
        days_after = (game_date - ASB_END_DATE).days

        if 0 <= days_after <= ASB_WINDOW_DAYS:
            penalty = 0.15 * (1 - days_after / ASB_WINDOW_DAYS)  # decays over the window
            reason = f"Post-ASB game (day {days_after + 1}): favorites historically underperform. Penalty: {penalty:.3f}"
            return penalty, reason
        return 0.0, ""

    def analyze_home_record(self, home_team: str, away_team: str) -> Tuple[float, float, str]:
        """Replace generic 60% home advantage with actual home/away records."""
        home_stats = self.team_stats.get(home_team, {})
        away_stats = self.team_stats.get(away_team, {})

        home_wp = home_stats.get('home_win_pct')
        away_wp = away_stats.get('away_win_pct')

        if home_wp is None and away_wp is None:
            return 0.0, 0.0, ""

        home_adj = 0.0
        away_adj = 0.0
        reasons = []

        if home_wp is not None:
            # Compare actual home record to the generic 0.6 assumption
            home_adj = (home_wp - 0.6) * 1.5  # amplify the signal
            reasons.append(f"{home_team} home record: {home_wp:.1%} ({'strong' if home_wp > 0.6 else 'WEAK'})")

        if away_wp is not None:
            # Good road teams get a boost, bad road teams get penalized
            away_adj = (away_wp - 0.4) * 1.5
            reasons.append(f"{away_team} road record: {away_wp:.1%} ({'strong' if away_wp > 0.4 else 'weak'})")

        return home_adj, away_adj, " | ".join(reasons)

    def analyze_star_matchup(self, home_team: str, away_team: str) -> Tuple[float, float, str]:
        """Star player dominance vs specific opponent."""
        matchups = self.data.get('star_matchups', {})
        # Expected: { "Cade Cunningham vs New York Knicks": { "avg_pts": 38.5, "avg_reb": 11.0,
        #   "team": "Detroit Pistons", "games": 3, "team_record": "3-0" } }
        home_adj = 0.0
        away_adj = 0.0
        reasons = []

        for key, info in matchups.items():
            player_team = info.get('team', '')
            games = info.get('games', 0)
            if games < 2:
                continue
            avg_pts = info.get('avg_pts', 0)
            record = info.get('team_record', '')
            wins = 0
            try:
                parts = record.split('-')
                wins = int(parts[0])
            except (ValueError, IndexError):
                pass

            # Determine which side benefits
            if player_team == home_team and away_team.lower() in key.lower():
                dominance = min((avg_pts - 20) / 30, 1.0) * (wins / max(games, 1))
                home_adj += dominance * 0.5
                reasons.append(f"⭐ Star matchup: {key} — {avg_pts:.1f} PPG in {games}G ({record})")
            elif player_team == away_team and home_team.lower() in key.lower():
                dominance = min((avg_pts - 20) / 30, 1.0) * (wins / max(games, 1))
                away_adj += dominance * 0.5
                reasons.append(f"⭐ Star matchup: {key} — {avg_pts:.1f} PPG in {games}G ({record})")

        return home_adj, away_adj, " | ".join(reasons) if reasons else ""

    def calculate_upset_potential(self, fav_team: str, dog_team: str,
                                  factor_scores: Dict[str, float]) -> Tuple[int, bool, str]:
        """Calculate upset potential 0-100 for the underdog. Returns (score, is_alert, reasoning)."""
        signals = []
        raw = 0.0

        # Each factor that favors the dog adds to upset potential
        h2h = factor_scores.get('h2h_dog', 0)
        if h2h > 0.1:
            raw += 20
            signals.append(f"H2H favors dog (+{h2h:.2f})")

        momentum_dog = factor_scores.get('momentum_dog', 0)
        momentum_fav = factor_scores.get('momentum_fav', 0)
        if momentum_dog > 0.3:
            raw += 15
            signals.append("Dog is HOT (last 10)")
        if momentum_fav < -0.2:
            raw += 10
            signals.append("Favorite is COLD")

        three_pt = factor_scores.get('three_pt_dog', 0)
        if three_pt > 0.05:
            raw += 15
            signals.append("3PT matchup exploit for dog")

        home_rec = factor_scores.get('home_record_fav', 0)
        if home_rec < -0.1:
            raw += 15
            signals.append("Favorite has WEAK home record")

        streak_fav = factor_scores.get('streak_fav', 0)
        if streak_fav < -0.1:
            raw += 10
            signals.append("Favorite on long win streak (overvalued)")

        star = factor_scores.get('star_dog', 0)
        if star > 0.1:
            raw += 15
            signals.append("Star player dominates this matchup")

        clutch_dog = factor_scores.get('clutch_dog', 0)
        if clutch_dog > 0.2:
            raw += 10
            signals.append("Dog is clutch in close games")

        score = min(int(raw), 100)
        is_alert = score >= 55
        reason = f"Upset potential {score}/100 for {dog_team}."
        if signals:
            reason += " Signals: " + ", ".join(signals)
        if is_alert:
            reason = f"🚨 UPSET ALERT: " + reason
        return score, is_alert, reason

    # ------------------------------------------------------------------
    # Market odds extraction (unchanged)
    # ------------------------------------------------------------------
    def get_market_odds(self, game: Dict) -> Dict[str, str]:
        home_team = game['home_team']
        away_team = game['away_team']
        matchup_key = f"{away_team} @ {home_team}"
        game_odds = self.odds_lookup.get(matchup_key)

        if not game_odds or 'bookmakers' not in game_odds:
            return {
                'home_ml': DEFAULT_ODDS, 'away_ml': DEFAULT_ODDS,
                'home_spread': DEFAULT_ODDS, 'away_spread': DEFAULT_ODDS,
                'over': DEFAULT_ODDS, 'under': DEFAULT_ODDS, 'total_line': 220.5
            }

        bookmaker = game_odds['bookmakers'][0]
        markets = {market['key']: market for market in bookmaker['markets']}
        odds_data = {
            'home_ml': DEFAULT_ODDS, 'away_ml': DEFAULT_ODDS,
            'home_spread': DEFAULT_ODDS, 'away_spread': DEFAULT_ODDS,
            'over': DEFAULT_ODDS, 'under': DEFAULT_ODDS, 'total_line': 220.5
        }

        if 'h2h' in markets:
            for outcome in markets['h2h']['outcomes']:
                fmt = lambda p: f"+{p}" if p > 0 else str(p)
                if outcome['name'] == home_team:
                    odds_data['home_ml'] = fmt(outcome['price'])
                elif outcome['name'] == away_team:
                    odds_data['away_ml'] = fmt(outcome['price'])

        if 'spreads' in markets:
            for outcome in markets['spreads']['outcomes']:
                fmt = lambda p: f"+{p}" if p > 0 else str(p)
                if outcome['name'] == home_team:
                    odds_data['home_spread'] = fmt(outcome['price'])
                elif outcome['name'] == away_team:
                    odds_data['away_spread'] = fmt(outcome['price'])

        if 'totals' in markets:
            for outcome in markets['totals']['outcomes']:
                fmt = lambda p: f"+{p}" if p > 0 else str(p)
                if outcome['name'] == 'Over':
                    odds_data['over'] = fmt(outcome['price'])
                    odds_data['total_line'] = outcome['point']
                elif outcome['name'] == 'Under':
                    odds_data['under'] = fmt(outcome['price'])

        return odds_data

    # ------------------------------------------------------------------
    # MAIN ANALYSIS (upgraded)
    # ------------------------------------------------------------------
    def analyze_game(self, game: Dict) -> GameAnalysis:
        """Analyze a single game and generate picks"""
        logger.info(f"Analyzing game: {game['away_team']} @ {game['home_team']}")
        
        home_team = game['home_team']
        away_team = game['away_team']
        
        # --- Original factors ---
        home_factors = self.analyze_team_factors(home_team, is_home=True)
        away_factors = self.analyze_team_factors(away_team, is_home=False)
        situational = self.analyze_situational_factors(game)
        home_injury_impact = self.analyze_injury_impact(home_team)
        away_injury_impact = self.analyze_injury_impact(away_team)
        odds = self.get_market_odds(game)

        # --- NEW factors ---
        upset_reasons = []
        factor_scores = {}  # for upset potential calc

        # 1. Head-to-Head
        h2h_home, h2h_away, h2h_reason = self.analyze_h2h(home_team, away_team)
        if h2h_reason:
            upset_reasons.append(h2h_reason)

        # 2. Momentum
        mom_home, mom_home_reason = self.analyze_momentum(home_team)
        mom_away, mom_away_reason = self.analyze_momentum(away_team)
        if mom_home_reason:
            upset_reasons.append(mom_home_reason)
        if mom_away_reason:
            upset_reasons.append(mom_away_reason)

        # 3. Clutch
        clutch_home, clutch_home_reason = self.analyze_clutch(home_team)
        clutch_away, clutch_away_reason = self.analyze_clutch(away_team)
        if clutch_home_reason:
            upset_reasons.append(clutch_home_reason)
        if clutch_away_reason:
            upset_reasons.append(clutch_away_reason)

        # 4. Tank Bowl
        is_tank_bowl, tank_reason = self.detect_tank_bowl(home_team, away_team)
        if tank_reason:
            upset_reasons.append(tank_reason)

        # 5. Streak
        streak_home, streak_home_reason = self.analyze_streak(home_team)
        streak_away, streak_away_reason = self.analyze_streak(away_team)
        if streak_home_reason:
            upset_reasons.append(streak_home_reason)
        if streak_away_reason:
            upset_reasons.append(streak_away_reason)

        # 6. 3PT Matchup
        tpm_home, tpm_away, tpm_reason = self.analyze_three_pt_matchup(home_team, away_team)
        if tpm_reason:
            upset_reasons.append(tpm_reason)

        # 7. Post-ASB
        asb_penalty, asb_reason = self.analyze_post_asb(game)
        if asb_reason:
            upset_reasons.append(asb_reason)

        # 8. Home Record
        hr_home, hr_away, hr_reason = self.analyze_home_record(home_team, away_team)
        if hr_reason:
            upset_reasons.append(hr_reason)

        # 9. Star Matchup
        star_home, star_away, star_reason = self.analyze_star_matchup(home_team, away_team)
        if star_reason:
            upset_reasons.append(star_reason)

        # --- Composite scores ---
        home_score = (
            home_factors.get('record_strength', 0.5) * ANALYSIS_WEIGHTS['record'] +
            home_factors.get('home_advantage', 0.6) * ANALYSIS_WEIGHTS['home_away'] +
            home_factors.get('offensive_efficiency', 1.0) * ANALYSIS_WEIGHTS['offensive_rating'] +
            home_factors.get('defensive_efficiency', 1.0) * ANALYSIS_WEIGHTS['defensive_rating'] +
            situational.get('altitude_advantage', 0) * 0.05 -
            home_injury_impact * ANALYSIS_WEIGHTS['injuries'] -
            situational.get('home_back_to_back', 0) * ANALYSIS_WEIGHTS['back_to_back'] +
            # NEW factors
            h2h_home * UPSET_WEIGHTS['h2h'] +
            mom_home * UPSET_WEIGHTS['momentum'] +
            clutch_home * UPSET_WEIGHTS['clutch'] +
            streak_home * UPSET_WEIGHTS['streak'] +
            tpm_home * UPSET_WEIGHTS['three_pt_matchup'] +
            hr_home * UPSET_WEIGHTS['home_record'] +
            star_home * UPSET_WEIGHTS['star_matchup']
        )
        
        away_score = (
            away_factors.get('record_strength', 0.5) * ANALYSIS_WEIGHTS['record'] +
            away_factors.get('home_advantage', 0.4) * ANALYSIS_WEIGHTS['home_away'] +
            away_factors.get('offensive_efficiency', 1.0) * ANALYSIS_WEIGHTS['offensive_rating'] +
            away_factors.get('defensive_efficiency', 1.0) * ANALYSIS_WEIGHTS['defensive_rating'] -
            situational.get('travel_distance', 0) * ANALYSIS_WEIGHTS['travel_fatigue'] -
            situational.get('timezone_change', 0) * 0.02 -
            away_injury_impact * ANALYSIS_WEIGHTS['injuries'] -
            situational.get('away_back_to_back', 0) * ANALYSIS_WEIGHTS['back_to_back'] +
            # NEW factors
            h2h_away * UPSET_WEIGHTS['h2h'] +
            mom_away * UPSET_WEIGHTS['momentum'] +
            clutch_away * UPSET_WEIGHTS['clutch'] +
            streak_away * UPSET_WEIGHTS['streak'] +
            tpm_away * UPSET_WEIGHTS['three_pt_matchup'] +
            hr_away * UPSET_WEIGHTS['home_record'] +
            star_away * UPSET_WEIGHTS['star_matchup']
        )

        # Post-ASB penalty: penalize whoever is the favorite
        if asb_penalty > 0:
            if home_score > away_score:
                home_score -= asb_penalty * UPSET_WEIGHTS['post_asb']
            else:
                away_score -= asb_penalty * UPSET_WEIGHTS['post_asb']

        # --- Generate picks ---
        score_diff = abs(home_score - away_score)
        base_confidence = min(55 + (score_diff * 100), 85)

        # Tank bowl cap
        if is_tank_bowl:
            base_confidence = min(base_confidence, TANK_MAX_CONFIDENCE)

        # Determine favorite/dog for upset calc
        if home_score >= away_score:
            fav_team, dog_team = home_team, away_team
            factor_scores.update({
                'h2h_dog': h2h_away, 'momentum_dog': mom_away, 'momentum_fav': mom_home,
                'three_pt_dog': tpm_away, 'home_record_fav': hr_home,
                'streak_fav': streak_home, 'star_dog': star_away, 'clutch_dog': clutch_away,
            })
        else:
            fav_team, dog_team = away_team, home_team
            factor_scores.update({
                'h2h_dog': h2h_home, 'momentum_dog': mom_home, 'momentum_fav': mom_away,
                'three_pt_dog': tpm_home, 'home_record_fav': hr_away,
                'streak_fav': streak_away, 'star_dog': star_home, 'clutch_dog': clutch_home,
            })

        # 10. Upset potential
        upset_score, upset_alert, upset_reason = self.calculate_upset_potential(
            fav_team, dog_team, factor_scores)
        upset_reasons.append(upset_reason)

        # Spread pick
        if home_score > away_score:
            spread_pick = f"{home_team} (spread TBD)"
            spread_confidence = base_confidence
        else:
            spread_pick = f"{away_team} (spread TBD)"
            spread_confidence = base_confidence

        if is_tank_bowl:
            spread_pick += " ⚠️ TANK BOWL — NO-PICK RECOMMENDED"

        if upset_alert:
            spread_pick += f" 🚨 UPSET ALERT ({dog_team})"

        # Moneyline pick
        if home_score > away_score:
            moneyline_pick = f"{home_team} ML"
            moneyline_confidence = base_confidence - 5
        else:
            moneyline_pick = f"{away_team} ML"
            moneyline_confidence = base_confidence - 5

        # Total pick
        pace_factor = (home_factors.get('pace', 1.0) + away_factors.get('pace', 1.0)) / 2
        total_line = odds.get('total_line', 220.5)
        if pace_factor > 1.05:
            total_pick = f"Over {total_line}"
            total_confidence = base_confidence - 10
        else:
            total_pick = f"Under {total_line}"
            total_confidence = base_confidence - 10

        # --- Reasoning ---
        reasoning = {
            'spread': self._generate_spread_reasoning(home_team, away_team, home_score, away_score,
                                                      home_factors, away_factors, situational),
            'moneyline': self._generate_moneyline_reasoning(home_team, away_team, home_score, away_score),
            'total': self._generate_total_reasoning(total_pick, pace_factor, total_line),
            'upset': "\n".join([r for r in upset_reasons if r]),
        }

        # --- All factors ---
        all_factors = {
            'home_score': home_score,
            'away_score': away_score,
            'score_differential': score_diff,
            'home_injury_impact': home_injury_impact,
            'away_injury_impact': away_injury_impact,
            # New factors
            'h2h_home': h2h_home,
            'h2h_away': h2h_away,
            'momentum_home': mom_home,
            'momentum_away': mom_away,
            'clutch_home': clutch_home,
            'clutch_away': clutch_away,
            'streak_home': streak_home,
            'streak_away': streak_away,
            'three_pt_home': tpm_home,
            'three_pt_away': tpm_away,
            'post_asb_penalty': asb_penalty,
            'home_record_adj_home': hr_home,
            'home_record_adj_away': hr_away,
            'star_matchup_home': star_home,
            'star_matchup_away': star_away,
            'tank_bowl': is_tank_bowl,
            'upset_potential': upset_score,
            'upset_alert': upset_alert,
            **home_factors,
            **away_factors,
            **situational,
        }

        return GameAnalysis(
            game_id=game.get('game_id', 'unknown'),
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            spread_pick=spread_pick,
            spread_confidence=spread_confidence,
            moneyline_pick=moneyline_pick,
            moneyline_confidence=moneyline_confidence,
            total_pick=total_pick,
            total_confidence=total_confidence,
            reasoning=reasoning,
            factors=all_factors
        )

    # ------------------------------------------------------------------
    # Reasoning generators
    # ------------------------------------------------------------------
    def _generate_spread_reasoning(self, home_team, away_team, home_score, away_score,
                                   home_factors, away_factors, situational) -> str:
        if home_score > away_score:
            favorite = home_team
            reasons = [
                f"{home_team} has home court advantage",
                f"Superior record strength: {home_factors.get('record_strength', 0.5):.3f}"
            ]
        else:
            favorite = away_team
            reasons = [
                f"{away_team} has better overall metrics",
                f"Record strength advantage: {away_factors.get('record_strength', 0.5):.3f}"
            ]
        if situational.get('travel_distance', 0) > 0.5:
            reasons.append(f"Long travel distance affects {away_team}")
        if situational.get('altitude_advantage', 0) > 0:
            reasons.append(f"{home_team} has altitude advantage")
        return f"{favorite} favored. " + ", ".join(reasons[:3])

    def _generate_moneyline_reasoning(self, home_team, away_team, home_score, away_score) -> str:
        if home_score > away_score:
            return f"{home_team} projected to win straight up based on comprehensive analysis"
        return f"{away_team} has edge despite playing on the road"

    def _generate_total_reasoning(self, total_pick, pace_factor, total_line) -> str:
        if "Over" in total_pick:
            return f"High-pace matchup (pace factor: {pace_factor:.2f}), expect scoring over {total_line}"
        return f"Defensive-minded game, pace factor {pace_factor:.2f} suggests under {total_line}"

    # ------------------------------------------------------------------
    # Batch analysis
    # ------------------------------------------------------------------
    def analyze_all_games(self) -> List[GameAnalysis]:
        logger.info(f"Starting analysis of {len(self.games)} games")
        analyses = []
        for game in self.games:
            try:
                analysis = self.analyze_game(game)
                analyses.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing game {game}: {str(e)}")
        logger.info(f"Completed analysis of {len(analyses)} games")
        return analyses


if __name__ == "__main__":
    sample_data = {
        'games': [
            {
                'game_id': 'test_1',
                'home_team': 'New York Knicks',
                'away_team': 'Detroit Pistons',
                'game_time': '2026-02-19T19:30:00'
            }
        ],
        'team_stats': {
            'New York Knicks': {
                'win_pct': 0.550, 'offensive_rating': 114.2, 'defensive_rating': 112.0,
                'pace': 99.0, 'home_win_pct': 0.500, 'away_win_pct': 0.600
            },
            'Detroit Pistons': {
                'win_pct': 0.759, 'offensive_rating': 117.8, 'defensive_rating': 108.5,
                'pace': 100.5, 'home_win_pct': 0.800, 'away_win_pct': 0.700
            }
        },
        'odds': [],
        'injuries': {},
        'h2h_history': {
            'Detroit Pistons vs New York Knicks': {
                'team_a_wins': 3, 'team_b_wins': 0, 'avg_margin': 25.0
            }
        },
        'recent_form': {
            'Detroit Pistons': {'wins': 8, 'losses': 2, 'streak': 5},
            'New York Knicks': {'wins': 4, 'losses': 6, 'streak': -2}
        },
        'star_matchups': {
            'Cade Cunningham vs New York Knicks': {
                'avg_pts': 38.5, 'avg_reb': 11.0, 'team': 'Detroit Pistons',
                'games': 3, 'team_record': '3-0'
            }
        },
        'shooting_stats': {
            'Detroit Pistons': {'three_pt_pct': 0.375, 'opp_three_pt_pct': 0.340, 'three_pt_attempts': 38},
            'New York Knicks': {'three_pt_pct': 0.350, 'opp_three_pt_pct': 0.365, 'three_pt_attempts': 33}
        }
    }

    analyzer = GameAnalyzer(sample_data)
    analyses = analyzer.analyze_all_games()

    print(f"\nAnalyzed {len(analyses)} games:")
    for a in analyses:
        print(f"\n{a.away_team} @ {a.home_team}")
        print(f"  Home score: {a.home_score:.4f} | Away score: {a.away_score:.4f}")
        print(f"  Spread: {a.spread_pick} ({a.spread_confidence:.1f}%)")
        print(f"  Moneyline: {a.moneyline_pick} ({a.moneyline_confidence:.1f}%)")
        print(f"  Total: {a.total_pick} ({a.total_confidence:.1f}%)")
        print(f"  Tank Bowl: {a.factors.get('tank_bowl')}")
        print(f"  Upset Potential: {a.factors.get('upset_potential')}/100 (Alert: {a.factors.get('upset_alert')})")
        print(f"\n  Upset Reasoning:\n  {a.reasoning.get('upset', 'N/A')}")
