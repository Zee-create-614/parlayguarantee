"""
Parlay Generator module for ParlayGuarantee Engine
Combines analyzed games into diversified parlay picks with correlation avoidance
"""
import logging
import random
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from itertools import combinations

from analyzer import GameAnalysis
from config import *

# Configure logging
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)


@dataclass
class ParlayLeg:
    """Individual leg of a parlay"""
    game: str
    pick: str
    pick_type: str  # 'spread', 'moneyline', 'total'
    odds: str
    confidence: float
    reasoning: str


@dataclass
class Parlay:
    """Complete parlay with multiple legs"""
    id: int
    legs: int
    type: str
    combined_odds: str
    combined_decimal: float
    confidence: float
    picks: List[ParlayLeg]
    potential_payout: Dict[str, str]
    

class ParlayGenerator:
    """Generates diversified parlay combinations from game analyses"""
    
    def __init__(self, analyses: List[GameAnalysis]):
        self.analyses = analyses
        self.available_picks = self._extract_all_picks()
        
        logger.info(f"ParlayGenerator initialized with {len(analyses)} games, {len(self.available_picks)} total picks")
    
    def _extract_all_picks(self) -> List[Dict]:
        """Extract all possible picks from analyses"""
        all_picks = []
        
        for analysis in self.analyses:
            game_id = f"{analysis.away_team} vs {analysis.home_team}"
            
            # Spread pick
            spread_pick = {
                'game_id': analysis.game_id,
                'game': game_id,
                'pick': analysis.spread_pick,
                'pick_type': 'spread',
                'confidence': analysis.spread_confidence,
                'reasoning': analysis.reasoning.get('spread', ''),
                'analysis': analysis
            }
            all_picks.append(spread_pick)
            
            # Moneyline pick
            ml_pick = {
                'game_id': analysis.game_id,
                'game': game_id,
                'pick': analysis.moneyline_pick,
                'pick_type': 'moneyline',
                'confidence': analysis.moneyline_confidence,
                'reasoning': analysis.reasoning.get('moneyline', ''),
                'analysis': analysis
            }
            all_picks.append(ml_pick)
            
            # Total pick
            total_pick = {
                'game_id': analysis.game_id,
                'game': game_id,
                'pick': analysis.total_pick,
                'pick_type': 'total',
                'confidence': analysis.total_confidence,
                'reasoning': analysis.reasoning.get('total', ''),
                'analysis': analysis
            }
            all_picks.append(total_pick)
        
        return all_picks
    
    def american_to_decimal_odds(self, american_odds: str) -> float:
        """Convert American odds to decimal odds"""
        try:
            odds_num = int(american_odds.replace('+', '').replace('-', ''))
            if american_odds.startswith('-'):
                return 1 + (100 / odds_num)
            else:
                return 1 + (odds_num / 100)
        except (ValueError, ZeroDivisionError):
            return 2.0  # Default decimal odds
    
    def decimal_to_american_odds(self, decimal_odds: float) -> str:
        """Convert decimal odds to American format"""
        if decimal_odds >= 2.0:
            american = int((decimal_odds - 1) * 100)
            return f"+{american}"
        else:
            american = int(-100 / (decimal_odds - 1))
            return str(american)
    
    def calculate_parlay_odds(self, individual_odds: List[str]) -> Tuple[float, str]:
        """Calculate combined parlay odds"""
        decimal_product = 1.0
        
        for odds in individual_odds:
            decimal_odds = self.american_to_decimal_odds(odds)
            decimal_product *= decimal_odds
        
        american_odds = self.decimal_to_american_odds(decimal_product)
        
        return decimal_product, american_odds
    
    def calculate_payout(self, decimal_odds: float) -> Dict[str, str]:
        """Calculate potential payouts for different bet amounts"""
        payouts = {}
        bet_amounts = [10, 25, 50, 100]
        
        for amount in bet_amounts:
            payout = amount * (decimal_odds - 1)
            payouts[f"${amount}"] = f"${payout:.0f}"
        
        return payouts
    
    def are_picks_correlated(self, pick1: Dict, pick2: Dict) -> bool:
        """Check if two picks are correlated (should not be in same parlay)"""
        # Same game correlation check
        if pick1['game_id'] == pick2['game_id']:
            # Different pick types from same game are usually OK
            # Exception: spread + moneyline for same team is highly correlated
            if (pick1['pick_type'] in ['spread', 'moneyline'] and 
                pick2['pick_type'] in ['spread', 'moneyline']):
                
                # Check if both picks are on the same team
                pick1_team = self._extract_team_from_pick(pick1['pick'])
                pick2_team = self._extract_team_from_pick(pick2['pick'])
                
                if pick1_team and pick2_team and pick1_team == pick2_team:
                    return True  # Highly correlated
        
        return False  # Not correlated
    
    def _extract_team_from_pick(self, pick_text: str) -> Optional[str]:
        """Extract team name from pick text"""
        # Simplified team extraction - would need more robust parsing in production
        for team in NBA_TEAM_COORDS.keys():
            if team in pick_text:
                return team
        return None
    
    def filter_uncorrelated_picks(self, potential_picks: List[Dict]) -> List[Dict]:
        """Filter out correlated picks to ensure parlay diversification"""
        filtered_picks = []
        
        for pick in potential_picks:
            is_correlated = False
            
            for existing_pick in filtered_picks:
                if self.are_picks_correlated(pick, existing_pick):
                    is_correlated = True
                    break
            
            if not is_correlated:
                filtered_picks.append(pick)
        
        return filtered_picks
    
    def generate_single_parlay(self, leg_count: int, parlay_id: int) -> Optional[Parlay]:
        """Generate a single parlay with specified number of legs"""
        # Sort picks by confidence (descending)
        sorted_picks = sorted(self.available_picks, key=lambda x: x['confidence'], reverse=True)
        
        # Select diverse picks with good confidence
        potential_picks = []
        
        # Mix confidence levels: some high-confidence, some value plays
        high_conf_picks = [p for p in sorted_picks if p['confidence'] >= 70]
        mid_conf_picks = [p for p in sorted_picks if 60 <= p['confidence'] < 70]
        value_picks = [p for p in sorted_picks if p['confidence'] < 60]
        
        # Determine pick distribution
        if leg_count <= 3:
            # Shorter parlays: mostly high confidence
            potential_picks.extend(random.sample(high_conf_picks, min(leg_count, len(high_conf_picks))))
        elif leg_count <= 5:
            # Medium parlays: mix of high and medium
            high_count = min(leg_count // 2, len(high_conf_picks))
            mid_count = min(leg_count - high_count, len(mid_conf_picks))
            potential_picks.extend(random.sample(high_conf_picks, high_count))
            potential_picks.extend(random.sample(mid_conf_picks, mid_count))
        else:
            # Longer parlays: include some value plays
            high_count = min(leg_count // 3, len(high_conf_picks))
            mid_count = min(leg_count // 2, len(mid_conf_picks))
            value_count = min(leg_count - high_count - mid_count, len(value_picks))
            potential_picks.extend(random.sample(high_conf_picks, high_count))
            potential_picks.extend(random.sample(mid_conf_picks, mid_count))
            potential_picks.extend(random.sample(value_picks, value_count))
        
        # Ensure we have enough picks
        if len(potential_picks) < leg_count:
            logger.warning(f"Not enough picks available for {leg_count}-leg parlay")
            return None
        
        # Filter for correlation and select final picks
        final_picks = self.filter_uncorrelated_picks(potential_picks)
        
        if len(final_picks) < leg_count:
            # If filtering removed too many, try with different picks
            random.shuffle(sorted_picks)
            potential_picks = sorted_picks[:leg_count * 2]  # Get more options
            final_picks = self.filter_uncorrelated_picks(potential_picks)
        
        if len(final_picks) < leg_count:
            logger.warning(f"Could not generate uncorrelated {leg_count}-leg parlay")
            return None
        
        # Select the final leg count
        selected_picks = final_picks[:leg_count]
        
        # Create parlay legs
        legs = []
        individual_odds = []
        
        for pick_data in selected_picks:
            # Use default odds (would integrate with real odds in production)
            odds = DEFAULT_ODDS
            individual_odds.append(odds)
            
            leg = ParlayLeg(
                game=pick_data['game'],
                pick=pick_data['pick'],
                pick_type=pick_data['pick_type'],
                odds=odds,
                confidence=pick_data['confidence'],
                reasoning=pick_data['reasoning']
            )
            legs.append(leg)
        
        # Calculate combined odds
        decimal_odds, american_odds = self.calculate_parlay_odds(individual_odds)
        
        # Calculate average confidence
        avg_confidence = sum(pick['confidence'] for pick in selected_picks) / len(selected_picks)
        
        # Adjust confidence for parlay (longer parlays are riskier)
        parlay_confidence = avg_confidence * (0.9 ** (leg_count - 2))  # Decrease confidence for more legs
        
        # Calculate payouts
        payouts = self.calculate_payout(decimal_odds)
        
        parlay = Parlay(
            id=parlay_id,
            legs=leg_count,
            type=f"{leg_count}-Leg Parlay",
            combined_odds=american_odds,
            combined_decimal=decimal_odds,
            confidence=round(parlay_confidence, 0),
            picks=legs,
            potential_payout=payouts
        )
        
        return parlay
    
    def generate_all_parlays(self) -> List[Parlay]:
        """Generate the complete set of parlay picks"""
        logger.info("Generating parlay combinations")
        
        parlays = []
        parlay_id = 1
        
        # Define leg distribution for 10 parlays
        leg_distribution = [2, 2, 3, 3, 3, 4, 4, 5, 6, 7]  # Mix of different parlay sizes
        random.shuffle(leg_distribution)  # Randomize order
        
        for leg_count in leg_distribution:
            if parlay_id > PARLAY_CONFIG['total_parlays']:
                break
            
            parlay = self.generate_single_parlay(leg_count, parlay_id)
            
            if parlay:
                parlays.append(parlay)
                logger.info(f"Generated {leg_count}-leg parlay (ID: {parlay_id}) with {parlay.confidence}% confidence")
                parlay_id += 1
            else:
                logger.warning(f"Failed to generate {leg_count}-leg parlay")
        
        logger.info(f"Generated {len(parlays)} total parlays")
        return parlays
    
    def export_to_json(self, parlays: List[Parlay], output_file: str = "picks_output.json") -> Dict:
        """Export parlays to JSON format"""
        logger.info(f"Exporting {len(parlays)} parlays to {output_file}")
        
        # Convert parlays to dictionaries
        parlay_dicts = []
        for parlay in parlays:
            parlay_dict = {
                'id': parlay.id,
                'legs': parlay.legs,
                'type': parlay.type,
                'combined_odds': parlay.combined_odds,
                'combined_decimal': round(parlay.combined_decimal, 1),
                'confidence': int(parlay.confidence),
                'picks': [],
                'potential_payout': parlay.potential_payout
            }
            
            # Convert legs
            for leg in parlay.picks:
                pick_dict = {
                    'game': leg.game,
                    'pick': leg.pick,
                    'type': leg.pick_type,
                    'odds': leg.odds,
                    'reasoning': leg.reasoning
                }
                parlay_dict['picks'].append(pick_dict)
            
            parlay_dicts.append(parlay_dict)
        
        # Create final output structure
        output_data = {
            'generated_at': datetime.now().isoformat() + 'Z',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'sport': 'NBA',
            'games_analyzed': len(self.analyses),
            'parlays': parlay_dicts,
            'track_record_entry': {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'total_parlays': len(parlays),
                'results': 'pending'
            }
        }
        
        # Write to file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Successfully exported parlays to {output_file}")
            return output_data
            
        except Exception as e:
            logger.error(f"Error exporting to JSON: {str(e)}")
            return output_data


class ParlayValidator:
    """Validates parlay picks for quality and compliance"""
    
    @staticmethod
    def validate_parlay_set(parlays: List[Parlay]) -> Dict[str, bool]:
        """Validate the entire set of parlays"""
        validation_results = {
            'count_valid': len(parlays) <= PARLAY_CONFIG['total_parlays'],
            'leg_range_valid': True,
            'confidence_valid': True,
            'diversification_valid': True
        }
        
        # Check leg count ranges
        for parlay in parlays:
            if parlay.legs < PARLAY_CONFIG['min_legs'] or parlay.legs > PARLAY_CONFIG['max_legs']:
                validation_results['leg_range_valid'] = False
        
        # Check confidence ranges
        for parlay in parlays:
            if parlay.confidence < PARLAY_CONFIG['min_confidence'] or parlay.confidence > PARLAY_CONFIG['max_confidence']:
                validation_results['confidence_valid'] = False
        
        # Check diversification (no duplicate picks across parlays)
        all_picks = []
        for parlay in parlays:
            for pick in parlay.picks:
                pick_key = f"{pick.game}_{pick.pick}"
                if pick_key in all_picks:
                    validation_results['diversification_valid'] = False
                all_picks.append(pick_key)
        
        return validation_results


if __name__ == "__main__":
    # Test parlay generator with sample data
    from analyzer import GameAnalysis
    
    # Create sample analyses
    sample_analyses = [
        GameAnalysis(
            game_id='1',
            home_team='Boston Celtics',
            away_team='Los Angeles Lakers',
            home_score=0.75,
            away_score=0.65,
            spread_pick='Celtics -4.5',
            spread_confidence=72.0,
            moneyline_pick='Celtics ML',
            moneyline_confidence=68.0,
            total_pick='Over 220.5',
            total_confidence=65.0,
            reasoning={
                'spread': 'Celtics strong at home',
                'moneyline': 'Better overall team',
                'total': 'High pace expected'
            },
            factors={}
        ),
        GameAnalysis(
            game_id='2',
            home_team='Golden State Warriors',
            away_team='Denver Nuggets',
            home_score=0.68,
            away_score=0.72,
            spread_pick='Nuggets -2.5',
            spread_confidence=70.0,
            moneyline_pick='Nuggets ML',
            moneyline_confidence=66.0,
            total_pick='Under 225.5',
            total_confidence=62.0,
            reasoning={
                'spread': 'Nuggets road warriors',
                'moneyline': 'Better recent form',
                'total': 'Defensive focus'
            },
            factors={}
        )
    ]
    
    generator = ParlayGenerator(sample_analyses)
    parlays = generator.generate_all_parlays()
    
    print(f"\nGenerated {len(parlays)} parlays:")
    for parlay in parlays:
        print(f"\nParlay {parlay.id}: {parlay.type}")
        print(f"Odds: {parlay.combined_odds} (Confidence: {parlay.confidence}%)")
        for pick in parlay.picks:
            print(f"  - {pick.game}: {pick.pick} ({pick.odds})")
    
    # Test export
    output_data = generator.export_to_json(parlays, "test_output.json")
    print(f"\nExported to JSON with {len(output_data['parlays'])} parlays")