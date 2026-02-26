#!/usr/bin/env python3
"""Take a line snapshot for today's games. Run this before morning engine run."""
from line_movement_tracker import init_db, take_snapshot
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

init_db()
for sport in ['nba', 'ncaab']:
    try:
        take_snapshot(sport)
    except Exception as e:
        print(f"Snapshot {sport} failed: {e}")
