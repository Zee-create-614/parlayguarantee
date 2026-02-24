"""
VALUE-BASED Tier Engine for ParlayGuarantee
Generates SHARP picks with value detection, not just favorites
Finds upsets, spread covers, and contrarian value plays

MAJOR UPGRADE: VALUE SCORE MODEL
- Edge vs market detection
- Upset candidate identification  
- Improved spread cover probability
- Pick diversification (no more stacked favorites)
- Confidence tier labeling (LOCK/VALUE/UPSET/LEAN)
"""

import json
import logging
import sys
import time
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import itertools
import random

# Local imports
from reliable_data_fetcher import ReliableDataFetcher
from user_parlay_generator import generate_user_parlays
try:
    from injury_scraper import get_injuries, get_team_injury_impact
    INJURY_AVAILABLE = True
except ImportError:
    INJURY_AVAILABLE = False
    logger.warning("Injury scraper not available")

try:
    from odds_fetcher import OddsFetcher
    ODDS_AVAILABLE = True  
except ImportError:
    ODDS_AVAILABLE = False
    logger.warning("Odds fetcher not available")

try:
    from analyzer import GameAnalyzer, UPSET_WEIGHTS
    ANALYZER_AVAILABLE = True
except ImportError:
    ANALYZER_AVAILABLE = False
    logger.warning("Game analyzer not available")

try:
    from line_movement_tracker import init_db as lm_init_db, fetch_odds_snapshot, store_snapshot, get_line_movement_score
    LINE_MOVEMENT_AVAILABLE = True
except ImportError:
    LINE_MOVEMENT_AVAILABLE = False

# ── Multi-sport engine imports ──
try:
    from mma_engine import MMAEngine
    MMA_AVAILABLE = True
except ImportError:
    MMA_AVAILABLE = False

try:
    from ncaab_engine import NCAABEngine
    NCAAB_AVAILABLE = True
except ImportError:
    NCAAB_AVAILABLE = False

try:
    from tennis_engine import TennisEngine
    TENNIS_AVAILABLE = True
except ImportError:
    TENNIS_AVAILABLE = False

try:
    from golf_engine import GolfEngine
    GOLF_AVAILABLE = True
except ImportError:
    GOLF_AVAILABLE = False

try:
    from boxing_engine import BoxingEngine
    BOXING_AVAILABLE = True
except ImportError:
    BOXING_AVAILABLE = False

logger = logging.getLogger(__name__)

class TierEngine:
    """
    New tier-based engine that generates picks for each tier:
    - single: Best 1-leg picks (moneylines)
    - 2leg through 7leg: Best N-leg parlay combinations
    
    Integrates:
    - Reliable data fetching (NBA.com with retry)
    - Injury adjustments
    - Odds data when available
    - No duplicate games in parlays
    """
    
    def __init__(self):
        self.data_fetcher = ReliableDataFetcher()
        
        # Initialize odds fetcher if available
        if ODDS_AVAILABLE:
            try:
                self.odds_fetcher = OddsFetcher()
                logger.info("✅ Odds fetcher initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize odds fetcher: {e}")
                self.odds_fetcher = None
        else:
            self.odds_fetcher = None
        
        # Tier configurations matching the website
        self.TIERS = {
            'single': {'legs': 1, 'count': 5},      # Top 5 single picks
            '2leg': {'legs': 2, 'count': 5},        # Top 5 2-leg parlays
            '3leg': {'legs': 3, 'count': 3},        # Top 3 3-leg parlays
            '4leg': {'legs': 4, 'count': 3},        # Top 3 4-leg parlays
            '5leg': {'legs': 5, 'count': 2},        # Top 2 5-leg parlays
            '6leg': {'legs': 6, 'count': 2},        # Top 2 6-leg parlays
            '7leg': {'legs': 7, 'count': 1},        # Top 1 7-leg parlay
        }
        
        self.TIER_ORDER = ['single', '2leg', '3leg', '4leg', '5leg', '6leg', '7leg']
        
        # Spread (ATS) tier configurations
        self.SPREAD_TIERS = {
            'spread_single': {'legs': 1, 'count': 5},
            'spread_2leg': {'legs': 2, 'count': 5},
            'spread_3leg': {'legs': 3, 'count': 3},
            'spread_4leg': {'legs': 4, 'count': 2},
            'spread_5leg': {'legs': 5, 'count': 1},
        }
        
        self.SPREAD_TIER_ORDER = ['spread_single', 'spread_2leg', 'spread_3leg', 'spread_4leg', 'spread_5leg']
    
    def _normal_cdf(self, x: float) -> float:
        """Calculate normal cumulative distribution function (CDF) approximation"""
        # Using error function approximation for standard normal CDF
        # CDF(x) = 0.5 * (1 + erf(x / sqrt(2)))
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    def calculate_value_score(self, game: Dict) -> float:
        """
        CORE VALUE MODEL: Calculate value score considering multiple factors
        Higher score = better value pick (not just higher win probability)
        """
        win_prob = game.get('win_prob', 0.5)
        pick_team = game.get('pick', '')
        home_team = game.get('home', '')
        away_team = game.get('away', '')
        spread = game.get('spread', 0)
        
        # Base value starts with win probability
        value_score = win_prob
        
        # 1. EDGE VS MARKET: Compare our model to implied odds from spread
        if spread != 0:
            # Convert spread to implied probability
            # Rough conversion: spread of 7 points ≈ 65% win probability for favorite
            spread_abs = abs(spread)
            if spread < 0:  # Home favored
                market_home_prob = 0.5 + (spread_abs / 25.0)  # Scale factor
                market_away_prob = 1 - market_home_prob
            else:  # Away favored  
                market_away_prob = 0.5 + (spread_abs / 25.0)
                market_home_prob = 1 - market_away_prob
            
            # Clamp market probabilities
            market_home_prob = max(0.25, min(0.85, market_home_prob))
            market_away_prob = max(0.25, min(0.85, market_away_prob))
            
            # Calculate our edge vs market
            if pick_team == home_team:
                market_prob = market_home_prob
            else:
                market_prob = market_away_prob
            
            edge_vs_market = win_prob - market_prob
            
            # Boost value score if we have edge vs market
            if edge_vs_market > 0.05:  # 5%+ edge gets boost
                value_score += edge_vs_market * 2.0  # Double the edge value
            elif edge_vs_market > 0.02:  # 2%+ edge gets smaller boost  
                value_score += edge_vs_market * 1.5
            
            # Store edge for pick labeling
            game['edge_vs_market'] = edge_vs_market
        else:
            game['edge_vs_market'] = 0
        
        # 2. HOME COURT ADVANTAGE WEIGHT: Home teams cover ~52-53% ATS
        is_home_pick = (pick_team == home_team)
        if is_home_pick:
            value_score += 0.03  # Small boost for home picks
        
        # 3. SPREAD SIZE ANALYSIS: Big spreads harder to cover, underdogs have value
        if spread != 0:
            spread_abs = abs(spread)
            if spread_abs >= 10:  # Big spread
                if spread > 0:  # Away team getting big points (value!)
                    if pick_team == away_team:
                        value_score += 0.08  # Big boost for big underdogs
                else:  # Home team laying big points (harder to cover)
                    if pick_team == home_team:
                        value_score -= 0.05  # Slight penalty for big favorites
            elif spread_abs <= 3:  # Pick'em games - toss-ups have value
                value_score += 0.02
        
        # 4. CONTRARIAN VALUE: When line seems too good, fade the public
        if spread != 0:
            spread_abs = abs(spread)
            # Very large spreads (15+) often have public betting one side heavily
            if spread_abs >= 15:
                # If we're taking the underdog, that's contrarian value
                is_underdog_pick = (spread > 0 and pick_team == away_team) or (spread < 0 and pick_team == home_team)
                if is_underdog_pick:
                    value_score += 0.12  # Big contrarian boost
        
        # 5. QUALITY CONTROL: Don't let value score get too crazy
        value_score = max(0.1, min(1.0, value_score))
        
        return value_score
    
    def find_upset_candidates(self, games: List[Dict], injuries: Dict = None, line_movements: Dict = None) -> List[Dict]:
        """
        ENHANCED UPSET DETECTOR: Find games with upset potential using sophisticated factors
        Now integrates: injury impact on favorites, line movement / sharp money signals, real H2H
        Returns list of games sorted by upset value
        """
        upset_candidates = []
        
        for game in games:
            spread = game.get('spread', 0)
            win_prob = game.get('win_prob', 0.5)
            pick_team = game.get('pick', '')
            home_team = game.get('home', '')
            away_team = game.get('away', '')
            
            # Basic upset score calculation
            upset_score = 0
            upset_reasons = []
            upset_factors = {}
            
            # === BASIC FACTORS (Original) ===
            
            # 1. TIGHT SPREADS with momentum (< 5 points)
            if spread != 0 and abs(spread) < 5:
                upset_score += 0.3
                upset_reasons.append(f"Tight spread ({spread:+.1f})")
                upset_factors['tight_spread'] = 0.3
            
            # 2. HOME UNDERDOGS (historically profitable ATS)
            if spread > 0:  # Away team favored, home getting points
                upset_score += 0.4
                upset_reasons.append("Home underdog")
                upset_factors['home_underdog'] = 0.4
                if pick_team == home_team:
                    upset_score += 0.2  # Extra if our model likes home dog
                    upset_factors['model_likes_home_dog'] = 0.2
            
            # 3. BIG UNDERDOGS with value (getting 7+ points)
            if spread != 0:
                spread_abs = abs(spread)
                if spread_abs >= 7:
                    is_underdog_pick = (spread > 0 and pick_team == home_team) or (spread < 0 and pick_team == away_team)
                    if is_underdog_pick:
                        upset_score += 0.5
                        upset_reasons.append(f"Big dog +{spread_abs:.1f}")
                        upset_factors['big_underdog'] = 0.5
            
            # 4. MODEL DISAGREEMENT: When our win_prob doesn't match spread
            if spread != 0:
                spread_abs = abs(spread)
                expected_favorite_prob = 0.5 + (spread_abs / 25.0)
                
                # If we think underdog has better chance than market suggests
                if spread > 0:  # Away favored
                    our_home_prob = win_prob if pick_team == home_team else (1 - win_prob)
                    market_home_prob = 1 - expected_favorite_prob
                    if our_home_prob > market_home_prob + 0.1:  # 10%+ better
                        upset_score += 0.4
                        upset_reasons.append("Model likes underdog")
                        upset_factors['model_disagreement'] = 0.4
                else:  # Home favored
                    our_away_prob = win_prob if pick_team == away_team else (1 - win_prob)
                    market_away_prob = 1 - expected_favorite_prob
                    if our_away_prob > market_away_prob + 0.1:
                        upset_score += 0.4
                        upset_reasons.append("Model likes road dog")
                        upset_factors['model_disagreement'] = 0.4
            
            # === ADVANCED FACTORS from analyzer.py ===
            if ANALYZER_AVAILABLE:
                # Calculate advanced upset factors
                advanced_factors = self._calculate_advanced_upset_factors(game)
                
                for factor_name, factor_value in advanced_factors.items():
                    if factor_name in UPSET_WEIGHTS:
                        weight = UPSET_WEIGHTS[factor_name]
                        contribution = factor_value * weight
                        upset_score += contribution
                        upset_factors[factor_name] = contribution
                        
                        # Add to reasons if significant
                        if contribution > 0.05:
                            upset_reasons.append(f"{factor_name.replace('_', ' ').title()}: +{contribution:.2f}")
            
            # === INJURY FACTOR: Star players OUT on favorite boosts upset potential ===
            if injuries and INJURY_AVAILABLE:
                try:
                    from injury_scraper import STAR_IMPACT, STATUS_MULTIPLIER
                    by_team = injuries.get('by_team', {})
                    spread = game.get('spread', 0)
                    
                    # Determine favorite and dog
                    if spread > 0:
                        favorite_team = away_team
                        dog_team = home_team
                    elif spread < 0:
                        favorite_team = home_team
                        dog_team = away_team
                    else:
                        favorite_team = dog_team = None
                    
                    if favorite_team:
                        # Check favorite's injuries
                        fav_injuries = by_team.get(favorite_team, [])
                        if not fav_injuries:
                            # Fuzzy match
                            for t, injs in by_team.items():
                                if favorite_team.lower() in t.lower() or t.lower() in favorite_team.lower():
                                    fav_injuries = injs
                                    break
                        
                        for inj in fav_injuries:
                            player = inj['player']
                            status = inj['status']
                            if player in STAR_IMPACT and status in ('Out', 'Doubtful'):
                                impact_rating = STAR_IMPACT[player]
                                status_mult = STATUS_MULTIPLIER.get(status, 0.5)
                                # Scale: 0.95 star OUT → +0.57, 0.72 star OUT → +0.43
                                boost = impact_rating * status_mult * 0.6
                                boost = min(boost, 0.6)
                                upset_score += boost
                                upset_reasons.append(f"⚠️ {player} {status} ({favorite_team} fav)")
                                upset_factors['injury_fav_star_out'] = upset_factors.get('injury_fav_star_out', 0) + boost
                        
                        # Check dog's injuries (reduce upset score)
                        dog_injuries = by_team.get(dog_team, [])
                        if not dog_injuries:
                            for t, injs in by_team.items():
                                if dog_team and (dog_team.lower() in t.lower() or t.lower() in dog_team.lower()):
                                    dog_injuries = injs
                                    break
                        
                        for inj in dog_injuries:
                            player = inj['player']
                            status = inj['status']
                            if player in STAR_IMPACT and status in ('Out', 'Doubtful'):
                                impact_rating = STAR_IMPACT[player]
                                status_mult = STATUS_MULTIPLIER.get(status, 0.5)
                                penalty = impact_rating * status_mult * 0.3
                                upset_score -= penalty
                                upset_reasons.append(f"📉 {player} {status} ({dog_team} dog)")
                                upset_factors['injury_dog_star_out'] = upset_factors.get('injury_dog_star_out', 0) - penalty
                except Exception as e:
                    logger.debug(f"Injury factor calc failed: {e}")

            # === LINE MOVEMENT FACTOR: Sharp money signals ===
            if LINE_MOVEMENT_AVAILABLE:
                try:
                    lm = get_line_movement_score(
                        home_team, away_team,
                        game.get('spread', 0),
                        game.get('game_date', None)
                    )
                    lm_score = lm.get('score', 0)
                    if lm_score != 0:
                        upset_score += lm_score
                        dog_move = lm.get('dog_movement_pts', 0)
                        if lm_score > 0:
                            upset_reasons.append(f"📊 Line moved {abs(dog_move):.1f}pts toward dog (sharp $)")
                        else:
                            upset_reasons.append(f"📊 Line moved toward favorite")
                        upset_factors['line_movement'] = lm_score
                    game['line_movement'] = lm
                except Exception as e:
                    logger.debug(f"Line movement calc failed: {e}")

            # Only include games with meaningful upset potential
            if upset_score >= 0.3:
                game['upset_score'] = upset_score
                game['upset_reasons'] = upset_reasons
                game['upset_factors'] = upset_factors
                upset_candidates.append(game)
        
        # Sort by upset score descending
        upset_candidates.sort(key=lambda x: x.get('upset_score', 0), reverse=True)
        return upset_candidates
    
    def _calculate_advanced_upset_factors(self, game: Dict) -> Dict[str, float]:
        """Calculate advanced upset factors from analyzer.py logic"""
        factors = {}
        
        home_team = game.get('home', '')
        away_team = game.get('away', '')
        pick_team = game.get('pick', '')
        
        try:
            # Get team stats for calculations
            home_stats = self.data_fetcher.stats_cache.get(home_team, {})
            away_stats = self.data_fetcher.stats_cache.get(away_team, {})
            
            # 1. H2H Factor - fetch real season series from ESPN
            factors['h2h'] = self._fetch_h2h_factor(home_team, away_team, pick_team)
            
            # 2. Momentum Factor - based on win percentage (proxy for form)
            home_wp = home_stats.get('win_pct', 0.5)
            away_wp = away_stats.get('win_pct', 0.5)
            
            if pick_team == home_team and home_wp > away_wp:
                factors['momentum'] = min(1.0, (home_wp - away_wp) * 2)
            elif pick_team == away_team and away_wp > home_wp:
                factors['momentum'] = min(1.0, (away_wp - home_wp) * 2)
            else:
                factors['momentum'] = 0.2  # Lower momentum if picking worse record team
            
            # 3. Home Record Factor — use real ESPN home/road splits
            home_rec_str = home_stats.get('home_record', '')
            away_road_str = away_stats.get('road_record', '')
            try:
                h_parts = home_rec_str.split('-')
                home_home_wpct = int(h_parts[0]) / max(1, int(h_parts[0]) + int(h_parts[1])) if len(h_parts) == 2 else 0.5
            except (ValueError, IndexError):
                home_home_wpct = 0.5
            try:
                a_parts = away_road_str.split('-')
                away_road_wpct = int(a_parts[0]) / max(1, int(a_parts[0]) + int(a_parts[1])) if len(a_parts) == 2 else 0.5
            except (ValueError, IndexError):
                away_road_wpct = 0.5
            
            # Home dog that's good at home = upset potential
            spread = game.get('spread', 0)
            if spread > 0 and home_home_wpct > 0.5:
                factors['home_record'] = min(1.0, home_home_wpct + 0.2)
            elif spread < 0 and away_road_wpct > 0.5:
                factors['home_record'] = min(1.0, away_road_wpct + 0.1)
            else:
                factors['home_record'] = 0.3
            
            # 4. Star Matchup Factor - based on PPG differential (proxy for star power)
            home_ppg = home_stats.get('ppg', 110)
            away_ppg = away_stats.get('ppg', 110)
            
            ppg_diff = abs(home_ppg - away_ppg)
            if ppg_diff > 10:  # Significant offensive difference
                factors['star_matchup'] = min(1.0, ppg_diff / 20)
            else:
                factors['star_matchup'] = 0.3
            
            # 5. Streak Factor — use real ESPN streak data
            home_streak = home_stats.get('streak', 0)
            away_streak = away_stats.get('streak', 0)
            # Positive = win streak, negative = lose streak
            # Underdog on a hot streak = upset danger
            spread = game.get('spread', 0)
            if spread > 0:  # Home is underdog
                if home_streak > 0:
                    factors['streak'] = min(1.0, 0.5 + home_streak * 0.1)
                elif away_streak < 0:  # Favorite on a losing streak
                    factors['streak'] = min(1.0, 0.5 + abs(away_streak) * 0.08)
                else:
                    factors['streak'] = 0.3
            elif spread < 0:  # Away is underdog
                if away_streak > 0:
                    factors['streak'] = min(1.0, 0.5 + away_streak * 0.1)
                elif home_streak < 0:
                    factors['streak'] = min(1.0, 0.5 + abs(home_streak) * 0.08)
                else:
                    factors['streak'] = 0.3
            else:
                factors['streak'] = 0.5
            
            # 6. Last-10 / Clutch Factor — use L10 record from ESPN
            home_l10 = home_stats.get('last_ten', '')
            away_l10 = away_stats.get('last_ten', '')
            try:
                home_l10_wins = int(home_l10.split('-')[0]) if home_l10 else 5
                away_l10_wins = int(away_l10.split('-')[0]) if away_l10 else 5
            except (ValueError, IndexError):
                home_l10_wins = 5
                away_l10_wins = 5
            
            # Underdog hot in L10 = upset danger
            if spread > 0:  # Home dog
                factors['clutch'] = min(1.0, home_l10_wins / 10.0 + 0.1)
            elif spread < 0:  # Away dog
                factors['clutch'] = min(1.0, away_l10_wins / 10.0 + 0.1)
            else:
                factors['clutch'] = 0.5
            
            # 7. 3PT Matchup Factor — use PPG differential as proxy
            factors['three_pt_matchup'] = 0.5  # Would need shooting stats for real calc
            
            # 8. Post-ASB Factor - check if recent games after all-star break
            from datetime import datetime
            asb_end = datetime(2026, 2, 16)  # All-Star Break end
            current_date = datetime.now()
            
            if current_date > asb_end and (current_date - asb_end).days < 10:
                factors['post_asb'] = 0.8  # Higher upset potential post-ASB
            else:
                factors['post_asb'] = 0.3
            
        except Exception as e:
            logger.debug(f"Error calculating advanced upset factors: {e}")
            # Return neutral factors if calculation fails
            for factor_name in UPSET_WEIGHTS.keys():
                factors[factor_name] = 0.5
        
        return factors
    
    def _fetch_h2h_factor(self, home_team: str, away_team: str, pick_team: str) -> float:
        """Fetch real H2H season series from ESPN and return a factor 0-1."""
        if not hasattr(self, '_h2h_cache'):
            self._h2h_cache = {}
        
        cache_key = f"{home_team}|{away_team}"
        if cache_key in self._h2h_cache:
            return self._h2h_cache[cache_key]
        
        try:
            import requests as _req
            
            # ESPN team ID lookup — build from known mapping
            _ESPN_SLUG = {
                'Atlanta Hawks': 'atl', 'Boston Celtics': 'bos', 'Brooklyn Nets': 'bkn',
                'Charlotte Hornets': 'cha', 'Chicago Bulls': 'chi', 'Cleveland Cavaliers': 'cle',
                'Dallas Mavericks': 'dal', 'Denver Nuggets': 'den', 'Detroit Pistons': 'det',
                'Golden State Warriors': 'gs', 'Houston Rockets': 'hou', 'Indiana Pacers': 'ind',
                'LA Clippers': 'lac', 'Los Angeles Clippers': 'lac', 'Los Angeles Lakers': 'lal',
                'Memphis Grizzlies': 'mem', 'Miami Heat': 'mia', 'Milwaukee Bucks': 'mil',
                'Minnesota Timberwolves': 'min', 'New Orleans Pelicans': 'no', 'New York Knicks': 'ny',
                'Oklahoma City Thunder': 'okc', 'Orlando Magic': 'orl', 'Philadelphia 76ers': 'phi',
                'Phoenix Suns': 'phx', 'Portland Trail Blazers': 'por', 'Sacramento Kings': 'sac',
                'San Antonio Spurs': 'sa', 'Toronto Raptors': 'tor', 'Utah Jazz': 'utah',
                'Washington Wizards': 'wsh',
            }
            _ESPN_ID = {
                'Atlanta Hawks': 1, 'Boston Celtics': 2, 'Brooklyn Nets': 17, 'Charlotte Hornets': 30,
                'Chicago Bulls': 4, 'Cleveland Cavaliers': 5, 'Dallas Mavericks': 6, 'Denver Nuggets': 7,
                'Detroit Pistons': 8, 'Golden State Warriors': 9, 'Houston Rockets': 10, 'Indiana Pacers': 11,
                'LA Clippers': 12, 'Los Angeles Clippers': 12, 'Los Angeles Lakers': 13, 'Memphis Grizzlies': 29,
                'Miami Heat': 14, 'Milwaukee Bucks': 15, 'Minnesota Timberwolves': 16, 'New Orleans Pelicans': 3,
                'New York Knicks': 18, 'Oklahoma City Thunder': 25, 'Orlando Magic': 19, 'Philadelphia 76ers': 20,
                'Phoenix Suns': 21, 'Portland Trail Blazers': 22, 'Sacramento Kings': 23, 'San Antonio Spurs': 24,
                'Toronto Raptors': 28, 'Utah Jazz': 26, 'Washington Wizards': 27,
            }
            
            team_id = _ESPN_ID.get(pick_team)
            if not team_id:
                self._h2h_cache[cache_key] = 0.5
                return 0.5
            
            # Fetch recent schedule/results for pick_team and look for matchups against opponent
            opponent = away_team if pick_team == home_team else home_team
            opp_id = _ESPN_ID.get(opponent)
            
            # ESPN schedule API
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/schedule"
            resp = _req.get(url, timeout=10)
            if resp.status_code != 200:
                self._h2h_cache[cache_key] = 0.5
                return 0.5
            
            data = resp.json()
            events = data.get('events', [])
            
            wins_vs_opp = 0
            losses_vs_opp = 0
            
            for event in events:
                # Check if opponent is in this game
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                if len(competitors) < 2:
                    continue
                
                teams_in_game = {c.get('team', {}).get('displayName', ''): c for c in competitors}
                
                if opponent not in teams_in_game and not any(opponent.split()[-1] in t for t in teams_in_game):
                    continue
                
                # This is a matchup against opponent — check result
                status_type = event.get('competitions', [{}])[0].get('status', {}).get('type', {}).get('name', '')
                if status_type != 'STATUS_FINAL':
                    continue
                
                # Find our team's result
                for c in competitors:
                    team_name = c.get('team', {}).get('displayName', '')
                    if team_name == pick_team or pick_team.split()[-1] in team_name:
                        winner = c.get('winner', False)
                        if winner:
                            wins_vs_opp += 1
                        else:
                            losses_vs_opp += 1
                        break
            
            total = wins_vs_opp + losses_vs_opp
            if total == 0:
                factor = 0.5
            else:
                h2h_pct = wins_vs_opp / total
                # Scale: 0% wins → 0.1, 50% → 0.5, 100% → 0.9
                factor = 0.1 + h2h_pct * 0.8
            
            self._h2h_cache[cache_key] = factor
            logger.debug(f"H2H {pick_team} vs {opponent}: {wins_vs_opp}-{losses_vs_opp} → factor={factor:.2f}")
            return factor
            
        except Exception as e:
            logger.debug(f"H2H fetch failed for {home_team} vs {away_team}: {e}")
            self._h2h_cache[cache_key] = 0.5
            return 0.5

    def _calculate_cover_prob_improved(self, win_prob: float, spread: float, pick_team: str, home_team: str, away_team: str) -> float:
        """
        IMPROVED SPREAD COVER PROBABILITY using normal distribution
        Much better than the crude linear formula
        """
        if spread == 0:
            return 0.5  # No spread = no cover concept
        
        # 1. Estimate margin of victory from win probability
        # If team has 70% win prob, they win by ~5 points on average
        # Formula: expected_margin = (win_prob - 0.5) * 25 (calibrated for NBA)
        if pick_team == home_team:
            # Home team pick
            expected_margin = (win_prob - 0.5) * 25
        else:
            # Away team pick - flip the sign
            expected_margin = (win_prob - 0.5) * -25
        
        # 2. NBA game margin standard deviation ≈ 12 points
        margin_std = 12.0
        
        # 3. Calculate cover probability using normal distribution
        # For home spread: positive spread means home getting points, negative means home laying points
        # We need P(actual_margin > spread_line) for the team to cover
        
        if pick_team == home_team:
            # Home team covering: P(home_margin > spread)
            # If spread is -7, home needs to win by >7, so P(margin > -7)
            # If spread is +3, home needs to lose by <3 (or win), so P(margin > 3) 
            cover_z = (expected_margin - spread) / margin_std
        else:
            # Away team covering: P(away_margin > away_spread)
            # Away spread is negative of home spread
            away_spread = -spread
            cover_z = (expected_margin - away_spread) / margin_std
        
        # 4. Use normal CDF to get cover probability
        cover_prob = self._normal_cdf(cover_z)
        
        # 5. Constrain between reasonable bounds
        cover_prob = max(0.15, min(0.90, cover_prob))
        
        return cover_prob
    
    def _assign_pick_confidence_tier(self, game: Dict) -> str:
        """
        CONFIDENCE TIERS: Label each pick with confidence level
        LOCK (>75% our confidence AND market agrees)  
        VALUE (our edge vs market > 5%)
        UPSET (underdog we think wins or covers)
        LEAN (slight edge, lower confidence)
        """
        win_prob = game.get('win_prob', 0.5)
        value_score = game.get('value_score', win_prob)
        edge_vs_market = game.get('edge_vs_market', 0)
        upset_score = game.get('upset_score', 0)
        spread = game.get('spread', 0)
        pick_team = game.get('pick', '')
        home_team = game.get('home', '')
        away_team = game.get('away', '')
        
        # LOCK: High confidence + market agreement
        if win_prob >= 0.75 and edge_vs_market >= -0.05:  # Model confident, market agrees
            return "LOCK"
        
        # VALUE: Significant edge vs market
        if edge_vs_market > 0.05:  # 5%+ edge
            return "VALUE"
        
        # UPSET: Underdog with upset potential
        if upset_score > 0:
            # Check if we're actually picking underdog
            is_underdog_pick = False
            if spread > 0:  # Away favored
                is_underdog_pick = (pick_team == home_team)
            elif spread < 0:  # Home favored  
                is_underdog_pick = (pick_team == away_team)
            
            if is_underdog_pick or upset_score >= 0.5:
                return "UPSET"
        
        # LEAN: Everything else (slight edges, lower confidence)
        return "LEAN"

    def initialize_odds_fetcher(self, api_key: str = "f3c9f91dc369f56dea1b523d3071e1f1"):
        """Initialize odds fetcher if API key is available"""
        if not ODDS_AVAILABLE:
            logger.warning("Odds fetcher not available - skipping odds integration")
            return
            
        try:
            self.odds_fetcher = OddsFetcher(api_key)
            logger.info("Odds fetcher initialized")
        except Exception as e:
            logger.warning(f"Could not initialize odds fetcher: {e}")
            self.odds_fetcher = None
    
    def fetch_and_analyze_games(self, target_date: date) -> List[Dict]:
        """
        Fetch games for target date and analyze them with probabilities
        Integrates injury data and odds data when available
        """
        logger.info(f"Fetching games for {target_date}")
        
        # Fetch basic game data
        games = self.data_fetcher.fetch_games_for_date(target_date)
        
        if not games:
            logger.warning(f"No games found for {target_date}")
            return []
        
        # Fetch team stats for probability calculations
        logger.info("Fetching team statistics...")
        team_stats = self.data_fetcher.fetch_team_stats()
        self.data_fetcher.stats_cache = team_stats
        
        # Fetch injury data
        logger.info("Fetching injury data...")
        injuries = {}
        if INJURY_AVAILABLE:
            try:
                injuries = get_injuries(force_refresh=True)
                injury_count = sum(len(team_injs) for team_injs in injuries.get('by_team', {}).values())
                logger.info(f"Found {injury_count} injury reports across teams")
            except Exception as e:
                logger.warning(f"Could not fetch injury data: {e}")
                injuries = {}
        else:
            logger.warning("Injury scraper not available")
        
        # Analyze each game
        analyzed_games = []
        for game in games:
            # Calculate base probability
            winner, prob = self.data_fetcher.calculate_win_probability(
                game['home_team'], 
                game['away_team']
            )
            
            # Apply injury adjustments
            adjusted_prob = self._apply_injury_adjustments(
                game['home_team'], 
                game['away_team'], 
                winner, 
                prob, 
                injuries
            )
            
            # Create analyzed game dict
            analyzed_game = {
                'home': game['home_team'],
                'away': game['away_team'],
                'pick': winner,
                'win_prob': adjusted_prob,
                'game_date': game['game_date'],
                'game_time': game['game_time'],
                'game_id': game['game_id'],
                'game_status': game['game_status'],
                'original_prob': prob,  # Keep original for reference
                'spread': game.get('spread', self._estimate_spread_from_probability(adjusted_prob)),
            }
            
            analyzed_games.append(analyzed_game)
        
        # Apply odds adjustments if available
        if self.odds_fetcher:
            try:
                logger.info("Applying odds-based adjustments...")
                analyzed_games = self._apply_odds_adjustments(analyzed_games, target_date)
            except Exception as e:
                logger.warning(f"Could not apply odds adjustments: {e}")
        
        # ⚡ APPLY VALUE SCORING - This is where the magic happens!
        logger.info("🔥 Calculating value scores for each game...")
        for game in analyzed_games:
            # Calculate value score (enhanced win probability)
            value_score = self.calculate_value_score(game)
            game['value_score'] = value_score
            
            # Assign confidence tier label
            pick_label = self._assign_pick_confidence_tier(game)
            game['pick_label'] = pick_label
        
        # Find upset candidates and tag ALL games with upset_potential + tank_bowl
        # Take a line movement snapshot before upset analysis
        if LINE_MOVEMENT_AVAILABLE:
            try:
                lm_init_db()
                lm_games = fetch_odds_snapshot("nba")
                if lm_games:
                    store_snapshot(lm_games, "nba")
                    logger.info(f"📊 Stored line movement snapshot ({len(lm_games)} games)")
            except Exception as e:
                logger.warning(f"Line movement snapshot failed: {e}")

        upset_candidates = self.find_upset_candidates(analyzed_games, injuries=injuries)
        logger.info(f"💎 Found {len(upset_candidates)} upset candidates")
        
        # Ensure every game has upset_potential and tank_bowl flags
        # CRITICAL: When upset composite is high, FLIP the pick to the underdog
        for game in analyzed_games:
            if 'upset_score' not in game:
                game['upset_score'] = 0.0
                game['upset_reasons'] = []
            game['upset_potential'] = round(game['upset_score'], 3)
            
            # Tank bowl detection: both teams below TANK_THRESHOLD win%
            home_stats = self.data_fetcher.stats_cache.get(game['home'], {}) if self.data_fetcher.stats_cache else {}
            away_stats = self.data_fetcher.stats_cache.get(game['away'], {}) if self.data_fetcher.stats_cache else {}
            home_wpct = home_stats.get('win_pct', 0.5) if home_stats else 0.5
            away_wpct = away_stats.get('win_pct', 0.5) if away_stats else 0.5
            game['tank_bowl'] = home_wpct < 0.35 and away_wpct < 0.35
            
            # 🔥 UPSET FLIP: If upset composite is strong (>= 0.8) AND the game is close-ish,
            # flip the pick to the underdog. This is the whole point of the upset composite.
            spread = game.get('spread', 0)
            upset_score = game.get('upset_score', 0)
            if upset_score >= 0.8 and abs(spread) <= 10:
                # Determine the underdog (home team getting points = home dog)
                if spread > 0:
                    underdog = game['home']  # Home team is getting points
                elif spread < 0:
                    underdog = game['away']  # Away team is getting points
                else:
                    underdog = None
                
                if underdog and game['pick'] != underdog:
                    old_pick = game['pick']
                    game['pick'] = underdog
                    game['win_prob'] = 1 - game['win_prob']  # Flip probability
                    game['upset_flip'] = True
                    game['original_pick'] = old_pick
                    logger.info(f"🔄 UPSET FLIP: {old_pick} → {underdog} (upset={upset_score:.2f}, spread={spread:+.1f})")
                    
                    # Recalculate value score with flipped pick
                    game['value_score'] = self.calculate_value_score(game)
                    game['pick_label'] = 'UPSET'
        
        # Sort by VALUE SCORE (not just win probability!)
        analyzed_games.sort(key=lambda x: x.get('value_score', x['win_prob']), reverse=True)
        
        # 🎯 LOG VALUE ANALYSIS for key games
        for i, game in enumerate(analyzed_games[:5]):  # Show top 5 value picks
            logger.info(f"🔥 VALUE PICK #{i+1}: {game['away']} @ {game['home']}")
            logger.info(f"   Win Prob: {game['win_prob']:.3f} | Value Score: {game.get('value_score', 0):.3f}")
            logger.info(f"   Edge vs Market: {game.get('edge_vs_market', 0):+.3f} | Label: {game.get('pick_label', 'N/A')}")
            if game.get('spread', 0) != 0:
                logger.info(f"   Spread: {game.get('spread', 0):+.1f} | Pick: {game['pick']}")
        
        logger.info(f"Analyzed {len(analyzed_games)} games with VALUE SCORING")
        return analyzed_games
    
    def _apply_injury_adjustments(self, home_team: str, away_team: str, 
                                 winner: str, prob: float, injuries: Dict) -> float:
        """Apply injury-based probability adjustments"""
        if not INJURY_AVAILABLE or not injuries or 'by_team' not in injuries:
            return prob
            
        adjusted_prob = prob
        
        try:
            # Use the injury scraper's impact calculation
            winner_impact = get_team_injury_impact(winner, injuries)
            
            if winner_impact > 0.05:  # Significant injury impact (>5%)
                # Reduce probability based on injury impact
                adjustment = min(winner_impact, 0.15)  # Cap at 15% reduction
                adjusted_prob = max(prob - adjustment, 0.25)  # Don't go below 25%
                logger.debug(f"Injury adjustment for {winner}: {prob:.3f} -> {adjusted_prob:.3f} (impact: {winner_impact:.3f})")
        
        except Exception as e:
            logger.debug(f"Error applying injury adjustments: {e}")
        
        return adjusted_prob
    
    def _apply_odds_adjustments(self, games: List[Dict], target_date: date) -> List[Dict]:
        """Apply odds-based adjustments to probabilities"""
        # Skip if odds fetcher not available
        if not self.odds_fetcher:
            logger.debug("Odds fetcher not available, skipping odds adjustments")
            return games
            
        try:
            # Fetch current odds for the date
            odds_data = self.odds_fetcher.fetch_daily_odds(target_date)
            
            for game in games:
                home_team = game['home']
                away_team = game['away']
                
                # Try to find matching odds
                matching_odds = None
                for odds_game in odds_data:
                    if (self._teams_match(odds_game.get('home_team', ''), home_team) and 
                        self._teams_match(odds_game.get('away_team', ''), away_team)):
                        matching_odds = odds_game
                        break
                
                if matching_odds:
                    # Use odds to validate/adjust probabilities
                    market_prob = self._odds_to_probability(matching_odds)
                    if market_prob:
                        # Blend our probability with market probability (70% ours, 30% market)
                        blended_prob = 0.7 * game['win_prob'] + 0.3 * market_prob
                        game['market_prob'] = market_prob
                        game['win_prob'] = blended_prob
            
            return games
            
        except Exception as e:
            logger.error(f"Error applying odds adjustments: {e}")
            return games
    
    def _teams_match(self, team1: str, team2: str) -> bool:
        """Check if two team names refer to the same team"""
        # Simple matching - could be enhanced
        return team1.lower().replace(' ', '') == team2.lower().replace(' ', '')
    
    def _odds_to_probability(self, odds_data: Dict) -> Optional[float]:
        """Convert odds data to implied probability for the favored team"""
        # This would need to be implemented based on odds_fetcher output format
        # For now, return None to skip odds blending
        return None
    
    def generate_single_picks(self, games: List[Dict], count: int = 5) -> List[Dict]:
        """🔥 Generate VALUE-BASED single picks - not just highest probability!"""
        if len(games) < count:
            logger.warning(f"Only {len(games)} games available for {count} single picks")
            count = len(games)
        
        picks = []
        for i in range(count):
            game = games[i]
            pick = {
                'pick_number': i + 1,
                'type': 'single',
                'legs': 1,
                'games': [game],
                'combined_prob': game['win_prob'],
                'value_score': game.get('value_score', game['win_prob']),
                'edge_vs_market': game.get('edge_vs_market', 0),
                'pick_label': game.get('pick_label', '📊 LEAN'),
                'implied_payout': self._calculate_payout(game['win_prob']),
                'earliest_game_time': game['game_time']
            }
            picks.append(pick)
        
        return picks
    
    def generate_parlay_picks(self, games: List[Dict], legs: int, count: int) -> List[Dict]:
        """
        🔥 DIVERSIFIED Parlay Generation - No more stacked favorites!
        Creates balanced parlays with mix of LOCKS, VALUE, and UPSET picks
        """
        if len(games) < legs:
            logger.warning(f"Not enough games ({len(games)}) for {legs}-leg parlays")
            return []
        
        # ⚡ PICK DIVERSIFICATION ALGORITHM
        # For 3+ leg parlays, ensure mix of pick types
        if legs >= 3:
            return self._generate_diversified_parlays(games, legs, count)
        
        # For 2-leg parlays, use regular combination but with value scoring
        all_combinations = list(itertools.combinations(games, legs))
        
        if not all_combinations:
            return []
        
        # Score each combination by COMBINED VALUE SCORE
        scored_combinations = []
        for combo in all_combinations:
            combined_prob = 1.0
            combined_value_score = 1.0
            pick_labels = []
            
            for game in combo:
                combined_prob *= game['win_prob']
                combined_value_score *= game.get('value_score', game['win_prob'])
                pick_labels.append(game.get('pick_label', '📊 LEAN'))
            
            # Get earliest game time for scheduling
            game_times = [g['game_time'] for g in combo if g['game_time']]
            earliest_time = min(game_times) if game_times else ''
            
            scored_combinations.append({
                'games': list(combo),
                'combined_prob': combined_prob,
                'combined_value_score': combined_value_score,
                'pick_labels': pick_labels,
                'earliest_time': earliest_time
            })
        
        # Sort by combined VALUE SCORE (not just probability!)
        scored_combinations.sort(key=lambda x: x['combined_value_score'], reverse=True)
        
        # Take top combinations
        top_combinations = scored_combinations[:count]
        
        # Format as picks
        picks = []
        for i, combo in enumerate(top_combinations):
            pick = {
                'pick_number': i + 1,
                'type': 'parlay',
                'legs': legs,
                'games': combo['games'],
                'combined_prob': round(combo['combined_prob'], 4),
                'combined_value_score': round(combo['combined_value_score'], 4),
                'pick_labels': combo['pick_labels'],
                'implied_payout': self._calculate_payout(combo['combined_prob']),
                'earliest_game_time': combo['earliest_time']
            }
            picks.append(pick)
        
        return picks
    
    def _generate_diversified_parlays(self, games: List[Dict], legs: int, count: int) -> List[Dict]:
        """
        🎯 ADVANCED DIVERSIFICATION: Create balanced parlays for 3+ legs
        Each parlay gets: 1-2 LOCKS + 1-2 VALUE + 0-1 UPSET picks
        """
        # Categorize games by pick label
        locks = [g for g in games if g.get('pick_label', '').startswith('LOCK')]
        values = [g for g in games if g.get('pick_label', '').startswith('VALUE')]
        upsets = [g for g in games if g.get('pick_label', '').startswith('UPSET')]
        leans = [g for g in games if g.get('pick_label', '').startswith('LEAN')]
        
        logger.info(f"🎯 Diversified parlay pool: {len(locks)} LOCKS, {len(values)} VALUE, {len(upsets)} UPSETS, {len(leans)} LEANS")
        
        diversified_combos = []
        max_attempts = 1000  # Prevent infinite loops
        attempts = 0
        
        while len(diversified_combos) < count * 3 and attempts < max_attempts:  # Generate more than needed
            attempts += 1
            combo_games = []
            used_games = set()
            
            # TEMPLATE: Mix of pick types for this parlay
            if legs >= 5:
                # 5+ legs: 2 locks, 2 value, 1 upset/lean
                target_locks = 2
                target_values = 2
                target_others = legs - 4
            elif legs >= 4:
                # 4 legs: 1-2 locks, 1-2 value, remainder others
                target_locks = 1
                target_values = 2
                target_others = legs - 3
            else:  # legs == 3
                # 3 legs: 1 lock, 1 value, 1 other
                target_locks = 1
                target_values = 1
                target_others = 1
            
            # Add LOCKS
            available_locks = [g for g in locks if g['game_id'] not in used_games]
            for _ in range(min(target_locks, len(available_locks))):
                if available_locks:
                    game = random.choice(available_locks)
                    combo_games.append(game)
                    used_games.add(game['game_id'])
                    available_locks = [g for g in available_locks if g['game_id'] != game['game_id']]
            
            # Add VALUE picks
            available_values = [g for g in values if g['game_id'] not in used_games]
            for _ in range(min(target_values, len(available_values))):
                if available_values:
                    game = random.choice(available_values)
                    combo_games.append(game)
                    used_games.add(game['game_id'])
                    available_values = [g for g in available_values if g['game_id'] != game['game_id']]
            
            # Fill remainder with UPSETS (preferred) or LEANS
            available_others = [g for g in (upsets + leans) if g['game_id'] not in used_games]
            while len(combo_games) < legs and available_others:
                game = random.choice(available_others)
                combo_games.append(game)
                used_games.add(game['game_id'])
                available_others = [g for g in available_others if g['game_id'] != game['game_id']]
            
            # If we couldn't fill the combo, try with any remaining games
            if len(combo_games) < legs:
                available_any = [g for g in games if g['game_id'] not in used_games]
                while len(combo_games) < legs and available_any:
                    game = random.choice(available_any)
                    combo_games.append(game)
                    used_games.add(game['game_id'])
                    available_any = [g for g in available_any if g['game_id'] != game['game_id']]
            
            # Only add if we have full combo
            if len(combo_games) == legs:
                # Calculate combined scores
                combined_prob = 1.0
                combined_value_score = 1.0
                pick_labels = []
                
                for game in combo_games:
                    combined_prob *= game['win_prob']
                    combined_value_score *= game.get('value_score', game['win_prob'])
                    pick_labels.append(game.get('pick_label', '📊 LEAN'))
                
                # Get earliest game time
                game_times = [g['game_time'] for g in combo_games if g['game_time']]
                earliest_time = min(game_times) if game_times else ''
                
                # Check for duplicates (same games in different order)
                combo_id = tuple(sorted(g['game_id'] for g in combo_games))
                if combo_id not in [tuple(sorted(c['combo_id'])) for c in diversified_combos]:
                    diversified_combos.append({
                        'games': combo_games,
                        'combined_prob': combined_prob,
                        'combined_value_score': combined_value_score,
                        'pick_labels': pick_labels,
                        'earliest_time': earliest_time,
                        'combo_id': list(combo_id)
                    })
        
        # Sort by combined value score
        diversified_combos.sort(key=lambda x: x['combined_value_score'], reverse=True)
        
        # Take top combinations
        top_combinations = diversified_combos[:count]
        
        # Format as picks
        picks = []
        for i, combo in enumerate(top_combinations):
            pick = {
                'pick_number': i + 1,
                'type': 'parlay',
                'legs': legs,
                'games': combo['games'],
                'combined_prob': round(combo['combined_prob'], 4),
                'combined_value_score': round(combo['combined_value_score'], 4),
                'pick_labels': combo['pick_labels'],
                'diversified': True,  # Flag to show this used diversification
                'implied_payout': self._calculate_payout(combo['combined_prob']),
                'earliest_game_time': combo['earliest_time']
            }
            picks.append(pick)
        
        logger.info(f"🎯 Generated {len(picks)} diversified parlays")
        return picks
    
    def _calculate_payout(self, probability: float) -> str:
        """Calculate implied payout multiplier from probability"""
        if probability <= 0:
            return "1.0x"
        
        payout_mult = 1.0 / probability
        return f"{payout_mult:.1f}x"
    
    def _calculate_cover_prob(self, win_prob: float, spread: float, pick_team: str = "", home_team: str = "", away_team: str = "") -> float:
        """
        LEGACY METHOD: Keeping for compatibility
        Use _calculate_cover_prob_improved for better accuracy
        """
        if pick_team and home_team and away_team:
            # Use improved method if team info available
            return self._calculate_cover_prob_improved(win_prob, spread, pick_team, home_team, away_team)
        
        # Fallback to old method
        abs_spread = abs(spread)
        if spread < 0:
            # Favorite: needs to win by more than the spread
            cover_prob = win_prob * (1 - abs_spread / 50.0)
        else:
            # Underdog: gets points, easier to cover
            cover_prob = (1 - win_prob) * (1 + abs_spread / 50.0)
        # Clamp between 0.2 and 0.9
        return max(0.2, min(0.9, cover_prob))

    def _build_spread_picks(self, games: List[Dict]) -> List[Dict]:
        """
        Build spread pick objects from analyzed games.
        Each game produces one ATS pick for the side our model favors to cover.
        """
        spread_picks = []
        for game in games:
            spread = game.get('spread', 0)
            if spread is None or spread == 0:
                continue  # skip games without spread data

            win_prob = game.get('win_prob', 0.5)
            pick_team = game.get('pick', '')

            # For favorites (spread < 0), our pick already IS the favorite
            # For underdogs (spread > 0), the picked team is the away underdog
            # We calculate cover prob for the team we pick on the ML side
            # But for spread, we pick whichever side has better cover value

            # Calculate cover prob for each side using IMPROVED method
            home = game.get('home', '')
            away = game.get('away', '')
            home_win_prob = win_prob if pick_team == home else 1 - win_prob

            # Use improved cover probability calculation
            home_cover = self._calculate_cover_prob_improved(home_win_prob, spread, home, home, away)
            away_cover = self._calculate_cover_prob_improved(1 - home_win_prob, -spread, away, home, away)

            # Pick the side with higher cover probability
            if home_cover >= away_cover:
                cover_team = home
                cover_prob = home_cover
                spread_value = spread  # e.g. -5.5
            else:
                cover_team = away
                cover_prob = away_cover
                spread_value = -spread  # flip sign for away

            # Apply VALUE SCORING to spread pick
            spread_game = {
                **game,
                'bet_type': 'spread',
                'spread_pick': cover_team,
                'spread_value': round(spread_value, 1),
                'cover_prob': round(cover_prob, 4),
                'pick': cover_team,  # For value scoring
                'win_prob': cover_prob,  # Use cover prob for value calculation
            }
            
            # Calculate value score for spread pick
            spread_value_score = self.calculate_value_score(spread_game)
            spread_game['value_score'] = spread_value_score
            
            # Assign confidence tier
            pick_label = self._assign_pick_confidence_tier(spread_game)
            spread_game['pick_label'] = pick_label

            spread_pick = spread_game
            spread_picks.append(spread_pick)

        # Sort by VALUE SCORE descending (not just cover probability!)
        spread_picks.sort(key=lambda x: x.get('value_score', x.get('cover_prob', 0)), reverse=True)
        return spread_picks

    def generate_spread_single_picks(self, spread_games: List[Dict], count: int = 5) -> List[Dict]:
        """🎯 Generate VALUE-BASED spread (ATS) single picks"""
        count = min(count, len(spread_games))
        picks = []
        for i in range(count):
            g = spread_games[i]
            pick = {
                'pick_number': i + 1,
                'type': 'single',
                'bet_type': 'spread',
                'legs': 1,
                'games': [g],
                'combined_prob': g['cover_prob'],
                'value_score': g.get('value_score', g['cover_prob']),
                'edge_vs_market': g.get('edge_vs_market', 0),
                'pick_label': g.get('pick_label', '📊 LEAN'),
                'implied_payout': self._calculate_payout(g['cover_prob']),
                'earliest_game_time': g.get('game_time', '')
            }
            picks.append(pick)
        return picks

    def generate_spread_parlay_picks(self, spread_games: List[Dict], legs: int, count: int) -> List[Dict]:
        """🎯 Generate VALUE-BASED spread (ATS) parlay picks with diversification"""
        if len(spread_games) < legs:
            return []

        # For 3+ legs, use diversification similar to moneyline parlays
        if legs >= 3:
            return self._generate_diversified_spread_parlays(spread_games, legs, count)

        # For 2-leg spread parlays, use value scoring
        all_combos = list(itertools.combinations(spread_games, legs))
        scored = []
        for combo in all_combos:
            combined_prob = 1.0
            combined_value_score = 1.0
            pick_labels = []
            
            for g in combo:
                combined_prob *= g['cover_prob']
                combined_value_score *= g.get('value_score', g['cover_prob'])
                pick_labels.append(g.get('pick_label', '📊 LEAN'))
            
            game_times = [g.get('game_time', '') for g in combo if g.get('game_time')]
            scored.append({
                'games': list(combo),
                'combined_prob': combined_prob,
                'combined_value_score': combined_value_score,
                'pick_labels': pick_labels,
                'earliest_time': min(game_times) if game_times else ''
            })

        # Sort by VALUE SCORE
        scored.sort(key=lambda x: x['combined_value_score'], reverse=True)

        picks = []
        for i, combo in enumerate(scored[:count]):
            pick = {
                'pick_number': i + 1,
                'type': 'parlay',
                'bet_type': 'spread',
                'legs': legs,
                'games': combo['games'],
                'combined_prob': round(combo['combined_prob'], 4),
                'combined_value_score': round(combo['combined_value_score'], 4),
                'pick_labels': combo['pick_labels'],
                'implied_payout': self._calculate_payout(combo['combined_prob']),
                'earliest_game_time': combo['earliest_time']
            }
            picks.append(pick)
        return picks
    
    def _generate_diversified_spread_parlays(self, spread_games: List[Dict], legs: int, count: int) -> List[Dict]:
        """🎯 Generate diversified spread parlays (3+ legs) with mix of favorites and dogs"""
        # Similar to moneyline diversification but for spread picks
        locks = [g for g in spread_games if g.get('pick_label', '').startswith('LOCK')]
        values = [g for g in spread_games if g.get('pick_label', '').startswith('VALUE')]
        upsets = [g for g in spread_games if g.get('pick_label', '').startswith('UPSET')]
        leans = [g for g in spread_games if g.get('pick_label', '').startswith('LEAN')]
        
        diversified_combos = []
        max_attempts = 1000
        attempts = 0
        
        while len(diversified_combos) < count * 3 and attempts < max_attempts:
            attempts += 1
            combo_games = []
            used_games = set()
            
            # Spread parlays: Mix favorites covering + dogs covering
            if legs >= 4:
                target_locks = 1
                target_values = 2
                target_others = legs - 3
            else:  # legs == 3
                target_locks = 1
                target_values = 1 
                target_others = 1
            
            # Add picks using same logic as moneyline diversification
            available_locks = [g for g in locks if g['game_id'] not in used_games]
            for _ in range(min(target_locks, len(available_locks))):
                if available_locks:
                    game = random.choice(available_locks)
                    combo_games.append(game)
                    used_games.add(game['game_id'])
                    available_locks = [g for g in available_locks if g['game_id'] != game['game_id']]
            
            available_values = [g for g in values if g['game_id'] not in used_games]
            for _ in range(min(target_values, len(available_values))):
                if available_values:
                    game = random.choice(available_values)
                    combo_games.append(game)
                    used_games.add(game['game_id'])
                    available_values = [g for g in available_values if g['game_id'] != game['game_id']]
            
            available_others = [g for g in (upsets + leans) if g['game_id'] not in used_games]
            while len(combo_games) < legs and available_others:
                game = random.choice(available_others)
                combo_games.append(game)
                used_games.add(game['game_id'])
                available_others = [g for g in available_others if g['game_id'] != game['game_id']]
            
            if len(combo_games) < legs:
                available_any = [g for g in spread_games if g['game_id'] not in used_games]
                while len(combo_games) < legs and available_any:
                    game = random.choice(available_any)
                    combo_games.append(game)
                    used_games.add(game['game_id'])
                    available_any = [g for g in available_any if g['game_id'] != game['game_id']]
            
            if len(combo_games) == legs:
                combined_prob = 1.0
                combined_value_score = 1.0
                pick_labels = []
                
                for game in combo_games:
                    combined_prob *= game['cover_prob']
                    combined_value_score *= game.get('value_score', game['cover_prob'])
                    pick_labels.append(game.get('pick_label', '📊 LEAN'))
                
                game_times = [g.get('game_time', '') for g in combo_games if g.get('game_time')]
                earliest_time = min(game_times) if game_times else ''
                
                combo_id = tuple(sorted(g['game_id'] for g in combo_games))
                if combo_id not in [tuple(sorted(c['combo_id'])) for c in diversified_combos]:
                    diversified_combos.append({
                        'games': combo_games,
                        'combined_prob': combined_prob,
                        'combined_value_score': combined_value_score,
                        'pick_labels': pick_labels,
                        'earliest_time': earliest_time,
                        'combo_id': list(combo_id)
                    })
        
        diversified_combos.sort(key=lambda x: x['combined_value_score'], reverse=True)
        top_combinations = diversified_combos[:count]
        
        picks = []
        for i, combo in enumerate(top_combinations):
            pick = {
                'pick_number': i + 1,
                'type': 'parlay',
                'bet_type': 'spread',
                'legs': legs,
                'games': combo['games'],
                'combined_prob': round(combo['combined_prob'], 4),
                'combined_value_score': round(combo['combined_value_score'], 4),
                'pick_labels': combo['pick_labels'],
                'diversified': True,
                'implied_payout': self._calculate_payout(combo['combined_prob']),
                'earliest_game_time': combo['earliest_time']
            }
            picks.append(pick)
        
        return picks
    
    def analyze_specific_game(self, home_team: str, away_team: str, games: List[Dict]) -> Dict:
        """
        🔍 DEMO: Analyze a specific game to show value detection
        Example: Cavs @ Hornets analysis
        """
        # Find the game
        target_game = None
        for game in games:
            if (home_team.lower() in game['home'].lower() and 
                away_team.lower() in game['away'].lower()):
                target_game = game
                break
        
        if not target_game:
            return {'error': f'Game not found: {away_team} @ {home_team}'}
        
        analysis = {
            'game': f"{target_game['away']} @ {target_game['home']}",
            'basic_pick': target_game['pick'],
            'win_probability': target_game['win_prob'],
            'value_score': target_game.get('value_score', 0),
            'edge_vs_market': target_game.get('edge_vs_market', 0),
            'pick_label': target_game.get('pick_label', 'N/A'),
            'spread': target_game.get('spread', 0),
            'analysis': []
        }
        
        # Detailed analysis
        spread = target_game.get('spread', 0)
        win_prob = target_game['win_prob']
        pick_team = target_game['pick']
        
        analysis['analysis'].append(f"Our model gives {pick_team} a {win_prob:.1%} chance to win")
        
        if spread != 0:
            analysis['analysis'].append(f"Market spread: {target_game['home']} {spread:+.1f}")
            
            # Calculate implied market probability
            spread_abs = abs(spread)
            if spread < 0:  # Home favored
                market_home_prob = 0.5 + (spread_abs / 25.0)
                market_away_prob = 1 - market_home_prob
            else:  # Away favored
                market_away_prob = 0.5 + (spread_abs / 25.0)
                market_home_prob = 1 - market_away_prob
            
            if pick_team == target_game['home']:
                market_prob = market_home_prob
            else:
                market_prob = market_away_prob
            
            analysis['analysis'].append(f"Market implies {pick_team} has ~{market_prob:.1%} win probability")
            
            edge = win_prob - market_prob
            if edge > 0.05:
                analysis['analysis'].append(f"VALUE! We have {edge:+.1%} edge vs market")
            elif edge > 0:
                analysis['analysis'].append(f"Slight edge: {edge:+.1%} vs market")
            else:
                analysis['analysis'].append(f"Market disagrees: {edge:+.1%} vs our model")
        
        # Check for upset potential
        if target_game.get('upset_score', 0) > 0:
            reasons = target_game.get('upset_reasons', [])
            analysis['analysis'].append(f"UPSET CANDIDATE! Reasons: {', '.join(reasons)}")
        
        return analysis
    
    def _estimate_spread_from_probability(self, win_prob: float) -> float:
        """
        Estimate a spread line from win probability for demo purposes
        This is a rough approximation: 60% win prob ≈ 2.5 point favorite
        """
        if win_prob >= 0.5:
            # Favorite - negative spread (home laying points)
            favorite_advantage = win_prob - 0.5  # e.g., 0.1 for 60%
            estimated_spread = -(favorite_advantage * 25)  # Scale to points
        else:
            # Underdog - positive spread (home getting points)  
            underdog_deficit = 0.5 - win_prob
            estimated_spread = underdog_deficit * 25
        
        # Round to typical spread increments (0.5 points)
        estimated_spread = round(estimated_spread * 2) / 2
        
        # Clamp to reasonable NBA spread range
        estimated_spread = max(-18, min(18, estimated_spread))
        
        return estimated_spread

    def generate_tier_picks(self, target_date: date) -> Dict:
        """
        Generate picks for all tiers
        Returns dict organized by tier with picks for each
        """
        logger.info(f"Generating tier picks for {target_date}")
        
        # Fetch and analyze games
        games = self.fetch_and_analyze_games(target_date)
        self._last_analyzed_games = games  # store for external access
        
        if not games:
            logger.warning("No games available - returning empty tier structure")
            return self._create_empty_tier_structure(target_date)
        
        result = {
            'date': target_date.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'total_games': len(games),
            'tiers': {}
        }
        
        # Generate picks for each tier
        for tier_id in self.TIER_ORDER:
            tier_config = self.TIERS[tier_id]
            legs = tier_config['legs']
            count = tier_config['count']
            
            logger.info(f"Generating {count} picks for {tier_id} ({legs} legs)")
            
            try:
                if legs == 1:
                    # Single picks
                    picks = self.generate_single_picks(games, count)
                else:
                    # Parlay picks
                    picks = self.generate_parlay_picks(games, legs, count)
                
                # Tag all ML picks with bet_type
                for pick in picks:
                    pick['bet_type'] = 'moneyline'
                    for g in pick.get('games', []):
                        g['bet_type'] = 'moneyline'
                
                result['tiers'][tier_id] = {
                    'tier_id': tier_id,
                    'tier_name': f"{legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
                    'legs': legs,
                    'picks': picks,
                    'total_picks': len(picks)
                }
                
                logger.info(f"Generated {len(picks)} picks for {tier_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate picks for {tier_id}: {e}")
                result['tiers'][tier_id] = {
                    'tier_id': tier_id,
                    'tier_name': f"{legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
                    'legs': legs,
                    'picks': [],
                    'total_picks': 0,
                    'error': str(e)
                }
        
        # Generate spread (ATS) tiers
        spread_games = self._build_spread_picks(games)
        logger.info(f"Built {len(spread_games)} spread pick candidates")
        
        for tier_id in self.SPREAD_TIER_ORDER:
            tier_config = self.SPREAD_TIERS[tier_id]
            legs = tier_config['legs']
            count = tier_config['count']
            
            logger.info(f"Generating {count} picks for {tier_id} ({legs} legs, spread)")
            
            try:
                if legs == 1:
                    picks = self.generate_spread_single_picks(spread_games, count)
                else:
                    picks = self.generate_spread_parlay_picks(spread_games, legs, count)
                
                result['tiers'][tier_id] = {
                    'tier_id': tier_id,
                    'tier_name': f"Spread {legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
                    'legs': legs,
                    'bet_type': 'spread',
                    'picks': picks,
                    'total_picks': len(picks)
                }
                logger.info(f"Generated {len(picks)} spread picks for {tier_id}")
            except Exception as e:
                logger.error(f"Failed to generate spread picks for {tier_id}: {e}")
                result['tiers'][tier_id] = {
                    'tier_id': tier_id,
                    'tier_name': f"Spread {legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
                    'legs': legs,
                    'bet_type': 'spread',
                    'picks': [],
                    'total_picks': 0,
                    'error': str(e)
                }
        
        logger.info("Tier pick generation complete")
        return result
    
    def _create_empty_tier_structure(self, target_date: date) -> Dict:
        """Create empty tier structure when no games are available"""
        result = {
            'date': target_date.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'total_games': 0,
            'no_games': True,
            'tiers': {}
        }
        
        for tier_id in self.TIER_ORDER:
            tier_config = self.TIERS[tier_id]
            legs = tier_config['legs']
            
            result['tiers'][tier_id] = {
                'tier_id': tier_id,
                'tier_name': f"{legs}-Leg {'Picks' if legs == 1 else 'Parlays'}",
                'legs': legs,
                'picks': [],
                'total_picks': 0
            }
        
        return result
    
    def run(self, target_date: date, output_file: str = "tier_picks_output.json", 
            odds_api_key: str = None) -> Dict:
        """
        Main entry point - generate all tier picks
        """
        logger.info("="*60)
        logger.info("TIER ENGINE STARTING")
        logger.info(f"Target date: {target_date}")
        logger.info("="*60)
        
        # Initialize odds fetcher if key provided
        if odds_api_key:
            self.initialize_odds_fetcher(odds_api_key)
        
        # Generate picks
        start_time = time.time()
        results = self.generate_tier_picks(target_date)
        duration = time.time() - start_time
        
        # Add metadata
        results['_metadata'] = {
            'engine_version': 'tier_engine_v1.0',
            'generation_duration_seconds': round(duration, 2),
            'total_tiers': len(self.TIER_ORDER),
            'tier_order': self.TIER_ORDER
        }
        
        # Save results
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        logger.info("="*60)
        logger.info("🔥 VALUE ENGINE RESULTS")
        logger.info("="*60)
        logger.info(f"Total games processed: {results['total_games']}")
        
        # Show tier results
        for tier_id in self.TIER_ORDER:
            tier_data = results['tiers'].get(tier_id, {})
            pick_count = tier_data.get('total_picks', 0)
            tier_name = tier_data.get('tier_name', tier_id)
            logger.info(f"{tier_name}: {pick_count} picks")
        
        # Show spread tier results
        for tier_id in self.SPREAD_TIER_ORDER:
            tier_data = results['tiers'].get(tier_id, {})
            pick_count = tier_data.get('total_picks', 0)
            tier_name = tier_data.get('tier_name', tier_id)
            logger.info(f"{tier_name}: {pick_count} picks")
        
        # 🎯 DEMO: Show specific game analysis (like Cavs @ Hornets)
        games = self._last_analyzed_games if hasattr(self, '_last_analyzed_games') and self._last_analyzed_games else []
        if games:
            logger.info("\n" + "="*60)
            logger.info("🔍 SAMPLE GAME ANALYSIS")
            logger.info("="*60)
            
            # Look for Cavs @ Hornets specifically
            cavs_hornets = self.analyze_specific_game("Hornets", "Cavaliers", games)
            if 'error' not in cavs_hornets:
                logger.info(f"🏀 {cavs_hornets['game']}")
                logger.info(f"📊 Basic Pick: {cavs_hornets['basic_pick']} ({cavs_hornets['win_probability']:.1%})")
                logger.info(f"🔥 Value Score: {cavs_hornets['value_score']:.3f}")
                logger.info(f"📈 Edge vs Market: {cavs_hornets['edge_vs_market']:+.1%}")
                logger.info(f"🏷️ Label: {cavs_hornets['pick_label']}")
                for line in cavs_hornets['analysis']:
                    logger.info(f"   {line}")
            else:
                # Show first available game as example
                if games:
                    sample_game = games[0]
                    logger.info(f"🏀 SAMPLE: {sample_game['away']} @ {sample_game['home']}")
                    logger.info(f"📊 Basic Pick: {sample_game['pick']} ({sample_game['win_prob']:.1%})")
                    logger.info(f"🔥 Value Score: {sample_game.get('value_score', 0):.3f}")
                    logger.info(f"📈 Edge vs Market: {sample_game.get('edge_vs_market', 0):+.1%}")
                    logger.info(f"🏷️ Label: {sample_game.get('pick_label', 'N/A')}")
        
        logger.info("\n" + "="*60)
        logger.info(f"🕐 Generation time: {duration:.2f} seconds")
        logger.info(f"💾 Output saved to: {output_file}")
        logger.info("🚀 SHARP VALUE PICKS READY!")
        logger.info("="*60)
        
        return results

    def generate_all_sports_picks(self, target_date: date = None) -> Dict:
        """
        Generate picks across ALL sports: NBA, NCAAB, MMA, Tennis, Golf, Boxing.
        Returns unified structure with per-sport sections.
        """
        td = target_date or date.today()
        date_str = td.isoformat()
        logger.info(f"=== MULTI-SPORT PICK GENERATION: {date_str} ===")

        result = {
            "date": date_str,
            "generated_at": datetime.now().isoformat(),
            "sports": {},
            "cross_sport_parlays": [],
        }

        all_straight_picks = []

        # 1. NBA (from tier engine itself)
        try:
            nba_result = self.generate_tier_picks(td)
            result["sports"]["NBA"] = nba_result
            # Extract straight picks for cross-sport parlays
            for tier_id, tier_data in nba_result.get("tiers", {}).items():
                if tier_data.get("legs") == 1:
                    for pick in tier_data.get("picks", []):
                        for g in pick.get("games", []):
                            all_straight_picks.append({**g, "sport": "NBA"})
            logger.info(f"NBA: {nba_result.get('total_games', 0)} games")
        except Exception as e:
            logger.error(f"NBA engine error: {e}")
            result["sports"]["NBA"] = {"error": str(e)}

        # 2. NCAAB
        if NCAAB_AVAILABLE:
            try:
                ncaab = NCAABEngine()
                ncaab_picks = ncaab.predict_games(td)
                result["sports"]["NCAAB"] = {
                    "total_picks": len(ncaab_picks),
                    "picks": ncaab_picks,
                }
                for p in ncaab_picks:
                    if p.get("confidence", 0) >= 0.58:
                        all_straight_picks.append({
                            "home_team": p.get("home_team", ""),
                            "away_team": p.get("away_team", ""),
                            "predicted_winner": p.get("predicted_winner", ""),
                            "confidence": p.get("confidence", 0.5),
                            "sport": "NCAAB",
                        })
                logger.info(f"NCAAB: {len(ncaab_picks)} picks")
            except Exception as e:
                logger.error(f"NCAAB engine error: {e}")
                result["sports"]["NCAAB"] = {"error": str(e)}

        # 3. MMA
        if MMA_AVAILABLE:
            try:
                mma = MMAEngine()
                mma_picks = mma.generate_picks(date_filter=date_str)
                straight = [p for p in mma_picks if p.get("type") == "straight"]
                result["sports"]["MMA"] = {
                    "total_picks": len(straight),
                    "total_parlays": len(mma_picks) - len(straight),
                    "picks": mma_picks,
                }
                for p in straight:
                    for g in p.get("games", []):
                        if g.get("confidence", 0) >= 0.58:
                            all_straight_picks.append({**g, "sport": "MMA"})
                logger.info(f"MMA: {len(straight)} picks")
            except Exception as e:
                logger.error(f"MMA engine error: {e}")
                result["sports"]["MMA"] = {"error": str(e)}

        # 4. Tennis
        if TENNIS_AVAILABLE:
            try:
                tennis = TennisEngine()
                tennis_picks = tennis.generate_picks(target_date=date_str)
                straight = [p for p in tennis_picks if p.get("type") == "straight"]
                result["sports"]["Tennis"] = {
                    "total_picks": len(straight),
                    "total_parlays": len(tennis_picks) - len(straight),
                    "picks": tennis_picks,
                }
                for p in straight:
                    for g in p.get("games", []):
                        if g.get("confidence", 0) >= 0.58:
                            all_straight_picks.append({**g, "sport": "Tennis"})
                logger.info(f"Tennis: {len(straight)} picks")
            except Exception as e:
                logger.error(f"Tennis engine error: {e}")
                result["sports"]["Tennis"] = {"error": str(e)}

        # 5. Golf
        if GOLF_AVAILABLE:
            try:
                golf = GolfEngine()
                golf_picks = golf.generate_picks(target_date=date_str)
                result["sports"]["Golf"] = {
                    "total_events": len(golf_picks),
                    "picks": golf_picks,
                }
                logger.info(f"Golf: {len(golf_picks)} events")
            except Exception as e:
                logger.error(f"Golf engine error: {e}")
                result["sports"]["Golf"] = {"error": str(e)}

        # 6. Boxing
        if BOXING_AVAILABLE:
            try:
                boxing = BoxingEngine()
                boxing_picks = boxing.generate_picks(target_date=date_str)
                straight = [p for p in boxing_picks if p.get("type") == "straight"]
                result["sports"]["Boxing"] = {
                    "total_picks": len(straight),
                    "total_parlays": len(boxing_picks) - len(straight),
                    "picks": boxing_picks,
                }
                for p in straight:
                    for g in p.get("games", []):
                        if g.get("confidence", 0) >= 0.58:
                            all_straight_picks.append({**g, "sport": "Boxing"})
                logger.info(f"Boxing: {len(straight)} picks")
            except Exception as e:
                logger.error(f"Boxing engine error: {e}")
                result["sports"]["Boxing"] = {"error": str(e)}

        # Generate cross-sport parlays
        if len(all_straight_picks) >= 2:
            result["cross_sport_parlays"] = self._build_cross_sport_parlays(all_straight_picks)
            logger.info(f"Cross-sport parlays: {len(result['cross_sport_parlays'])}")

        result["summary"] = {
            "sports_available": list(result["sports"].keys()),
            "total_straight_picks": len(all_straight_picks),
            "cross_sport_parlays": len(result.get("cross_sport_parlays", [])),
        }

        return result

    def _build_cross_sport_parlays(self, picks: List[Dict], max_legs: int = 5) -> List[Dict]:
        """Build parlays mixing picks from different sports."""
        # Sort by confidence
        picks.sort(key=lambda p: p.get("confidence", 0), reverse=True)
        top = picks[:12]

        parlays = []
        parlay_num = 1

        for n_legs in range(2, min(max_legs + 1, len(top) + 1)):
            combos = list(itertools.combinations(top, n_legs))
            # Prefer combos with different sports
            scored = []
            for combo in combos:
                sports_set = set(p.get("sport", "") for p in combo)
                conf = 1.0
                for p in combo:
                    conf *= p.get("confidence", 0.5)
                diversity_bonus = len(sports_set) / n_legs  # 1.0 = all different sports
                score = conf * (1 + diversity_bonus * 0.2)
                scored.append((score, conf, combo, sports_set))

            scored.sort(key=lambda x: x[0], reverse=True)

            for score, conf, combo, sports in scored[:3]:
                legs = []
                for p in combo:
                    legs.append({
                        "sport": p.get("sport", ""),
                        "home_team": p.get("home_team", ""),
                        "away_team": p.get("away_team", ""),
                        "predicted_winner": p.get("predicted_winner", ""),
                        "confidence": p.get("confidence", 0.5),
                    })
                parlays.append({
                    "pick_number": parlay_num,
                    "type": "cross_sport_parlay",
                    "legs": n_legs,
                    "sports": list(sports),
                    "combined_confidence": round(conf, 4),
                    "diversity_score": round(len(sports) / n_legs, 2),
                    "games": legs,
                })
                parlay_num += 1

        return parlays


def main():
    """CLI interface for tier engine"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ParlayGuarantee Tier Engine')
    parser.add_argument('--date', help='Target date (YYYY-MM-DD)')
    parser.add_argument('--output', default='tier_picks_output.json', help='Output file')
    parser.add_argument('--odds-key', help='Odds API key (optional)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--all-sports', action='store_true', help='Generate picks for ALL sports')
    
    args = parser.parse_args()
    
    # Set up logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('tier_engine.log', encoding='utf-8')
        ]
    )
    
    # Parse date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        target_date = date.today()
    
    # Run engine
    engine = TierEngine()

    if args.all_sports:
        results = engine.generate_all_sports_picks(target_date)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        summary = results.get("summary", {})
        print(f"✅ Multi-sport: {summary.get('sports_available', [])} — {summary.get('total_straight_picks', 0)} picks")
        print(f"📁 Output saved to: {args.output}")
    else:
        results = engine.run(target_date, args.output, args.odds_key)

        if results.get('no_games'):
            print("⚠️  No games available for the target date")
            sys.exit(0)

        total_picks = sum(tier.get('total_picks', 0) for tier in results['tiers'].values())
        if total_picks > 0:
            print(f"✅ Success! Generated {total_picks} picks across {len(results['tiers'])} tiers")
            print(f"📁 Output saved to: {args.output}")
        else:
            print("❌ No picks generated")
            sys.exit(1)

if __name__ == "__main__":
    main()