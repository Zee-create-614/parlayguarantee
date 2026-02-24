"""
Comprehensive Daily Pick Generator v2 for ParlayGuarantee
Generates ALL picks for the day across NBA, NCAAB, spreads, totals, and parlays

Output structure:
picks_YYYY-MM-DD/
  nba_spreads.json       # NBA spread picks
  nba_totals.json        # NBA O/U picks  
  ncaab_spreads.json     # NCAAB spread picks
  ncaab_totals.json      # NCAAB O/U picks
  parlays_nba.json       # NBA-only parlay combos (2-10 legs)
  parlays_ncaab.json     # NCAAB-only parlay combos
  parlays_mixed.json     # NBA+NCAAB cross-sport parlays
  parlays_nba_ou.json    # NBA O/U only parlays
  parlays_ncaab_ou.json  # NCAAB O/U only parlays
  parlays_mixed_ou.json  # Cross-sport O/U parlays
  summary.json           # Master summary

Usage:
  python daily_picks_v2.py                    # Generate today's picks
  python daily_picks_v2.py --date 2026-02-21  # Specific date
  python daily_picks_v2.py --max-legs 8       # Limit parlay size
"""

import json
import logging
import sys
import time
from datetime import date, datetime
from typing import Dict, List, Tuple
from pathlib import Path
from itertools import combinations

logger = logging.getLogger(__name__)

# Import our engines
try:
    from engine_v2 import NBAPredictor
    from totals_engine_v2 import TotalsEngineV2
    from ncaab_engine import NCABEngine  # Assuming this exists
    from ncaab_totals_engine_v2 import NCAABTotalsEngineV2
    NBA_AVAILABLE = True
    NCAAB_AVAILABLE = True
except ImportError as e:
    logger.error(f"Import error: {e}")
    NBA_AVAILABLE = False
    NCAAB_AVAILABLE = False


def american_to_decimal(american_odds: int) -> float:
    """Convert American odds to decimal odds."""
    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1


def calculate_parlay_odds(picks: List[Dict]) -> Tuple[float, int]:
    """Calculate true parlay odds and payout."""
    decimal_odds = []
    
    for pick in picks:
        # Estimate odds based on confidence and edge
        confidence = pick.get('confidence', 0.55)
        edge = pick.get('edge', 0)
        
        # Convert confidence to implied odds
        if confidence > 0.5:
            # Favorite
            implied_prob = confidence
            decimal = 1 / implied_prob
        else:
            # Dog (shouldn't happen much with our models)
            implied_prob = confidence
            decimal = 1 / implied_prob
            
        # Adjust for edge - positive edge means better value
        if edge > 0:
            decimal *= 1.1  # Bonus for positive edge
        elif edge < 0:
            decimal *= 0.95  # Penalty for negative edge
            
        decimal_odds.append(max(1.5, min(3.0, decimal)))  # Keep in reasonable range
    
    # Calculate parlay odds
    parlay_decimal = 1
    for odds in decimal_odds:
        parlay_decimal *= odds
    
    # Convert to American
    if parlay_decimal >= 2.0:
        american = int((parlay_decimal - 1) * 100)
    else:
        american = int(-100 / (parlay_decimal - 1))
    
    return parlay_decimal, american


class DailyPickGenerator:
    def __init__(self, max_parlay_legs: int = 10):
        self.max_parlay_legs = max_parlay_legs
        self.nba_engine = None
        self.nba_totals_engine = None
        self.ncaab_engine = None
        self.ncaab_totals_engine = None
        
        # Initialize engines
        if NBA_AVAILABLE:
            self.nba_engine = NBAPredictor()
            self.nba_totals_engine = TotalsEngineV2()
        if NCAAB_AVAILABLE:
            self.ncaab_totals_engine = NCAABTotalsEngineV2()
    
    def generate_all_picks(self, target_date: date = None) -> Dict:
        """Generate comprehensive picks for the day."""
        if target_date is None:
            target_date = date.today()
            
        logger.info(f"Generating comprehensive picks for {target_date}")
        
        # Create output directory
        picks_dir = Path(__file__).parent / f"picks_{target_date}"
        picks_dir.mkdir(exist_ok=True)
        
        results = {
            'date': target_date.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'files_created': [],
            'summary': {},
        }
        
        # === NBA SPREADS ===
        nba_spreads = []
        if NBA_AVAILABLE and self.nba_engine:
            try:
                logger.info("Generating NBA spread picks...")
                # This would use the existing successful NBA engine
                # For now, placeholder structure
                nba_spreads = self._generate_nba_spreads(target_date)
                self._save_picks(picks_dir / 'nba_spreads.json', nba_spreads)
                results['files_created'].append('nba_spreads.json')
                results['summary']['nba_spreads'] = len(nba_spreads)
            except Exception as e:
                logger.error(f"NBA spreads error: {e}")
        
        # === NBA TOTALS ===
        nba_totals = []
        if NBA_AVAILABLE and self.nba_totals_engine:
            try:
                logger.info("Generating NBA O/U picks...")
                nba_totals = self.nba_totals_engine.run_predictions(target_date)
                self._save_picks(picks_dir / 'nba_totals.json', nba_totals)
                results['files_created'].append('nba_totals.json')
                results['summary']['nba_totals'] = len(nba_totals)
            except Exception as e:
                logger.error(f"NBA totals error: {e}")
        
        # === NCAAB SPREADS ===
        ncaab_spreads = []
        if NCAAB_AVAILABLE and self.ncaab_engine:
            try:
                logger.info("Generating NCAAB spread picks...")
                # Placeholder - would use NCAAB spread engine
                ncaab_spreads = self._generate_ncaab_spreads(target_date)
                self._save_picks(picks_dir / 'ncaab_spreads.json', ncaab_spreads)
                results['files_created'].append('ncaab_spreads.json')
                results['summary']['ncaab_spreads'] = len(ncaab_spreads)
            except Exception as e:
                logger.error(f"NCAAB spreads error: {e}")
        
        # === NCAAB TOTALS ===
        ncaab_totals = []
        if NCAAB_AVAILABLE and self.ncaab_totals_engine:
            try:
                logger.info("Generating NCAAB O/U picks...")
                ncaab_totals = self.ncaab_totals_engine.run_predictions(target_date)
                self._save_picks(picks_dir / 'ncaab_totals.json', ncaab_totals)
                results['files_created'].append('ncaab_totals.json')
                results['summary']['ncaab_totals'] = len(ncaab_totals)
            except Exception as e:
                logger.error(f"NCAAB totals error: {e}")
        
        # === PARLAY GENERATION ===
        logger.info("Generating parlay combinations...")
        
        # NBA-only parlays
        if nba_spreads or nba_totals:
            nba_all_picks = nba_spreads + nba_totals
            nba_parlays = self._generate_parlays(nba_all_picks, 'NBA Mixed')
            self._save_picks(picks_dir / 'parlays_nba.json', nba_parlays)
            results['files_created'].append('parlays_nba.json')
            results['summary']['nba_parlays'] = len(nba_parlays)
        
        # NCAAB-only parlays
        if ncaab_spreads or ncaab_totals:
            ncaab_all_picks = ncaab_spreads + ncaab_totals
            ncaab_parlays = self._generate_parlays(ncaab_all_picks, 'NCAAB Mixed')
            self._save_picks(picks_dir / 'parlays_ncaab.json', ncaab_parlays)
            results['files_created'].append('parlays_ncaab.json')
            results['summary']['ncaab_parlays'] = len(ncaab_parlays)
        
        # Cross-sport parlays
        if (nba_spreads or nba_totals) and (ncaab_spreads or ncaab_totals):
            all_picks = nba_spreads + nba_totals + ncaab_spreads + ncaab_totals
            mixed_parlays = self._generate_parlays(all_picks, 'Cross-Sport')
            self._save_picks(picks_dir / 'parlays_mixed.json', mixed_parlays)
            results['files_created'].append('parlays_mixed.json')
            results['summary']['mixed_parlays'] = len(mixed_parlays)
        
        # O/U only parlays
        if nba_totals:
            nba_ou_parlays = self._generate_parlays(nba_totals, 'NBA O/U Only')
            self._save_picks(picks_dir / 'parlays_nba_ou.json', nba_ou_parlays)
            results['files_created'].append('parlays_nba_ou.json')
            results['summary']['nba_ou_parlays'] = len(nba_ou_parlays)
        
        if ncaab_totals:
            ncaab_ou_parlays = self._generate_parlays(ncaab_totals, 'NCAAB O/U Only')
            self._save_picks(picks_dir / 'parlays_ncaab_ou.json', ncaab_ou_parlays)
            results['files_created'].append('parlays_ncaab_ou.json')
            results['summary']['ncaab_ou_parlays'] = len(ncaab_ou_parlays)
        
        if nba_totals and ncaab_totals:
            mixed_ou_parlays = self._generate_parlays(nba_totals + ncaab_totals, 'Cross-Sport O/U')
            self._save_picks(picks_dir / 'parlays_mixed_ou.json', mixed_ou_parlays)
            results['files_created'].append('parlays_mixed_ou.json')
            results['summary']['mixed_ou_parlays'] = len(mixed_ou_parlays)
        
        # === MASTER SUMMARY ===
        summary = {
            'date': target_date.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'total_straight_picks': (len(nba_spreads) + len(nba_totals) + 
                                   len(ncaab_spreads) + len(ncaab_totals)),
            'total_parlays': sum(results['summary'].get(k, 0) for k in results['summary'] 
                               if 'parlay' in k),
            'categories': results['summary'],
            'files': results['files_created'],
            'best_picks': self._get_best_picks(nba_spreads, nba_totals, 
                                             ncaab_spreads, ncaab_totals),
        }
        
        self._save_picks(picks_dir / 'summary.json', summary)
        results['files_created'].append('summary.json')
        
        logger.info(f"Generation complete: {len(results['files_created'])} files created")
        return results
    
    def _generate_nba_spreads(self, target_date: date) -> List[Dict]:
        """Generate NBA spread picks (placeholder)."""
        # This would integrate with the successful NBA engine
        # For now, return empty list
        return []
    
    def _generate_ncaab_spreads(self, target_date: date) -> List[Dict]:
        """Generate NCAAB spread picks (placeholder)."""
        # This would integrate with NCAAB spread engine
        return []
    
    def _generate_parlays(self, straight_picks: List[Dict], category: str) -> List[Dict]:
        """Generate all parlay combinations from straight picks."""
        if not straight_picks:
            return []
        
        # Filter to only strong picks for parlays
        strong_picks = [p for p in straight_picks 
                       if p.get('confidence', 0) >= 0.58 and 
                       abs(p.get('edge', 0)) >= 1.0]
        
        if len(strong_picks) < 2:
            logger.warning(f"Not enough strong picks for {category} parlays")
            return []
        
        parlays = []
        
        # Generate combinations from 2 legs up to max
        for num_legs in range(2, min(len(strong_picks) + 1, self.max_parlay_legs + 1)):
            for combo in combinations(strong_picks, num_legs):
                # Calculate parlay metrics
                decimal_odds, american_odds = calculate_parlay_odds(list(combo))
                
                # Combined confidence (conservative)
                combined_confidence = 1
                for pick in combo:
                    combined_confidence *= pick.get('confidence', 0.55)
                
                # Average edge
                avg_edge = sum(abs(p.get('edge', 0)) for p in combo) / len(combo)
                
                # Create parlay entry
                parlay = {
                    'legs': list(combo),
                    'num_legs': num_legs,
                    'category': category,
                    'combined_confidence': round(combined_confidence, 3),
                    'avg_edge': round(avg_edge, 2),
                    'estimated_odds': american_odds,
                    'decimal_odds': round(decimal_odds, 2),
                    'bet_amount': 25,  # Standard bet
                    'potential_payout': int(25 * decimal_odds),
                    'created_at': datetime.now().isoformat(),
                }
                
                # Add tier based on confidence and edge
                if combined_confidence >= 0.3 and avg_edge >= 2.0:
                    parlay['tier'] = '🔒 STRONG PARLAY'
                elif combined_confidence >= 0.2 and avg_edge >= 1.5:
                    parlay['tier'] = '📊 VALUE PARLAY'
                elif combined_confidence >= 0.15:
                    parlay['tier'] = '📈 SPECULATIVE'
                else:
                    parlay['tier'] = '🎰 LOTTERY'
                
                parlays.append(parlay)
        
        # Sort by combined confidence * avg_edge (value score)
        parlays.sort(key=lambda x: x['combined_confidence'] * x['avg_edge'], reverse=True)
        
        # Limit to reasonable number to avoid massive files
        max_parlays_per_category = 1000
        if len(parlays) > max_parlays_per_category:
            logger.info(f"Trimming {category} parlays from {len(parlays)} to {max_parlays_per_category}")
            parlays = parlays[:max_parlays_per_category]
        
        logger.info(f"Generated {len(parlays)} {category} parlays")
        return parlays
    
    def _get_best_picks(self, nba_spreads: List, nba_totals: List,
                       ncaab_spreads: List, ncaab_totals: List) -> Dict:
        """Extract the best picks across all categories."""
        all_straight = nba_spreads + nba_totals + ncaab_spreads + ncaab_totals
        
        if not all_straight:
            return {}
        
        # Sort by confidence * edge (value metric)
        all_straight.sort(key=lambda x: x.get('confidence', 0) * abs(x.get('edge', 0)), 
                         reverse=True)
        
        # Get top picks
        top_5 = all_straight[:5]
        locks = [p for p in all_straight if '🔒' in p.get('tier', '')]
        strong = [p for p in all_straight if 'STRONG' in p.get('tier', '')]
        
        return {
            'top_5_overall': top_5,
            'locks': locks,
            'strong_plays': strong[:10],  # Top 10 strong plays
            'overs': [p for p in all_straight if p.get('pick', '') == 'OVER'][:5],
            'unders': [p for p in all_straight if p.get('pick', '') == 'UNDER'][:5],
        }
    
    def _save_picks(self, file_path: Path, data: any):
        """Save picks to JSON file."""
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Saved {file_path.name}")
        except Exception as e:
            logger.error(f"Error saving {file_path}: {e}")
    
    def display_summary(self, results: Dict):
        """Display generation summary."""
        print(f"\n{'='*80}")
        print(f"  📊 DAILY PICKS GENERATION COMPLETE — {results['date']}")
        print(f"{'='*80}")
        
        summary = results.get('summary', {})
        
        # Straight picks
        print(f"\n  STRAIGHT PICKS:")
        if 'nba_spreads' in summary:
            print(f"    NBA Spreads: {summary['nba_spreads']}")
        if 'nba_totals' in summary:
            print(f"    NBA Totals: {summary['nba_totals']}")
        if 'ncaab_spreads' in summary:
            print(f"    NCAAB Spreads: {summary['ncaab_spreads']}")
        if 'ncaab_totals' in summary:
            print(f"    NCAAB Totals: {summary['ncaab_totals']}")
        
        # Parlays
        print(f"\n  PARLAYS:")
        parlay_keys = [k for k in summary.keys() if 'parlay' in k]
        for key in parlay_keys:
            clean_name = key.replace('_', ' ').title()
            print(f"    {clean_name}: {summary[key]}")
        
        # Files
        print(f"\n  FILES CREATED: {len(results['files_created'])}")
        for file_name in results['files_created']:
            print(f"    - {file_name}")
        
        print(f"{'='*80}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    # Parse arguments
    target_date = date.today()
    max_legs = 10
    
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target_date = date.fromisoformat(sys.argv[idx + 1])
    
    if '--max-legs' in sys.argv:
        idx = sys.argv.index('--max-legs')
        if idx + 1 < len(sys.argv):
            max_legs = int(sys.argv[idx + 1])
    
    # Generate picks
    generator = DailyPickGenerator(max_parlay_legs=max_legs)
    results = generator.generate_all_picks(target_date)
    generator.display_summary(results)
    
    print(f"\nPicks saved to: picks_{target_date}/")


if __name__ == "__main__":
    main()