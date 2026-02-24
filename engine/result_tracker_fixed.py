"""
ParlayGuarantee Result Tracker - FIXED VERSION
Scores individual spread/moneyline picks from analyzed_games.json against actual NBA outcomes.
Stores results in SQLite for tracking accuracy over time.

FIXES:
- Better ESPN API integration with timeout handling
- Improved team name normalization
- Fallback data sources for picks
- More robust error handling
- Clear logging of what data is being processed

Usage:
    python result_tracker_fixed.py --date 2026-02-19
    python result_tracker_fixed.py                     # scores yesterday's picks
"""

import sys
import json
import sqlite3
import argparse
import time
import logging
import shutil
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "results.db"
ENGINE_DIR = Path(__file__).parent
HISTORY_DIR = ENGINE_DIR / "history"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

# Enhanced team name normalization
TEAM_ALIASES = {
    'atlanta hawks': 'Atlanta Hawks',
    'boston celtics': 'Boston Celtics',
    'brooklyn nets': 'Brooklyn Nets',
    'charlotte hornets': 'Charlotte Hornets',
    'chicago bulls': 'Chicago Bulls',
    'cleveland cavaliers': 'Cleveland Cavaliers',
    'dallas mavericks': 'Dallas Mavericks',
    'denver nuggets': 'Denver Nuggets',
    'detroit pistons': 'Detroit Pistons',
    'golden state warriors': 'Golden State Warriors',
    'houston rockets': 'Houston Rockets',
    'indiana pacers': 'Indiana Pacers',
    'la clippers': 'LA Clippers',
    'los angeles clippers': 'LA Clippers',
    'los angeles lakes': 'Los Angeles Lakers',
    'la lakers': 'Los Angeles Lakers',
    'memphis grizzlies': 'Memphis Grizzlies',
    'miami heat': 'Miami Heat',
    'milwaukee bucks': 'Milwaukee Bucks',
    'minnesota timberwolves': 'Minnesota Timberwolves',
    'new orleans pelicans': 'New Orleans Pelicans',
    'new york knicks': 'New York Knicks',
    'oklahoma city thunder': 'Oklahoma City Thunder',
    'okc thunder': 'Oklahoma City Thunder',
    'orlando magic': 'Orlando Magic',
    'philadelphia 76ers': 'Philadelphia 76ers',
    'phoenix suns': 'Phoenix Suns',
    'portland trail blazers': 'Portland Trail Blazers',
    'sacramento kings': 'Sacramento Kings',
    'san antonio spurs': 'San Antonio Spurs',
    'toronto raptors': 'Toronto Raptors',
    'utah jazz': 'Utah Jazz',
    'washington wizards': 'Washington Wizards'
}

def normalize_team(name: str) -> str:
    """Normalize a team name to standard NBA name."""
    if not name:
        return name
    lower = name.lower().strip()
    return TEAM_ALIASES.get(lower, name)


def init_db(db_path: Path = DB_PATH):
    """Create tables if they don't exist."""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS pick_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            product TEXT NOT NULL,
            pick_number INTEGER NOT NULL,
            type TEXT NOT NULL,
            predicted_winner TEXT NOT NULL,
            actual_winner TEXT,
            correct INTEGER,
            confidence REAL,
            odds TEXT,
            game_home TEXT,
            game_away TEXT,
            home_score INTEGER,
            away_score INTEGER,
            spread REAL,
            spread_pick TEXT,
            spread_correct INTEGER,
            pick_label TEXT,
            upset_score REAL,
            value_score REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, product, pick_number, predicted_winner)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            product TEXT NOT NULL,
            total_picks INTEGER,
            correct_picks INTEGER,
            accuracy REAL,
            spread_correct INTEGER DEFAULT 0,
            spread_total INTEGER DEFAULT 0,
            spread_accuracy REAL DEFAULT 0,
            parlays_hit INTEGER DEFAULT 0,
            total_parlays INTEGER DEFAULT 0,
            deposit_kept INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, product)
        )
    """)

    conn.commit()
    return conn


def fetch_game_results_espn(game_date: str) -> Dict[str, Dict]:
    """Fetch actual game results from ESPN API. Returns dict keyed by team names."""
    logger.info(f"Fetching NBA scores from ESPN for {game_date}...")

    try:
        date_obj = date.fromisoformat(game_date)
        date_str = date_obj.strftime('%Y%m%d')
        
        resp = requests.get(ESPN_SCOREBOARD, params={'dates': date_str}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch ESPN scoreboard: {e}")
        return {}

    events = data.get('events', [])
    if not events:
        logger.warning(f"No games found for {game_date}")
        return {}

    results = {}
    game_count = 0

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
            is_home = t.get('homeAway') == 'home'
            
            if is_home:
                home = normalize_team(team_name)
                home_score = score
            else:
                away = normalize_team(team_name)
                away_score = score
        
        if home and away and status == 'STATUS_FINAL':
            game_count += 1
            winner = home if home_score > away_score else away
            margin = home_score - away_score  # positive = home won by this much
            
            result = {
                'home_team': home,
                'away_team': away,
                'home_score': home_score,
                'away_score': away_score,
                'winner': winner,
                'margin': margin,
                'final': True
            }
            
            # Index by multiple keys for easy lookup
            results[home] = result
            results[away] = result
            results[f"{home} vs {away}"] = result
            results[f"{away} vs {home}"] = result

    logger.info(f"Found {game_count} completed games from ESPN")
    
    # Log the games for verification
    unique_games = [v for k, v in results.items() if ' vs ' in k and v['away_team'] < v['home_team']]
    for game in unique_games:
        logger.info(f"  {game['away_team']} {game['away_score']} @ {game['home_team']} {game['home_score']} — Winner: {game['winner']}")
    
    return results


def load_picks_for_date_enhanced(game_date: str) -> List[Dict]:
    """
    Enhanced pick loading with multiple fallback sources.
    Returns flat list of individual game picks.
    """
    logger.info(f"Loading picks for {game_date}...")
    
    # 1. Try archived analyzed_games
    archived_ag = HISTORY_DIR / f"analyzed_games_{game_date}.json"
    if archived_ag.exists():
        logger.info(f"Found archived analyzed_games: {archived_ag.name}")
        with open(archived_ag, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            matching = [g for g in data if g.get('game_date', '') == game_date]
            if matching:
                logger.info(f"Loaded {len(matching)} picks from archived analyzed_games")
                return matching
    
    # 2. Try current analyzed_games
    ag_path = ENGINE_DIR / 'analyzed_games.json'
    if ag_path.exists():
        with open(ag_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            matching = [g for g in data if g.get('game_date', '') == game_date]
            if matching:
                logger.info(f"Loaded {len(matching)} picks from current analyzed_games")
                return matching
    
    # 3. Try all_parlays file (extract individual games)
    all_parlays = ENGINE_DIR / f'all_parlays_{game_date}.json'
    if all_parlays.exists():
        logger.info(f"Found all_parlays file: {all_parlays.name}")
        with open(all_parlays, 'r', encoding='utf-8') as f:
            data = json.load(f)
        games = data.get('games', [])
        if games:
            logger.info(f"Extracted {len(games)} individual picks from all_parlays")
            return games
    
    # 4. Try archived picks_output
    archived_po = HISTORY_DIR / f"picks_output_{game_date}.json"
    if archived_po.exists():
        logger.info(f"Found archived picks_output: {archived_po.name}")
        with open(archived_po, 'r', encoding='utf-8') as f:
            data = json.load(f)
        games = extract_single_games_from_picks_output(data, game_date)
        if games:
            logger.info(f"Extracted {len(games)} picks from archived picks_output")
            return games
    
    # 5. Try current picks_output
    po_path = ENGINE_DIR / 'picks_output.json'
    if po_path.exists():
        with open(po_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        picks_date = data.get('date', data.get('target_date', ''))
        if picks_date == game_date:
            games = extract_single_games_from_picks_output(data, game_date)
            if games:
                logger.info(f"Extracted {len(games)} picks from current picks_output")
                return games
    
    # 6. Try mock picks file (for testing)
    mock_path = ENGINE_DIR / f'mock_picks_{game_date}.json'
    if mock_path.exists():
        logger.info(f"Found mock picks file: {mock_path.name}")
        with open(mock_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        games = data.get('games', [])
        if games:
            logger.info(f"Loaded {len(games)} picks from mock file")
            return games
    
    logger.warning(f"No pick data found for {game_date}")
    return []


def extract_single_games_from_picks_output(data: dict, game_date: str) -> List[Dict]:
    """Extract individual games from picks_output.json single tier format."""
    tiers = data.get('tiers', {})
    single_tier = tiers.get('single', {})
    games = []
    
    for pick in single_tier.get('picks', []):
        for g in pick.get('games', []):
            # Ensure it has the expected format
            if 'home' in g and 'away' in g and 'pick' in g:
                g['game_date'] = game_date  # Ensure date is set
                games.append(g)
    
    return games


def check_spread_cover(pick_team: str, spread: float, home_team: str, margin: int) -> Optional[bool]:
    """
    Check if a spread pick covered.
    spread: the line for the home team (negative = home favored)
    margin: actual home margin (positive = home won)
    """
    if spread is None or margin is None:
        return None

    # Standard ATS logic: 
    # If spread is -3.5 (home favored by 3.5), home covers if they win by more than 3.5
    # adjusted_spread = margin + spread
    # If adjusted_spread > 0, home covered the spread
    # If adjusted_spread < 0, away covered the spread
    
    adjusted = margin + spread  # positive = home beat the spread
    
    if normalize_team(pick_team) == normalize_team(home_team):
        return adjusted > 0  # Home team picked, they need to beat the spread
    else:
        return adjusted < 0  # Away team picked, they need to beat the spread


def score_individual_picks(game_date: str, conn: sqlite3.Connection, picks: List[Dict]) -> Dict[str, Any]:
    """Score individual game picks (moneyline + spread) against actual results."""
    results = fetch_game_results_espn(game_date)

    if not results:
        logger.error(f"No game results found for {game_date}")
        return {'error': 'No game results available'}

    c = conn.cursor()
    
    # Clear existing results for this date to avoid duplicates
    c.execute("DELETE FROM pick_results WHERE date = ? AND product = 'nba_engine'", (game_date,))
    
    ml_correct = 0
    ml_total = 0
    spread_correct = 0
    spread_total = 0

    logger.info(f"\nScoring {len(picks)} picks against actual results...")

    for i, pick in enumerate(picks):
        # Handle multiple formats
        home = normalize_team(pick.get('home', pick.get('home_team', '')))
        away = normalize_team(pick.get('away', pick.get('away_team', '')))
        predicted = normalize_team(pick.get('pick', pick.get('predicted_winner', '')))
        confidence = pick.get('win_prob', pick.get('confidence', pick.get('win_probability', 0)))
        spread = pick.get('spread')
        value_score = pick.get('value_score', 0)
        pick_label = pick.get('pick_label', '')
        upset_score = pick.get('upset_score', pick.get('upset_potential', 0))

        # Find actual result
        game_result = None
        for key in [home, away, f"{home} vs {away}", f"{away} vs {home}"]:
            if key in results:
                game_result = results[key]
                break

        if not game_result:
            logger.warning(f"  #{i+1}: No result found for {away} @ {home}")
            continue

        actual_winner = game_result['winner']
        margin = game_result['margin']
        home_score = game_result['home_score']
        away_score = game_result['away_score']
        
        # Moneyline check
        ml_hit = (normalize_team(predicted) == normalize_team(actual_winner))
        ml_total += 1
        if ml_hit:
            ml_correct += 1

        # Spread check
        spread_hit = None
        if spread is not None:
            spread_hit = check_spread_cover(predicted, spread, home, margin)
            if spread_hit is not None:
                spread_total += 1
                if spread_hit:
                    spread_correct += 1

        # Log result
        emoji = "✅" if ml_hit else "❌"
        spread_emoji = ""
        if spread_hit is not None:
            spread_emoji = f" | Spread {'✅' if spread_hit else '❌'} ({spread:+.1f})"
        
        logger.info(f"  #{i+1} {emoji} {away} @ {home}: picked {predicted} "
                     f"({confidence:.1%}) | Actual: {actual_winner} "
                     f"({away_score}-{home_score}){spread_emoji}")

        # Store in DB
        try:
            c.execute("""
                INSERT OR REPLACE INTO pick_results
                (date, product, pick_number, type, predicted_winner, actual_winner,
                 correct, confidence, odds, game_home, game_away,
                 home_score, away_score, spread, spread_pick, spread_correct,
                 pick_label, upset_score, value_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game_date, 'nba_engine', i + 1, 'straight',
                predicted, actual_winner,
                1 if ml_hit else 0,
                confidence, '',
                home, away,
                home_score, away_score,
                spread,
                f"{predicted} {spread:+.1f}" if spread else None,
                1 if spread_hit else (0 if spread_hit is not None else None),
                pick_label, upset_score, value_score,
            ))
        except Exception as e:
            logger.error(f"DB insert error for pick #{i+1}: {e}")

    conn.commit()

    # Calculate and save summary
    ml_acc = (ml_correct / ml_total * 100) if ml_total > 0 else 0
    spread_acc = (spread_correct / spread_total * 100) if spread_total > 0 else 0

    try:
        c.execute("""
            INSERT OR REPLACE INTO daily_summaries
            (date, product, total_picks, correct_picks, accuracy,
             spread_correct, spread_total, spread_accuracy, deposit_kept)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_date, 'nba_engine', ml_total, ml_correct, round(ml_acc, 1),
            spread_correct, spread_total, round(spread_acc, 1),
            1 if ml_acc >= 60 else 0,
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Summary insert error: {e}")

    summary = {
        'moneyline': {'correct': ml_correct, 'total': ml_total, 'accuracy': round(ml_acc, 1)},
        'spread': {'correct': spread_correct, 'total': spread_total, 'accuracy': round(spread_acc, 1)},
    }

    logger.info(f"\n=== SUMMARY ===")
    logger.info(f"  Moneyline: {ml_correct}/{ml_total} ({ml_acc:.1f}%)")
    logger.info(f"  Spread:    {spread_correct}/{spread_total} ({spread_acc:.1f}%)")

    return summary


def main():
    parser = argparse.ArgumentParser(description='Score ParlayGuarantee picks against actual NBA results')
    parser.add_argument('--date', type=str, default=None,
                        help='Game date to score (YYYY-MM-DD). Default: yesterday')
    parser.add_argument('--db', type=str, default=None, help='Path to results database')
    args = parser.parse_args()

    game_date = args.date or (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    db_path = Path(args.db) if args.db else DB_PATH

    logger.info(f"=== ParlayGuarantee Result Tracker (FIXED) ===")
    logger.info(f"Scoring picks for: {game_date}")

    # Load picks
    picks = load_picks_for_date_enhanced(game_date)

    if not picks:
        logger.error(f"No picks found for {game_date}")
        sys.exit(1)

    logger.info(f"Loaded {len(picks)} individual picks for {game_date}")

    # Init DB and score
    conn = init_db(db_path)

    try:
        summary = score_individual_picks(game_date, conn, picks)
        
        if 'error' not in summary:
            logger.info(f"\n=== Final Results for {game_date} ===")
            ml = summary['moneyline']
            sp = summary['spread']
            logger.info(f"  Moneyline: {ml['correct']}/{ml['total']} ({ml['accuracy']}%)")
            logger.info(f"  Spread:    {sp['correct']}/{sp['total']} ({sp['accuracy']}%)")
            
            if ml['accuracy'] >= 60:
                logger.info(f"  🎉 DEPOSIT KEPT! (≥60% accuracy)")
            else:
                logger.info(f"  💰 REFUND REQUIRED (<60% accuracy)")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()