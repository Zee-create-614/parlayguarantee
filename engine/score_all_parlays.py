"""
Score ALL parlays from generate_all_parlays.py against actual NBA results.
FIXED VERSION with better error handling and data sources.

Usage: python score_all_parlays_fixed.py [all_parlays_YYYY-MM-DD.json]
       python score_all_parlays_fixed.py --yesterday
"""

import json
import requests
import sys
import logging
from datetime import datetime, date, timedelta
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ESPN Scoreboard API
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# Enhanced team name normalization
TEAM_ALIASES = {
    'LA Clippers': ['LA Clippers', 'Los Angeles Clippers', 'LAC', 'Clippers'],
    'Los Angeles Lakers': ['Los Angeles Lakers', 'LA Lakers', 'LAL', 'Lakers'],
    'Oklahoma City Thunder': ['Oklahoma City Thunder', 'OKC Thunder', 'OKC'],
    'Golden State Warriors': ['Golden State Warriors', 'Warriors', 'GSW'],
    'New York Knicks': ['New York Knicks', 'Knicks', 'NYK'],
    'Philadelphia 76ers': ['Philadelphia 76ers', '76ers', 'PHI'],
    'Portland Trail Blazers': ['Portland Trail Blazers', 'Trail Blazers', 'POR'],
    'San Antonio Spurs': ['San Antonio Spurs', 'Spurs', 'SAS'],
    # Add more as needed
}

def normalize_team(name):
    """Enhanced team name normalization"""
    if not name:
        return name
        
    name = name.strip()
    name_lower = name.lower()
    
    # Direct mapping
    for canonical, aliases in TEAM_ALIASES.items():
        for alias in aliases:
            if alias.lower() == name_lower:
                return canonical
    
    # Return as-is if no mapping found
    return name


def fetch_scores_espn(game_date):
    """Fetch final scores from ESPN for a given date (enhanced)"""
    if isinstance(game_date, str):
        game_date = date.fromisoformat(game_date)
        
    date_str = game_date.strftime('%Y%m%d')
    logger.info(f"Fetching scores from ESPN for {game_date} (date_str: {date_str})")
    
    try:
        resp = requests.get(ESPN_SCOREBOARD, params={'dates': date_str}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch ESPN data: {e}")
        return []
    
    events = data.get('events', [])
    if not events:
        logger.warning(f"No events found for {game_date}")
        return []
    
    results = []
    
    for event in events:
        competitions = event.get('competitions', [])
        if not competitions:
            continue
            
        comp = competitions[0]
        status = comp.get('status', {}).get('type', {}).get('name', '')
        
        teams = comp.get('competitors', [])
        if len(teams) < 2:
            continue
        
        home = away = None
        home_score = away_score = 0
        
        for t in teams:
            team_name = t.get('team', {}).get('displayName', '')
            score = int(t.get('score', 0))
            if t.get('homeAway') == 'home':
                home = normalize_team(team_name)
                home_score = score
            else:
                away = normalize_team(team_name)
                away_score = score
        
        if home and away:
            winner = home if home_score > away_score else away
            result = {
                'home': home,
                'away': away,
                'home_score': home_score,
                'away_score': away_score,
                'winner': winner,
                'margin': abs(home_score - away_score),
                'final': status == 'STATUS_FINAL',
            }
            results.append(result)
    
    logger.info(f"Found {len(results)} games from ESPN")
    return results


def find_parlay_file(target_date):
    """Find the best available parlay file for the target date"""
    engine_dir = Path(__file__).parent
    
    # Primary: all_parlays_YYYY-MM-DD.json
    primary_file = engine_dir / f'all_parlays_{target_date}.json'
    if primary_file.exists():
        logger.info(f"Found primary parlay file: {primary_file.name}")
        return primary_file
    
    # Fallback 1: Check history directory
    history_dir = engine_dir / 'history'
    if history_dir.exists():
        archived_file = history_dir / f'all_parlays_{target_date}.json'
        if archived_file.exists():
            logger.info(f"Found archived parlay file: {archived_file.name}")
            return archived_file
    
    # Fallback 2: Mock picks (for testing)
    mock_file = engine_dir / f'mock_picks_{target_date}.json'
    if mock_file.exists():
        logger.info(f"Found mock picks file: {mock_file.name}")
        return mock_file
    
    logger.error(f"No parlay file found for {target_date}")
    return None


def score_parlays(parlays_file, game_date=None):
    """Score parlays with enhanced error handling"""
    if isinstance(parlays_file, str):
        parlays_file = Path(parlays_file)
        
    if not parlays_file.exists():
        # Try to find alternative
        if game_date:
            alt_file = find_parlay_file(game_date)
            if alt_file:
                parlays_file = alt_file
            else:
                logger.error(f"No parlay data found for {game_date}")
                return
        else:
            logger.error(f"File not found: {parlays_file}")
            return

    logger.info(f"Scoring parlays from: {parlays_file}")

    try:
        with open(parlays_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load parlay file: {e}")
        return
    
    if not game_date:
        game_date = data.get('date')
        if game_date:
            game_date = date.fromisoformat(game_date) if isinstance(game_date, str) else game_date
    
    if not game_date:
        logger.error("Could not determine game date")
        return
        
    logger.info(f"Scoring parlays for {game_date}")
    
    # Handle different data formats
    if 'games' in data:
        # Simple games list format
        total_picks = len(data['games'])
        logger.info(f"Found {total_picks} individual games")
    elif 'bets' in data:
        # Full parlay structure
        total_bets = data.get('summary', {}).get('total_bets', 0)
        logger.info(f"Found {total_bets} total parlay bets")
    else:
        logger.error("Unknown data format in parlay file")
        return
    
    # Fetch actual scores
    scores = fetch_scores_espn(game_date)
    if not scores:
        logger.error("No scores found. Games may not be final yet.")
        return
    
    not_final = [s for s in scores if not s['final']]
    if not_final:
        logger.warning(f"{len(not_final)} games not yet final")
    
    # Display actual results
    logger.info("\nActual Results:")
    for s in scores:
        status = "FINAL" if s['final'] else "IN PROGRESS"
        logger.info(f"  {s['away']} {s['away_score']} @ {s['home']} {s['home_score']} — Winner: {s['winner']} ({status})")
    
    # Build lookup for game results
    score_lookup = {}
    for s in scores:
        # Multiple keys for flexible matching
        keys = [
            (normalize_team(s['home']), normalize_team(s['away'])),
            (normalize_team(s['away']), normalize_team(s['home'])),
            s['home'].lower(),
            s['away'].lower(),
        ]
        for key in keys:
            score_lookup[key] = s
    
    # Score the picks based on data format
    if 'games' in data:
        # Simple individual game scoring
        score_individual_games(data, score_lookup, game_date)
    elif 'bets' in data:
        # Full parlay scoring
        score_parlay_bets(data, score_lookup, game_date)
    
    # Save scored results
    scored_file = str(parlays_file).replace('.json', '_scored.json')
    data['scored_at'] = datetime.now().isoformat()
    data['game_date'] = str(game_date)
    
    with open(scored_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\nScored results saved to: {scored_file}")
    return data


def score_individual_games(data, score_lookup, game_date):
    """Score individual games (simple format)"""
    games = data['games']
    correct = 0
    total = len(games)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"INDIVIDUAL GAME RESULTS — {game_date}")
    logger.info(f"{'='*70}")
    
    for i, game in enumerate(games):
        home = normalize_team(game.get('home', ''))
        away = normalize_team(game.get('away', ''))
        pick = normalize_team(game.get('pick', ''))
        confidence = game.get('win_prob', 0)
        
        # Find game result
        game_result = None
        for key in [(home, away), (away, home), home.lower(), away.lower()]:
            if key in score_lookup:
                game_result = score_lookup[key]
                break
        
        if not game_result:
            logger.warning(f"  #{i+1}: No result found for {away} @ {home}")
            game['result'] = 'NO_SCORE'
            continue
        
        actual_winner = normalize_team(game_result['winner'])
        game['actual_winner'] = actual_winner
        game['actual_score'] = f"{game_result['away']} {game_result['away_score']} @ {game_result['home']} {game_result['home_score']}"
        
        is_correct = (normalize_team(pick) == normalize_team(actual_winner))
        game['correct'] = is_correct
        game['result'] = 'W' if is_correct else 'L'
        
        if is_correct:
            correct += 1
        
        emoji = "✅" if is_correct else "❌"
        logger.info(f"  #{i+1} {emoji} {away} @ {home}: picked {pick} ({confidence:.1%}) | Actual: {actual_winner}")
    
    accuracy = (correct / total * 100) if total > 0 else 0
    
    logger.info(f"\n{'='*70}")
    logger.info(f"SUMMARY")
    logger.info(f"{'='*70}")
    logger.info(f"Total picks: {total}")
    logger.info(f"Correct: {correct} ({accuracy:.1f}%)")
    logger.info(f"Deposit status: {'KEPT' if accuracy >= 60 else 'REFUNDED'} ({'✅' if accuracy >= 60 else '❌'})")
    
    # Add summary to data
    data['scoring_summary'] = {
        'total_picks': total,
        'correct_picks': correct,
        'accuracy': round(accuracy, 1),
        'deposit_kept': accuracy >= 60
    }


def score_parlay_bets(data, score_lookup, game_date):
    """Score full parlay structure (complex format)"""
    # This would implement the full parlay scoring logic
    # Similar to the original score_all_parlays.py
    logger.info("Full parlay scoring not implemented in this fixed version yet")
    logger.info("Use the simple individual game format for now")


def main():
    if len(sys.argv) > 1:
        if '--yesterday' in sys.argv:
            yesterday = date.today() - timedelta(days=1)
            target_date = yesterday.isoformat()
            parlays_file = find_parlay_file(target_date)
            if not parlays_file:
                logger.error(f"No parlay data found for {target_date}")
                sys.exit(1)
        else:
            parlays_file = Path(sys.argv[1])
            target_date = None
    else:
        target_date = date.today().isoformat()
        parlays_file = find_parlay_file(target_date)
        if not parlays_file:
            logger.error(f"No parlay data found for {target_date}")
            sys.exit(1)
    
    score_parlays(parlays_file, target_date)


if __name__ == '__main__':
    main()