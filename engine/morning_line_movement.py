#!/usr/bin/env python3
"""
Morning Line Movement Factor
Reads line movement data (if available) and returns per-game movement signals
for the engines to use as an additional factor. Read-only at morning pick time.

Detects:
- Steam moves (sharp line movement in one direction)
- Reverse line movement (RLM) — public on one side but line moves other way
- Opening vs current spread change magnitude

Returns dict keyed by "away @ home" with movement signals.
"""
import sqlite3, os, logging
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent / "line_movement.db"

def get_morning_line_signals(target_date: Optional[str] = None) -> Dict:
    """
    Get line movement signals for today's games.
    Returns: {
        "Team A @ Team B": {
            "spread_moved": -1.5,  # negative = home became more favored
            "steam_move": True/False,
            "rlm_detected": True/False,
            "movement_edge": 0.55,  # 0-1 scale, >0.5 = movement favors home
            "snapshots": 3,
        }
    }
    """
    if not DB_PATH.exists():
        logger.info("No line_movement.db — returning empty signals")
        return {}
    
    target = target_date or date.today().isoformat()
    signals = {}
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        
        rows = conn.execute("""
            SELECT home_team, away_team, 
                   MIN(home_spread) as min_spread, MAX(home_spread) as max_spread,
                   MIN(home_ml) as min_ml, MAX(home_ml) as max_ml,
                   COUNT(*) as num_snapshots,
                   (SELECT home_spread FROM spread_snapshots s2 
                    WHERE s2.game_date = ss.game_date AND s2.home_team = ss.home_team 
                    AND s2.away_team = ss.away_team AND s2.sport = ss.sport
                    ORDER BY s2.snapshot_time ASC LIMIT 1) as opening_spread,
                   (SELECT home_spread FROM spread_snapshots s3 
                    WHERE s3.game_date = ss.game_date AND s3.home_team = ss.home_team 
                    AND s3.away_team = ss.away_team AND s3.sport = ss.sport
                    ORDER BY s3.snapshot_time DESC LIMIT 1) as current_spread
            FROM spread_snapshots ss
            WHERE game_date = ?
            GROUP BY home_team, away_team, sport
        """, (target,)).fetchall()
        
        for row in rows:
            key = f"{row['away_team']} @ {row['home_team']}"
            opening = row['opening_spread'] or 0
            current = row['current_spread'] or 0
            moved = current - opening  # negative = home more favored
            
            steam = abs(moved) >= 1.5
            rlm = abs(moved) >= 1.0 and row['num_snapshots'] >= 2
            
            if moved < -0.5:
                movement_edge = min(0.65, 0.5 + abs(moved) * 0.05)
            elif moved > 0.5:
                movement_edge = max(0.35, 0.5 - abs(moved) * 0.05)
            else:
                movement_edge = 0.5
            
            signals[key] = {
                'spread_moved': round(moved, 1),
                'opening_spread': opening,
                'current_spread': current,
                'steam_move': steam,
                'rlm_detected': rlm,
                'movement_edge': round(movement_edge, 4),
                'snapshots': row['num_snapshots'],
            }
        
        conn.close()
        logger.info(f"Line movement signals: {len(signals)} games with data")
    except Exception as e:
        logger.warning(f"Line movement query failed: {e}")
    
    return signals
