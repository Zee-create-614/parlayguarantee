"""
ParlayGuarantee Result Tracker
Scores individual spread/moneyline picks from analyzed_games.json against actual NBA outcomes.
Stores results in SQLite for tracking accuracy over time.

Usage:
    python result_tracker.py --date 2026-02-20
    python result_tracker.py                     # scores yesterday's picks
"""

import sys
import json
import sqlite3
import argparse
import time
import logging
import shutil
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "results.db"
ENGINE_DIR = Path(__file__).parent
HISTORY_DIR = ENGINE_DIR / "history"

TEAM_ID_MAP = {t['id']: t['full_name'] for t in teams.get_teams()}

# Common team name aliases for matching
TEAM_ALIASES = {}
for t in teams.get_teams():
    full = t['full_name']
    TEAM_ALIASES[full.lower()] = full
    TEAM_ALIASES[t['abbreviation'].lower()] = full
    # Also index by city and nickname
    parts = full.rsplit(' ', 1)
    if len(parts) == 2:
        TEAM_ALIASES[parts[1].lower()] = full  # "Lakers" -> "Los Angeles Lakers"
    # Handle "Trail Blazers" type names
    parts2 = full.rsplit(' ', 2)
    if len(parts2) == 3:
        TEAM_ALIASES[f"{parts2[1]} {parts2[2]}".lower()] = full


def normalize_team(name: str) -> str:
    """Normalize a team name to full NBA name."""
    if not name:
        return name
    lower = name.lower().strip()
    return TEAM_ALIASES.get(lower, name)


def safe_get_data_frames(endpoint_result):
    """Safely convert nba_api endpoint result to list of DataFrames."""
    try:
        return endpoint_result.get_data_frames()
    except (IndexError, KeyError):
        data = endpoint_result.get_dict()
        frames = []
        for rs in data.get('resultSets', []):
            headers = rs.get('headers', [])
            rows = rs.get('rowSet', [])
            frames.append(pd.DataFrame(rows, columns=headers) if headers else pd.DataFrame())
        return frames


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

    c.execute("""
        CREATE TABLE IF NOT EXISTS dfs_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            strategy TEXT NOT NULL,
            projected_points REAL,
            actual_points REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(date, platform, strategy)
        )
    """)

    conn.commit()
    return conn


def archive_picks(game_date: str):
    """Archive today's analyzed_games.json and picks_output.json by date."""
    HISTORY_DIR.mkdir(exist_ok=True)

    for fname in ['analyzed_games.json', 'picks_output.json']:
        src = ENGINE_DIR / fname
        if src.exists():
            dst = HISTORY_DIR / f"{fname.replace('.json', '')}_{game_date}.json"
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                logger.info(f"Archived {fname} -> {dst.name}")


def load_picks_for_date(game_date: str) -> List[Dict]:
    """
    Load individual game picks for a date.
    Priority:
      1. history/analyzed_games_YYYY-MM-DD.json (archived)
      2. analyzed_games.json (if date matches)
      3. Falls back to picks_output.json single tier
    Returns flat list of individual game picks.
    """
    # Try archived file first
    archived = HISTORY_DIR / f"analyzed_games_{game_date}.json"
    if archived.exists():
        logger.info(f"Loading archived picks: {archived.name}")
        with open(archived, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return [g for g in data if g.get('game_date', '') == game_date]
        return []

    # Try current analyzed_games.json
    ag_path = ENGINE_DIR / 'analyzed_games.json'
    if ag_path.exists():
        with open(ag_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            matching = [g for g in data if g.get('game_date', '') == game_date]
            if matching:
                logger.info(f"Loaded {len(matching)} picks from analyzed_games.json")
                return matching

    # Fallback: extract individual games from picks_output.json single tier
    po_path = ENGINE_DIR / 'picks_output.json'
    if po_path.exists():
        with open(po_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        picks_date = data.get('date', data.get('target_date', ''))
        if picks_date != game_date:
            # Try history
            archived_po = HISTORY_DIR / f"picks_output_{game_date}.json"
            if archived_po.exists():
                with open(archived_po, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                logger.warning(f"No picks found for {game_date}")
                return []

        # Extract individual games from single tier
        tiers = data.get('tiers', {})
        single_tier = tiers.get('single', {})
        games = []
        for pick in single_tier.get('picks', []):
            for g in pick.get('games', []):
                games.append(g)
        if games:
            logger.info(f"Extracted {len(games)} individual picks from picks_output.json single tier")
        return games

    logger.warning(f"No picks data found for {game_date}")
    return []


def fetch_game_results(game_date: str) -> Dict[str, Dict]:
    """Fetch actual game results from NBA API. Returns dict keyed by team names."""
    logger.info(f"Fetching NBA scores for {game_date}...")

    try:
        sb = scoreboardv2.ScoreboardV2(
            game_date=game_date,
            league_id='00',
            timeout=30
        )
        time.sleep(1)
        frames = safe_get_data_frames(sb)
    except Exception as e:
        logger.error(f"Failed to fetch scoreboard: {e}")
        return {}

    if len(frames) < 2:
        logger.warning("Not enough data frames from scoreboard")
        return {}

    game_header = frames[0]
    line_score = frames[1]
    results = {}

    if line_score.empty:
        logger.warning("No line score data -- games may not have finished yet")
        return {}

    for game_id in line_score['GAME_ID'].unique():
        game_teams = line_score[line_score['GAME_ID'] == game_id]
        if len(game_teams) < 2:
            continue

        teams_data = []
        for _, row in game_teams.iterrows():
            pts = row.get('PTS', None)
            if pts is None or pd.isna(pts):
                continue
            teams_data.append({
                'team_id': row['TEAM_ID'],
                'team_name': TEAM_ID_MAP.get(row['TEAM_ID'], row.get('TEAM_ABBREVIATION', '???')),
                'team_abbrev': row.get('TEAM_ABBREVIATION', ''),
                'pts': int(pts),
            })

        if len(teams_data) < 2:
            continue

        game_hdr = game_header[game_header['GAME_ID'] == game_id]
        if not game_hdr.empty:
            home_id = game_hdr.iloc[0].get('HOME_TEAM_ID')
            away_id = game_hdr.iloc[0].get('VISITOR_TEAM_ID')
        else:
            home_id = teams_data[1]['team_id']
            away_id = teams_data[0]['team_id']

        home = next((t for t in teams_data if t['team_id'] == home_id), teams_data[1])
        away = next((t for t in teams_data if t['team_id'] == away_id), teams_data[0])

        margin = home['pts'] - away['pts']  # positive = home won by this much
        winner = home if home['pts'] > away['pts'] else away

        result = {
            'home_team': home['team_name'],
            'away_team': away['team_name'],
            'home_score': home['pts'],
            'away_score': away['pts'],
            'winner': winner['team_name'],
            'margin': margin,  # positive = home won
        }

        # Index by multiple keys for easy lookup
        results[home['team_name']] = result
        results[away['team_name']] = result
        results[f"{home['team_name']} vs {away['team_name']}"] = result

    game_count = len([k for k in results if ' vs ' in k])
    logger.info(f"Found {game_count} completed games")
    return results


def check_spread_cover(pick_team: str, spread: float, home_team: str, margin: int) -> Optional[bool]:
    """
    Check if a spread pick covered.
    spread: the line for the home team (negative = home favored)
    margin: actual home margin (positive = home won)
    """
    if spread is None or margin is None:
        return None

    # Adjusted margin = actual margin + spread
    # If pick is on home team: home covers if margin + spread > 0 (wait, standard: home covers if margin > -spread)
    # spread is from home perspective: home -3.5 means home needs to win by >3.5
    # If we picked the home team: they cover if margin > abs(spread) when spread is negative
    # Simpler: adjusted_margin = margin + spread. If > 0, home covered. If < 0, away covered.
    
    adjusted = margin + spread  # positive = home beat the spread
    
    if pick_team == home_team:
        return adjusted > 0
    else:
        return adjusted < 0


def score_individual_picks(game_date: str, conn: sqlite3.Connection, picks: List[Dict]) -> Dict[str, Any]:
    """Score individual game picks (moneyline + spread) against actual results."""
    results = fetch_game_results(game_date)

    if not results:
        logger.warning(f"No game results found for {game_date}")
        return {'error': 'No game results available'}

    c = conn.cursor()
    
    ml_correct = 0
    ml_total = 0
    spread_correct = 0
    spread_total = 0

    for i, pick in enumerate(picks):
        # Handle both NBA engine formats
        home = normalize_team(pick.get('home', pick.get('home_team', '')))
        away = normalize_team(pick.get('away', pick.get('away_team', '')))
        predicted = normalize_team(pick.get('pick', pick.get('predicted_winner', '')))
        confidence = pick.get('win_prob', pick.get('confidence', pick.get('win_probability', 0)))
        spread = pick.get('spread')
        value_score = pick.get('value_score', 0)
        pick_label = pick.get('pick_label', '')
        upset_score = pick.get('upset_score', pick.get('upset_potential', 0))

        # Find actual result
        game_result = results.get(home) or results.get(away)
        if not game_result:
            logger.warning(f"  No result found for {away} @ {home}")
            continue

        actual_winner = game_result['winner']
        margin = game_result['margin']
        ml_hit = (actual_winner == predicted)
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

        emoji = "✅" if ml_hit else "❌"
        spread_emoji = ""
        if spread_hit is not None:
            spread_emoji = f" | Spread {'✅' if spread_hit else '❌'} ({spread:+.1f})"
        
        logger.info(f"  {emoji} {away} @ {home}: picked {predicted} "
                     f"({confidence:.1%}) | Actual: {actual_winner} "
                     f"({game_result['away_score']}-{game_result['home_score']}){spread_emoji}")

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
                game_result['home_score'], game_result['away_score'],
                spread,
                f"{predicted} {spread:+.1f}" if spread else None,
                1 if spread_hit else (0 if spread_hit is not None else None),
                pick_label, upset_score, value_score,
            ))
        except Exception as e:
            logger.error(f"DB insert error: {e}")

    ml_acc = (ml_correct / ml_total * 100) if ml_total > 0 else 0
    spread_acc = (spread_correct / spread_total * 100) if spread_total > 0 else 0

    # Save daily summary
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
    except Exception as e:
        logger.error(f"Summary insert error: {e}")

    conn.commit()

    summary = {
        'moneyline': {'correct': ml_correct, 'total': ml_total, 'accuracy': round(ml_acc, 1)},
        'spread': {'correct': spread_correct, 'total': spread_total, 'accuracy': round(spread_acc, 1)},
    }

    logger.info(f"\n  Moneyline: {ml_correct}/{ml_total} ({ml_acc:.1f}%)")
    logger.info(f"  Spread:    {spread_correct}/{spread_total} ({spread_acc:.1f}%)")

    return summary


def main():
    parser = argparse.ArgumentParser(description='Score ParlayGuarantee picks against actual NBA results')
    parser.add_argument('--date', type=str, default=None,
                        help='Game date to score (YYYY-MM-DD). Default: yesterday')
    parser.add_argument('--db', type=str, default=None, help='Path to results database')
    parser.add_argument('--archive', action='store_true',
                        help='Archive current picks before scoring')
    args = parser.parse_args()

    game_date = args.date or (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    db_path = Path(args.db) if args.db else DB_PATH

    logger.info(f"=== ParlayGuarantee Result Tracker ===")
    logger.info(f"Scoring picks for: {game_date}")

    if args.archive:
        archive_picks(date.today().isoformat())

    # Load individual picks for the date
    picks = load_picks_for_date(game_date)

    if not picks:
        logger.warning(f"No picks found for {game_date}")
        logger.info("Tip: Run 'python generate_from_odds.py' to generate picks, "
                     "then archive them with --archive before games start.")
        sys.exit(0)

    logger.info(f"Loaded {len(picks)} individual picks for {game_date}")

    # Init DB and score
    conn = init_db(db_path)

    try:
        summary = score_individual_picks(game_date, conn, picks)

        logger.info(f"\n=== Results Summary for {game_date} ===")
        if 'error' not in summary:
            ml = summary['moneyline']
            sp = summary['spread']
            logger.info(f"  Moneyline: {ml['correct']}/{ml['total']} ({ml['accuracy']}%)")
            logger.info(f"  Spread:    {sp['correct']}/{sp['total']} ({sp['accuracy']}%)")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
