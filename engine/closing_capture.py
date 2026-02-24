"""
Closing Line Capture for ParlayGuarantee
Captures closing lines ~30 minutes before games start

This script should be run approximately 30 minutes before the first game
of the day tips off to capture the "closing" lines that represent the
sharpest market consensus.

Features:
- Automatic detection of game start times
- Capture closing lines for all sports
- Update existing line movement records
- Generate pre-game analysis comparing opening to closing lines
- Alert for significant line movements

Usage:
  python closing_capture.py                    # Auto-detect today's games
  python closing_capture.py --date 2026-02-21  # Specific date
  python closing_capture.py --force            # Force capture regardless of timing
  python closing_capture.py --analysis-only   # Just analyze existing data
"""

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import requests
import statistics

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "line_movement.db"
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Sports configuration
SPORTS_CONFIG = {
    'basketball_nba': {
        'name': 'NBA',
        'markets': ['spreads', 'totals', 'h2h'],
        'timezone_offset': -5,  # EST
    },
    'basketball_ncaab': {
        'name': 'NCAAB', 
        'markets': ['spreads', 'totals', 'h2h'],
        'timezone_offset': -5,  # EST
    }
}

# Minimum time before game start to capture (minutes)
MIN_CAPTURE_TIME = 15
MAX_CAPTURE_TIME = 120  # Don't capture more than 2 hours early


class ClosingLineCapture:
    def __init__(self, force_capture: bool = False):
        self.force_capture = force_capture
        
    def capture_closing_lines(self, target_date: date = None) -> Dict:
        """Capture closing lines for all games."""
        if target_date is None:
            target_date = date.today()
            
        logger.info(f"Starting closing line capture for {target_date}")
        
        # Get games and their start times
        upcoming_games = self._get_upcoming_games(target_date)
        if not upcoming_games:
            logger.warning(f"No games found for {target_date}")
            return {'status': 'no_games', 'captured': 0}
        
        # Check timing unless forced
        if not self.force_capture:
            timing_check = self._check_capture_timing(upcoming_games)
            if not timing_check['should_capture']:
                logger.info(f"Timing check failed: {timing_check['message']}")
                return {'status': 'timing_failed', 'message': timing_check['message']}
        
        # Capture current lines
        results = {'captured': 0, 'updated': 0, 'errors': 0, 'sports': {}}
        
        for sport_key, sport_config in SPORTS_CONFIG.items():
            try:
                sport_results = self._capture_sport_closing(sport_key, sport_config, target_date)
                results['sports'][sport_key] = sport_results
                results['captured'] += sport_results.get('captured', 0)
                results['updated'] += sport_results.get('updated', 0)
                results['errors'] += sport_results.get('errors', 0)
                
            except Exception as e:
                logger.error(f"Error capturing {sport_key}: {e}")
                results['errors'] += 1
        
        # Generate analysis
        analysis = self._analyze_line_movements(target_date)
        results['analysis'] = analysis
        
        # Save capture summary
        self._save_capture_summary(target_date, results)
        
        logger.info(f"Closing capture complete: {results['updated']} games updated, {results['errors']} errors")
        return results
    
    def _get_upcoming_games(self, target_date: date) -> List[Dict]:
        """Get all games for the date with start times."""
        all_games = []
        
        for sport_key, sport_config in SPORTS_CONFIG.items():
            try:
                games = self._fetch_sport_games(sport_key, sport_config)
                
                # Filter to target date and add sport info
                for game in games:
                    game_dt = self._parse_commence_time(game.get('commence_time', ''))
                    if game_dt and game_dt.date() == target_date:
                        game['sport'] = sport_key
                        game['sport_name'] = sport_config['name']
                        game['game_datetime'] = game_dt
                        all_games.append(game)
                        
            except Exception as e:
                logger.error(f"Error fetching {sport_key} games: {e}")
        
        # Sort by start time
        all_games.sort(key=lambda x: x.get('game_datetime', datetime.now()))
        
        logger.info(f"Found {len(all_games)} games for {target_date}")
        return all_games
    
    def _check_capture_timing(self, games: List[Dict]) -> Dict:
        """Check if it's the right time to capture closing lines."""
        if not games:
            return {'should_capture': False, 'message': 'No games found'}
        
        now = datetime.now()
        first_game = games[0]
        first_start = first_game.get('game_datetime')
        
        if not first_start:
            return {'should_capture': False, 'message': 'Could not determine game start time'}
        
        # Calculate time until first game
        time_until = (first_start - now).total_seconds() / 60  # minutes
        
        if time_until < MIN_CAPTURE_TIME:
            return {
                'should_capture': False,
                'message': f'Too close to game start ({time_until:.0f} min). Need at least {MIN_CAPTURE_TIME} min.'
            }
        elif time_until > MAX_CAPTURE_TIME:
            return {
                'should_capture': False,
                'message': f'Too early ({time_until:.0f} min until first game). Wait until within {MAX_CAPTURE_TIME} min.'
            }
        else:
            return {
                'should_capture': True,
                'message': f'Good timing: {time_until:.0f} minutes until first game starts',
                'time_until_first': time_until,
                'first_game': f"{first_game.get('away_team', '')} @ {first_game.get('home_team', '')}"
            }
    
    def _fetch_sport_games(self, sport_key: str, sport_config: Dict) -> List[Dict]:
        """Fetch games for a specific sport."""
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'us',
            'markets': ','.join(sport_config['markets']),
            'oddsFormat': 'american',
        }
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        
        resp = requests.get(url, params=params, timeout=30)
        remaining = resp.headers.get('x-requests-remaining', '?')
        logger.debug(f"{sport_key} API requests remaining: {remaining}")
        
        if resp.status_code != 200:
            logger.error(f"API error for {sport_key}: {resp.status_code}")
            return []
        
        return resp.json()
    
    def _parse_commence_time(self, commence_time: str) -> Optional[datetime]:
        """Parse commence time to datetime object."""
        if not commence_time:
            return None
        
        try:
            # Parse ISO format and convert to EST
            utc_dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
            est_offset = timedelta(hours=-5)  # EST
            est_dt = utc_dt + est_offset
            return est_dt
        except Exception as e:
            logger.error(f"Error parsing commence time '{commence_time}': {e}")
            return None
    
    def _capture_sport_closing(self, sport_key: str, sport_config: Dict, target_date: date) -> Dict:
        """Capture closing lines for a specific sport."""
        games = self._fetch_sport_games(sport_key, sport_config)
        
        captured = updated = errors = 0
        
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        
        for game in games:
            try:
                # Parse game info
                game_dt = self._parse_commence_time(game.get('commence_time', ''))
                if not game_dt or game_dt.date() != target_date:
                    continue
                
                home = game['home_team']
                away = game['away_team']
                
                # Extract consensus lines
                lines = self._extract_consensus_lines(game.get('bookmakers', []))
                if not lines:
                    errors += 1
                    continue
                
                # Update existing record with closing lines
                c.execute('''UPDATE line_movements 
                    SET close_total = ?, close_total_over_odds = ?, close_total_under_odds = ?,
                        close_spread = ?, close_spread_home_odds = ?, close_spread_away_odds = ?,
                        close_ml_home = ?, close_ml_away = ?, close_captured_at = ?
                    WHERE game_date = ? AND sport = ? AND home_team = ? AND away_team = ?''',
                    (lines.get('total'), lines.get('total_over_odds'), lines.get('total_under_odds'),
                     lines.get('spread'), lines.get('spread_home_odds'), lines.get('spread_away_odds'),
                     lines.get('ml_home'), lines.get('ml_away'), datetime.now(),
                     target_date.isoformat(), sport_config['name'], home, away))
                
                if c.rowcount > 0:
                    updated += 1
                else:
                    # Insert new record if not exists (fallback)
                    c.execute('''INSERT OR IGNORE INTO line_movements
                        (game_date, sport, home_team, away_team, commence_time,
                         close_total, close_total_over_odds, close_total_under_odds,
                         close_spread, close_spread_home_odds, close_spread_away_odds,
                         close_ml_home, close_ml_away, close_captured_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (target_date.isoformat(), sport_config['name'], home, away, 
                         game.get('commence_time'),
                         lines.get('total'), lines.get('total_over_odds'), lines.get('total_under_odds'),
                         lines.get('spread'), lines.get('spread_home_odds'), lines.get('spread_away_odds'),
                         lines.get('ml_home'), lines.get('ml_away'), datetime.now()))
                    if c.rowcount > 0:
                        captured += 1
                
            except Exception as e:
                logger.error(f"Error processing {home} vs {away}: {e}")
                errors += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"{sport_config['name']}: {updated} updated, {captured} new, {errors} errors")
        
        return {
            'updated': updated,
            'captured': captured,
            'errors': errors,
            'sport': sport_config['name'],
        }
    
    def _extract_consensus_lines(self, bookmakers: List[Dict]) -> Dict:
        """Extract consensus lines from bookmakers."""
        totals = []
        total_over_odds = []
        total_under_odds = []
        spreads = []
        spread_home_odds = []
        spread_away_odds = []
        ml_home = []
        ml_away = []
        
        for book in bookmakers:
            book_name = book.get('title', '')
            
            for market in book.get('markets', []):
                if market['key'] == 'totals':
                    for outcome in market['outcomes']:
                        if outcome['name'] == 'Over':
                            totals.append(outcome.get('point', 0))
                            total_over_odds.append(outcome.get('price', 0))
                        elif outcome['name'] == 'Under':
                            total_under_odds.append(outcome.get('price', 0))
                            
                elif market['key'] == 'spreads':
                    for outcome in market['outcomes']:
                        spreads.append(outcome.get('point', 0))
                        # Determine home vs away based on point value (home typically negative)
                        if outcome.get('point', 0) < 0:  # Home favorite
                            spread_home_odds.append(outcome.get('price', 0))
                        else:  # Away favorite or home dog
                            spread_away_odds.append(outcome.get('price', 0))
                            
                elif market['key'] == 'h2h':
                    for outcome in market['outcomes']:
                        # Need to determine home vs away team
                        # This is simplified - would need better team matching
                        if 'home' in outcome.get('name', '').lower():
                            ml_home.append(outcome.get('price', 0))
                        else:
                            ml_away.append(outcome.get('price', 0))
        
        # Calculate consensus (median for lines, mean for odds)
        result = {}
        if totals:
            result['total'] = statistics.median(totals)
        if total_over_odds:
            result['total_over_odds'] = int(statistics.mean(total_over_odds))
        if total_under_odds:
            result['total_under_odds'] = int(statistics.mean(total_under_odds))
        if spreads:
            result['spread'] = statistics.median(spreads)
        if spread_home_odds:
            result['spread_home_odds'] = int(statistics.mean(spread_home_odds))
        if spread_away_odds:
            result['spread_away_odds'] = int(statistics.mean(spread_away_odds))
        if ml_home:
            result['ml_home'] = int(statistics.mean(ml_home))
        if ml_away:
            result['ml_away'] = int(statistics.mean(ml_away))
            
        return result
    
    def _analyze_line_movements(self, target_date: date) -> Dict:
        """Analyze line movements from opening to closing."""
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        
        # Calculate movements for games with both opening and closing lines
        c.execute('''UPDATE line_movements 
                     SET total_movement = close_total - open_total,
                         spread_movement = close_spread - open_spread,
                         ml_movement_home = close_ml_home - open_ml_home,
                         ml_movement_away = close_ml_away - open_ml_away
                     WHERE game_date = ? 
                       AND open_total IS NOT NULL 
                       AND close_total IS NOT NULL''', (target_date.isoformat(),))
        
        # Get movement summary
        c.execute('''SELECT sport,
                            COUNT(*) as games,
                            AVG(ABS(total_movement)) as avg_total_move,
                            AVG(ABS(spread_movement)) as avg_spread_move,
                            MAX(ABS(total_movement)) as max_total_move,
                            MAX(ABS(spread_movement)) as max_spread_move
                     FROM line_movements 
                     WHERE game_date = ? AND total_movement IS NOT NULL
                     GROUP BY sport''', (target_date.isoformat(),))
        
        summary = c.fetchall()
        
        # Get significant movers
        c.execute('''SELECT home_team, away_team, sport,
                            open_total, close_total, total_movement,
                            open_spread, close_spread, spread_movement
                     FROM line_movements
                     WHERE game_date = ? 
                       AND (ABS(total_movement) >= 2.0 OR ABS(spread_movement) >= 1.0)
                     ORDER BY ABS(total_movement) DESC''', (target_date.isoformat(),))
        
        big_movers = c.fetchall()
        
        conn.commit()
        conn.close()
        
        return {
            'date': target_date.isoformat(),
            'summary': summary,
            'significant_moves': big_movers,
            'analysis_time': datetime.now().isoformat(),
        }
    
    def _save_capture_summary(self, target_date: date, results: Dict):
        """Save capture summary to file."""
        summary_path = Path(__file__).parent / f"closing_capture_{target_date}.json"
        
        try:
            with open(summary_path, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"Capture summary saved to {summary_path}")
        except Exception as e:
            logger.error(f"Error saving summary: {e}")
    
    def analyze_existing_data(self, target_date: date) -> Dict:
        """Analyze existing line movement data without capturing new lines."""
        logger.info(f"Analyzing existing line data for {target_date}")
        
        analysis = self._analyze_line_movements(target_date)
        
        # Display analysis
        self._display_analysis(analysis)
        
        return analysis
    
    def _display_analysis(self, analysis: Dict):
        """Display line movement analysis."""
        print(f"\n{'='*80}")
        print(f"  📈 LINE MOVEMENT ANALYSIS — {analysis['date']}")
        print(f"{'='*80}")
        
        # Summary by sport
        print(f"\n  MOVEMENT SUMMARY:")
        for summary_row in analysis.get('summary', []):
            sport, games, avg_total, avg_spread, max_total, max_spread = summary_row
            print(f"    {sport}: {games} games")
            print(f"      Avg Total Movement: {avg_total:.1f} points")
            print(f"      Avg Spread Movement: {avg_spread:.1f} points")
            print(f"      Max Total Movement: {max_total:.1f} points")
            print(f"      Max Spread Movement: {max_spread:.1f} points")
        
        # Significant movers
        movers = analysis.get('significant_moves', [])
        if movers:
            print(f"\n  SIGNIFICANT MOVEMENTS (≥2.0 total or ≥1.0 spread):")
            for mover in movers:
                home, away, sport, ot, ct, tm, os, cs, sm = mover
                print(f"    {away} @ {home} ({sport})")
                if tm and abs(tm) >= 2.0:
                    direction = "⬆️" if tm > 0 else "⬇️"
                    print(f"      Total: {ot} → {ct} ({direction} {abs(tm):.1f})")
                if sm and abs(sm) >= 1.0:
                    direction = "⬆️" if sm > 0 else "⬇️"  
                    print(f"      Spread: {os:+.1f} → {cs:+.1f} ({direction} {abs(sm):.1f})")
        
        print(f"\n{'='*80}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    # Parse arguments
    force_capture = '--force' in sys.argv
    analysis_only = '--analysis-only' in sys.argv
    
    target_date = date.today()
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        if idx + 1 < len(sys.argv):
            target_date = date.fromisoformat(sys.argv[idx + 1])
    
    capture = ClosingLineCapture(force_capture=force_capture)
    
    if analysis_only:
        # Just analyze existing data
        analysis = capture.analyze_existing_data(target_date)
    else:
        # Capture closing lines
        results = capture.capture_closing_lines(target_date)
        
        print(f"\n{'='*60}")
        print(f"  CLOSING LINE CAPTURE RESULTS")
        print(f"{'='*60}")
        print(f"  Date: {target_date}")
        print(f"  Status: {results.get('status', 'completed')}")
        print(f"  Games Updated: {results.get('updated', 0)}")
        print(f"  New Captures: {results.get('captured', 0)}")
        print(f"  Errors: {results.get('errors', 0)}")
        
        if 'message' in results:
            print(f"  Message: {results['message']}")
        
        # Show sport breakdown
        for sport, sport_results in results.get('sports', {}).items():
            print(f"    {sport}: {sport_results.get('updated', 0)} updated, {sport_results.get('errors', 0)} errors")
        
        # Display analysis if available
        analysis = results.get('analysis', {})
        if analysis:
            capture._display_analysis(analysis)
        
        print(f"{'='*60}")


if __name__ == "__main__":
    main()