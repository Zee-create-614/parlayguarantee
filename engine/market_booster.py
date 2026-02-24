"""
Market Confidence Booster
Takes engine picks and adjusts confidence based on prediction market consensus
Implements boosting rules and contrarian pick flagging
"""
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from prediction_markets import PredictionMarketsAggregator

logger = logging.getLogger(__name__)


class MarketBooster:
    """Adjusts pick confidence based on prediction market consensus"""
    
    def __init__(self, sport: str = 'NBA'):
        self.sport = sport
        self.aggregator = PredictionMarketsAggregator()
        self.market_data_cache = None
        logger.info(f"Initialized MarketBooster for {sport}")
    
    def boost_picks(self, picks_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply market-based confidence boosting to all picks
        
        Args:
            picks_data: Original picks output from engine
            
        Returns:
            Enhanced picks data with market consensus and adjusted confidence
        """
        logger.info("Starting market-based confidence boosting...")
        
        # Fetch market data once for efficiency
        if self.market_data_cache is None:
            logger.info("Fetching prediction market data...")
            self.market_data_cache = self.aggregator.fetch_all_sports_markets(self.sport)
            logger.info(f"Cached market data for {len(self.market_data_cache)} games")
        
        # Process each product's picks
        enhanced_picks = {}
        
        for product_id, product_data in picks_data.items():
            if isinstance(product_data, dict) and 'picks' in product_data:
                logger.info(f"Processing {product_id} with {len(product_data['picks'])} picks")
                
                enhanced_product_data = product_data.copy()
                enhanced_picks_list = []
                
                for pick in product_data['picks']:
                    enhanced_pick = self._boost_individual_pick(pick)
                    enhanced_picks_list.append(enhanced_pick)
                
                enhanced_product_data['picks'] = enhanced_picks_list
                
                # Add market boosting summary to product data
                boost_stats = self._calculate_boost_stats(enhanced_picks_list)
                enhanced_product_data['market_boost_summary'] = boost_stats
                
                enhanced_picks[product_id] = enhanced_product_data
            else:
                # Pass through non-pick data unchanged
                enhanced_picks[product_id] = product_data
        
        # Add global market boost metadata
        enhanced_picks['_market_boost_metadata'] = {
            'applied_at': datetime.now().isoformat(),
            'market_sources': ['kalshi', 'polymarket'],
            'boost_version': '1.0',
            'total_games_with_market_data': len(self.market_data_cache)
        }
        
        logger.info("Market-based confidence boosting completed")
        return enhanced_picks
    
    def _boost_individual_pick(self, pick: Dict[str, Any]) -> Dict[str, Any]:
        """Apply market boosting to a single pick"""
        enhanced_pick = pick.copy()
        
        # Process each game in the pick
        enhanced_games = []
        pick_market_data = []
        
        for game in pick.get('games', []):
            enhanced_game, game_market_data = self._boost_individual_game(game)
            enhanced_games.append(enhanced_game)
            if game_market_data:
                pick_market_data.append(game_market_data)
        
        enhanced_pick['games'] = enhanced_games
        
        # Calculate overall pick adjustments
        if pick_market_data:
            enhanced_pick['market_consensus'] = self._calculate_pick_consensus(pick_market_data)
            enhanced_pick['combined_prob'] = self._adjust_combined_probability(
                pick.get('combined_prob', 1.0), 
                enhanced_pick['market_consensus']
            )
        else:
            enhanced_pick['market_consensus'] = {
                'status': 'no_market_data',
                'message': 'No prediction market data available for this pick'
            }
        
        return enhanced_pick
    
    def _boost_individual_game(self, game: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict]]:
        """Apply market boosting to a single game within a pick"""
        enhanced_game = game.copy()
        
        home_team = game.get('home', '')
        away_team = game.get('away', '')
        picked_team = game.get('pick', '')
        our_prob = game.get('win_prob', 0.5)
        
        if not all([home_team, away_team, picked_team]):
            logger.debug(f"Incomplete game data for market boosting: {game}")
            return enhanced_game, None
        
        # Find market data for this game
        market_data = self._find_market_data_for_game(home_team, away_team)
        
        if not market_data:
            logger.debug(f"No market data found for {home_team} vs {away_team}")
            enhanced_game['market_consensus'] = {
                'status': 'no_data',
                'kalshi_prob': None,
                'polymarket_prob': None,
                'our_prob': our_prob,
                'consensus': 'no_data',
                'adjusted_confidence': our_prob
            }
            return enhanced_game, None
        
        # Get market probabilities for the picked team
        picked_team_market_data = market_data['consolidated_probabilities'].get(picked_team, {})
        
        kalshi_prob = picked_team_market_data.get('kalshi_prob')
        polymarket_prob = picked_team_market_data.get('polymarket_prob')
        consensus_prob = picked_team_market_data.get('consensus_prob')
        
        # Apply boosting logic
        consensus_type, adjusted_confidence = self._apply_boosting_rules(
            our_prob, consensus_prob, kalshi_prob, polymarket_prob
        )
        
        # Create market consensus data
        market_consensus = {
            'kalshi_prob': kalshi_prob,
            'polymarket_prob': polymarket_prob,
            'our_prob': our_prob,
            'consensus': consensus_type,
            'adjusted_confidence': adjusted_confidence
        }
        
        enhanced_game['market_consensus'] = market_consensus
        enhanced_game['win_prob'] = adjusted_confidence  # Update the win probability
        
        return enhanced_game, market_consensus
    
    def _find_market_data_for_game(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Find market data for a specific game"""
        if not self.market_data_cache:
            return None
        
        # Try different game key formats
        teams_sorted = sorted([home_team, away_team])
        game_key = f"{teams_sorted[0]}_{teams_sorted[1]}"
        
        market_data = self.market_data_cache.get(game_key)
        
        if not market_data:
            # Try alternative matching (e.g., partial team names)
            for cached_game_key, cached_data in self.market_data_cache.items():
                if self._teams_match(home_team, away_team, cached_game_key):
                    market_data = cached_data
                    break
        
        return market_data
    
    def _teams_match(self, home_team: str, away_team: str, cached_game_key: str) -> bool:
        """Check if team names match cached game key with fuzzy matching"""
        try:
            cached_teams = cached_game_key.split('_')
            if len(cached_teams) != 2:
                return False
            
            # Check if any combination matches
            teams_to_check = [home_team, away_team]
            
            for team in teams_to_check:
                for cached_team in cached_teams:
                    # Fuzzy matching - check if key words match
                    team_words = set(team.upper().split())
                    cached_words = set(cached_team.upper().split())
                    
                    # If significant overlap, consider it a match
                    if len(team_words & cached_words) >= 1:
                        return True
            
            return False
            
        except Exception:
            return False
    
    def _apply_boosting_rules(
        self, 
        our_prob: float, 
        consensus_prob: Optional[float],
        kalshi_prob: Optional[float], 
        polymarket_prob: Optional[float]
    ) -> Tuple[str, float]:
        """
        Apply the boosting rules based on agreement with market consensus
        
        Returns: (consensus_type, adjusted_confidence)
        """
        if consensus_prob is None:
            # No consensus data available
            return 'no_data', our_prob
        
        # Calculate agreement level
        prob_diff = abs(our_prob - consensus_prob)
        
        # Boosting rules implementation
        if prob_diff <= 0.05:  # Within 5%
            # Strong agreement - boost by 10%
            boost_factor = 0.10
            adjusted = min(our_prob + boost_factor, 1.0)
            return 'strong_agree', adjusted
            
        elif prob_diff <= 0.10:  # Within 10%
            # Agreement - boost by 5-8%
            boost_factor = 0.065  # Average of 5-8%
            adjusted = min(our_prob + boost_factor, 1.0)
            return 'agree', adjusted
            
        elif prob_diff > 0.15:  # Disagree by more than 15%
            # Major disagreement - flag as contrarian
            return 'contrarian', our_prob
            
        else:
            # Mild disagreement - no change
            return 'mild_disagree', our_prob
    
    def _calculate_pick_consensus(self, game_market_data: List[Dict]) -> Dict[str, Any]:
        """Calculate overall pick consensus from individual game data"""
        if not game_market_data:
            return {'status': 'no_data'}
        
        # Count consensus types
        consensus_counts = {}
        total_games = len(game_market_data)
        
        for game_data in game_market_data:
            consensus_type = game_data.get('consensus', 'unknown')
            consensus_counts[consensus_type] = consensus_counts.get(consensus_type, 0) + 1
        
        # Determine overall pick consensus
        if consensus_counts.get('strong_agree', 0) > 0:
            overall_consensus = 'strong_agree'
        elif consensus_counts.get('agree', 0) > 0:
            overall_consensus = 'agree'
        elif consensus_counts.get('contrarian', 0) > 0:
            overall_consensus = 'contrarian'
        else:
            overall_consensus = 'mixed'
        
        return {
            'overall_consensus': overall_consensus,
            'game_breakdown': consensus_counts,
            'total_games': total_games,
            'contrarian_games': consensus_counts.get('contrarian', 0),
            'boosted_games': consensus_counts.get('strong_agree', 0) + consensus_counts.get('agree', 0)
        }
    
    def _adjust_combined_probability(self, original_combined_prob: float, market_consensus: Dict) -> float:
        """Adjust the combined probability for the entire pick based on market consensus"""
        if market_consensus.get('status') == 'no_data':
            return original_combined_prob
        
        overall_consensus = market_consensus.get('overall_consensus', 'mixed')
        
        # Apply pick-level adjustments
        if overall_consensus == 'strong_agree':
            # Boost combined probability
            boost_factor = 0.08  # Slightly less than individual game boost
            return min(original_combined_prob + boost_factor, 1.0)
            
        elif overall_consensus == 'agree':
            # Moderate boost
            boost_factor = 0.05
            return min(original_combined_prob + boost_factor, 1.0)
            
        elif overall_consensus == 'contrarian':
            # Flag but don't penalize (let user decide)
            return original_combined_prob
            
        else:
            # Mixed or mild disagreement - no change
            return original_combined_prob
    
    def _calculate_boost_stats(self, enhanced_picks: List[Dict]) -> Dict[str, Any]:
        """Calculate summary statistics for market boosting"""
        total_picks = len(enhanced_picks)
        
        if total_picks == 0:
            return {'total_picks': 0}
        
        boost_stats = {
            'total_picks': total_picks,
            'picks_with_market_data': 0,
            'picks_boosted': 0,
            'picks_contrarian': 0,
            'avg_boost_amount': 0.0,
            'consensus_breakdown': {}
        }
        
        total_boost_amount = 0.0
        boosted_count = 0
        
        for pick in enhanced_picks:
            market_consensus = pick.get('market_consensus', {})
            
            if market_consensus.get('status') != 'no_market_data':
                boost_stats['picks_with_market_data'] += 1
                
                overall_consensus = market_consensus.get('overall_consensus', 'unknown')
                boost_stats['consensus_breakdown'][overall_consensus] = \
                    boost_stats['consensus_breakdown'].get(overall_consensus, 0) + 1
                
                if overall_consensus in ['strong_agree', 'agree']:
                    boost_stats['picks_boosted'] += 1
                    
                    # Calculate boost amount
                    original_prob = pick.get('combined_prob', 0.0)
                    for game in pick.get('games', []):
                        market_data = game.get('market_consensus', {})
                        adjusted = market_data.get('adjusted_confidence', 0.0)
                        original = market_data.get('our_prob', 0.0)
                        if adjusted > original:
                            total_boost_amount += (adjusted - original)
                            boosted_count += 1
                
                elif overall_consensus == 'contrarian':
                    boost_stats['picks_contrarian'] += 1
        
        if boosted_count > 0:
            boost_stats['avg_boost_amount'] = total_boost_amount / boosted_count
        
        return boost_stats


def apply_market_boosting(picks_data: Dict[str, Any], sport: str = 'NBA') -> Dict[str, Any]:
    """
    Convenience function to apply market boosting to picks data
    
    Args:
        picks_data: Original picks output from engine
        sport: Sport type (default: NBA)
        
    Returns:
        Enhanced picks data with market consensus and adjusted confidence
    """
    try:
        booster = MarketBooster(sport)
        return booster.boost_picks(picks_data)
    except Exception as e:
        logger.error(f"Market boosting failed: {str(e)}")
        # Return original data with error metadata on failure
        picks_data['_market_boost_error'] = {
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
        return picks_data


if __name__ == "__main__":
    # Test the market booster with sample data
    logging.basicConfig(level=logging.INFO)
    
    sample_picks = {
        'test-product': {
            'product': 'test-product',
            'picks': [
                {
                    'pick_number': 1,
                    'type': 'straight',
                    'games': [
                        {
                            'home': 'Los Angeles Lakers',
                            'away': 'Golden State Warriors',
                            'pick': 'Los Angeles Lakers',
                            'win_prob': 0.75,
                            'game_date': '2026-02-19'
                        }
                    ],
                    'combined_prob': 0.75
                }
            ]
        }
    }
    
    print("Testing market booster with sample data...")
    enhanced_picks = apply_market_boosting(sample_picks)
    
    print("\nEnhanced picks:")
    print(json.dumps(enhanced_picks, indent=2, default=str))