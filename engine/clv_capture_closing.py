#!/usr/bin/env python3
"""Capture closing odds for CLV tracking. Run near tipoff times."""
import sys
from clv_tracker import capture_closing_odds

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

nba_updated = capture_closing_odds("basketball_nba")
ncaab_updated = capture_closing_odds("basketball_ncaab")
print(f"CLV closing capture: NBA={nba_updated}, NCAAB={ncaab_updated}")
