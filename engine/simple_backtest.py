"""
Simplified NBA Backtesting System - Works with basic data
Tests parlay generation strategy with simplified stats to validate the core concept
"""
import sys
import json
import time
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import traceback

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# NBA API imports
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('simple_backtest.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SimpleBacktestResult:
    """Results for a single night of backtesting"""
    date: str
    games_available: int
    parlays_generated: int
    parlays_hit: int
    hit_rate: float
    deposit_kept: bool
    daily_profit_loss: float
    parlay_details: List[Dict]


@dataclass
class ParlayPick:
    """Individual parlay pick"""
    game: str
    pick_type: str  # 'spread', 'moneyline', 'total'
    pick: str
    confidence: float


@dataclass
class SimpleParlay:
    """Simple parlay with basic info"""
    id: int
    legs: int
    picks: List[ParlayPick]
    confidence: float


class SimpleNBABacktester:
    """Simplified NBA backtesting system"""
    
    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.teams_data = teams.get_teams()
        self.team_name_lookup = {team['id']: team['full_name'] for team in self.teams_data}
        self.results = []
        
        logger.info(f"Simple Backtester initialized for {start_date} to {end_date}")
    
    def get_games_for_date(self, target_date: date) -> List[Dict]:
        """Get completed games for a specific date"""
        try:
            date_str = target_date.strftime('%m/%d/%Y')
            logger.info(f"Fetching games for {date_str}")
            
            time.sleep(0.6)  # Rate limiting
            
            scoreboard = scoreboardv2.ScoreboardV2(game_date=date_str)
            dataframes = scoreboard.get_data_frames()
            
            games_header = dataframes[0]
            line_score = dataframes[1]
            
            if games_header.empty:
                return []
            
            games = []
            for _, game in games_header.iterrows():
                if game['GAME_STATUS_TEXT'] != 'Final':
                    continue
                    
                game_id = str(game['GAME_ID'])
                home_team_id = game['HOME_TEAM_ID']
                away_team_id = game['VISITOR_TEAM_ID']
                
                home_team = self.team_name_lookup.get(home_team_id, f"Team_{home_team_id}")
                away_team = self.team_name_lookup.get(away_team_id, f"Team_{away_team_id}")
                
                # Get scores from line score
                home_score = 0
                away_score = 0
                
                game_scores = line_score[line_score['GAME_ID'] == game['GAME_ID']]
                for _, team_line in game_scores.iterrows():
                    if team_line['TEAM_ID'] == home_team_id:
                        home_score = team_line['PTS']
                    elif team_line['TEAM_ID'] == away_team_id:
                        away_score = team_line['PTS']
                
                if home_score > 0 and away_score > 0:  # Valid completed game
                    games.append({
                        'game_id': game_id,
                        'home_team': home_team,
                        'away_team': away_team,
                        'home_team_id': home_team_id,
                        'away_team_id': away_team_id,
                        'home_score': home_score,
                        'away_score': away_score,
                        'total_score': home_score + away_score,
                        'margin': home_score - away_score
                    })
            
            logger.info(f"Found {len(games)} completed games")
            return games
            
        except Exception as e:
            logger.error(f"Error fetching games: {e}")
            return []
    
    def generate_simple_picks(self, games: List[Dict]) -> List[ParlayPick]:
        """Generate picks using simplified logic"""
        picks = []
        
        for game in games:
            game_desc = f"{game['away_team']} @ {game['home_team']}"
            
            # Simplified spread pick (favor home teams slightly)
            spread_pick = f"{game['home_team']} -3.0"
            spread_confidence = 65.0  # Moderate confidence
            
            picks.append(ParlayPick(
                game=game_desc,
                pick_type='spread',
                pick=spread_pick,
                confidence=spread_confidence
            ))
            
            # Simplified moneyline pick (home team)
            ml_pick = f"{game['home_team']} ML"
            ml_confidence = 60.0
            
            picks.append(ParlayPick(
                game=game_desc,
                pick_type='moneyline',
                pick=ml_pick,
                confidence=ml_confidence
            ))
            
            # Simplified total pick (over 220 - average NBA total)
            total_pick = "Over 220"
            total_confidence = 55.0
            
            picks.append(ParlayPick(
                game=game_desc,
                pick_type='total',
                pick=total_pick,
                confidence=total_confidence
            ))
        
        return picks
    
    def create_parlays(self, picks: List[ParlayPick]) -> List[SimpleParlay]:
        """Create parlays from available picks"""
        if len(picks) < 6:  # Need at least 6 picks to make meaningful parlays
            return []
        
        parlays = []
        parlay_id = 1
        
        # Sort picks by confidence
        picks.sort(key=lambda x: x.confidence, reverse=True)
        
        # Create different parlay sizes
        parlay_configs = [
            (2, 2),  # 2 two-leg parlays
            (3, 3),  # 3 three-leg parlays
            (4, 2),  # 2 four-leg parlays
            (5, 2),  # 2 five-leg parlays
            (6, 1)   # 1 six-leg parlay
        ]
        
        pick_index = 0
        for legs, count in parlay_configs:
            for _ in range(count):
                if pick_index + legs > len(picks):
                    break
                    
                parlay_picks = picks[pick_index:pick_index + legs]
                avg_confidence = sum(p.confidence for p in parlay_picks) / len(parlay_picks)
                
                parlays.append(SimpleParlay(
                    id=parlay_id,
                    legs=legs,
                    picks=parlay_picks,
                    confidence=avg_confidence
                ))
                
                parlay_id += 1
                pick_index += legs
        
        return parlays
    
    def check_parlay_result(self, parlay: SimpleParlay, games: List[Dict]) -> bool:
        """Check if a parlay hit"""
        game_lookup = {f"{g['away_team']} @ {g['home_team']}": g for g in games}
        
        for pick in parlay.picks:
            if pick.game not in game_lookup:
                return False
                
            game = game_lookup[pick.game]
            
            if pick.pick_type == 'spread':
                # Simplified: check if home team won (assuming we always picked home -3)
                if game['margin'] <= 3:  # Home team didn't cover 3 points
                    return False
                    
            elif pick.pick_type == 'moneyline':
                # Check if home team won
                if game['margin'] <= 0:
                    return False
                    
            elif pick.pick_type == 'total':
                # Check if over 220 hit
                if game['total_score'] <= 220:
                    return False
        
        return True
    
    def backtest_date(self, target_date: date) -> Optional[SimpleBacktestResult]:
        """Backtest a single date"""
        try:
            logger.info(f"\nBacktesting {target_date}")
            
            games = self.get_games_for_date(target_date)
            if len(games) < 3:
                logger.info(f"Not enough games ({len(games)}), skipping")
                return None
            
            # Generate picks
            picks = self.generate_simple_picks(games)
            
            # Create parlays
            parlays = self.create_parlays(picks)
            if not parlays:
                logger.info("No parlays generated, skipping")
                return None
            
            logger.info(f"Generated {len(parlays)} parlays")
            
            # Check results
            hits = 0
            parlay_details = []
            
            for parlay in parlays:
                hit = self.check_parlay_result(parlay, games)
                if hit:
                    hits += 1
                
                parlay_details.append({
                    'id': parlay.id,
                    'legs': parlay.legs,
                    'confidence': parlay.confidence,
                    'hit': hit,
                    'picks': [{'type': p.pick_type, 'pick': p.pick} for p in parlay.picks]
                })
            
            hit_rate = hits / len(parlays)
            deposit_kept = hits >= 1
            daily_pnl = (hits * 50) - (len(parlays) * 10)  # $50 avg win, $10 per bet
            
            result = SimpleBacktestResult(
                date=target_date.strftime('%Y-%m-%d'),
                games_available=len(games),
                parlays_generated=len(parlays),
                parlays_hit=hits,
                hit_rate=hit_rate,
                deposit_kept=deposit_kept,
                daily_profit_loss=daily_pnl,
                parlay_details=parlay_details
            )
            
            logger.info(f"Results: {hits}/{len(parlays)} hit ({hit_rate:.1%})")
            logger.info(f"Deposit {'KEPT' if deposit_kept else 'REFUNDED'}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error backtesting {target_date}: {e}")
            return None
    
    def run_full_backtest(self) -> Dict:
        """Run complete backtest"""
        logger.info(f"\nStarting backtest: {self.start_date} to {self.end_date}")
        
        current_date = self.start_date
        while current_date <= self.end_date:
            result = self.backtest_date(current_date)
            if result:
                self.results.append(result)
            
            current_date += timedelta(days=1)
        
        if not self.results:
            return {"error": "No results generated"}
        
        # Calculate overall results
        total_nights = len(self.results)
        nights_with_hits = sum(1 for r in self.results if r.parlays_hit > 0)
        deposit_keep_rate = (nights_with_hits / total_nights) * 100
        
        avg_hits = sum(r.parlays_hit for r in self.results) / total_nights
        total_pnl = sum(r.daily_profit_loss for r in self.results)
        
        overall_results = {
            "test_period": f"{self.start_date} to {self.end_date}",
            "total_nights": total_nights,
            "nights_with_at_least_1_hit": nights_with_hits,
            "deposit_keep_rate": f"{deposit_keep_rate:.1f}%",
            "average_hits_per_night": avg_hits,
            "total_profit_loss": total_pnl,
            "nightly_results": [asdict(r) for r in self.results]
        }
        
        # Save results
        with open("simple_backtest_results.json", "w", encoding="utf-8") as f:
            json.dump(overall_results, f, indent=2)
        
        return overall_results


def print_simple_summary(results: Dict):
    """Print summary of simple backtest"""
    print("\n" + "="*60)
    print("🏀 SIMPLE PARLAY BACKTEST RESULTS 🏀")
    print("="*60)
    
    print(f"\n📅 Period: {results['test_period']}")
    print(f"🌙 Total nights: {results['total_nights']}")
    print(f"💰 Nights with ≥1 hit: {results['nights_with_at_least_1_hit']}")
    print(f"🏦 DEPOSIT KEEP RATE: {results['deposit_keep_rate']} 👈 KEY METRIC")
    print(f"📈 Avg hits per night: {results['average_hits_per_night']:.2f}")
    print(f"💵 Total P&L: ${results['total_profit_loss']:,.2f}")
    
    keep_rate = float(results['deposit_keep_rate'].replace('%', ''))
    
    print("\n🚀 VIABILITY ASSESSMENT:")
    if keep_rate >= 80:
        print("✅ EXCELLENT - Very viable!")
    elif keep_rate >= 70:
        print("✅ GOOD - Viable with optimization")
    elif keep_rate >= 60:
        print("⚠️  MARGINAL - Needs improvement")
    else:
        print("❌ NOT VIABLE - Rework needed")
    
    print("="*60)


def main():
    """Main execution"""
    # Test 5 days in December 2024
    start_date = date(2024, 12, 1)
    end_date = date(2024, 12, 5)
    
    print("🏀 SIMPLE NBA PARLAY BACKTEST")
    print(f"📅 Testing {start_date} to {end_date}")
    print("🎯 Validating core backtesting concept\n")
    
    backtester = SimpleNBABacktester(start_date, end_date)
    
    try:
        results = backtester.run_full_backtest()
        
        if "error" not in results:
            print_simple_summary(results)
            print("\n✅ Simple backtest complete!")
            print("📊 Results saved to simple_backtest_results.json")
            print("🚀 Ready for full comprehensive backtest!")
        else:
            print(f"❌ Backtest failed: {results['error']}")
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()