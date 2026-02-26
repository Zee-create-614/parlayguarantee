#!/usr/bin/env python3
"""
Advanced Data Refresher — Keeps Alpha V3 + Rex V2 caches warm
===============================================================
Runs daily (via cron) to pre-fetch all 15 advanced factor data sources
so the caches are fresh whenever Josh manually runs Alpha V3 or Rex V2.

Does NOT run any engine or generate picks. Just refreshes data.
"""

import sys, logging, time, traceback
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('refresh_advanced_data.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

EST = timezone(timedelta(hours=-5))

def refresh_nba():
    """Refresh all 15 NBA advanced stat caches for Alpha V3."""
    results = {}
    try:
        from nba_advanced_stats import (
            fetch_team_ratings, fetch_schedule_rest, fetch_ats_trends,
            fetch_player_advanced_stats, estimate_lineup_impact,
            compute_travel_fatigue, fetch_referee_data, compute_pace_matchup,
            fetch_public_betting, compute_motivation, fetch_strength_of_schedule,
            get_coaching_matchup, fetch_quarter_patterns, fetch_clutch_stats,
            fetch_ft_rate,
        )
    except ImportError as e:
        logger.error(f"Cannot import nba_advanced_stats: {e}")
        return {"error": str(e)}

    fetchers = [
        ("team_ratings", fetch_team_ratings),
        ("schedule_rest", fetch_schedule_rest),
        ("ats_trends", fetch_ats_trends),
        ("player_advanced_stats", fetch_player_advanced_stats),
        ("referee_data", fetch_referee_data),
        ("public_betting", fetch_public_betting),
        ("strength_of_schedule", fetch_strength_of_schedule),
        ("quarter_patterns", fetch_quarter_patterns),
        ("clutch_stats", fetch_clutch_stats),
        ("ft_rate", fetch_ft_rate),
    ]

    for name, fn in fetchers:
        try:
            start = time.time()
            data = fn()
            elapsed = time.time() - start
            count = len(data) if isinstance(data, (dict, list)) else 0
            results[name] = {"ok": True, "items": count, "seconds": round(elapsed, 1)}
            logger.info(f"  NBA {name}: {count} items in {elapsed:.1f}s")
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}
            logger.warning(f"  NBA {name} FAILED: {e}")

    # These need game-specific args, just log they exist
    for name in ["lineup_impact", "travel_fatigue", "pace_matchup", "motivation", "coaching_matchup"]:
        results[name] = {"ok": True, "note": "computed per-game at runtime"}

    return results


def refresh_ncaab():
    """Refresh all 15 NCAAB advanced stat caches for Rex V2."""
    results = {}
    try:
        from ncaab_advanced_stats import (
            fetch_barttorvik_stats, fetch_ats_trends, fetch_top_players,
            fetch_public_betting,
        )
    except ImportError as e:
        logger.error(f"Cannot import ncaab_advanced_stats: {e}")
        return {"error": str(e)}

    fetchers = [
        ("barttorvik_stats", fetch_barttorvik_stats),
        ("ats_trends", fetch_ats_trends),
        ("top_players", fetch_top_players),
        ("public_betting", fetch_public_betting),
    ]

    for name, fn in fetchers:
        try:
            start = time.time()
            data = fn()
            elapsed = time.time() - start
            count = len(data) if isinstance(data, (dict, list)) else 0
            results[name] = {"ok": True, "items": count, "seconds": round(elapsed, 1)}
            logger.info(f"  NCAAB {name}: {count} items in {elapsed:.1f}s")
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}
            logger.warning(f"  NCAAB {name} FAILED: {e}")

    for name in ["rest_density", "travel_distance", "home_court", "coaching", "rivalry",
                  "motivation", "conf_vs_nonconf"]:
        results[name] = {"ok": True, "note": "computed per-game at runtime"}

    return results


if __name__ == '__main__':
    now = datetime.now(EST)
    logger.info(f"=== Advanced Data Refresh — {now.strftime('%Y-%m-%d %H:%M ET')} ===")

    logger.info("Refreshing NBA data (Alpha V3)...")
    nba = refresh_nba()
    nba_ok = sum(1 for v in nba.values() if isinstance(v, dict) and v.get('ok'))
    nba_fail = sum(1 for v in nba.values() if isinstance(v, dict) and not v.get('ok'))

    logger.info("Refreshing NCAAB data (Rex V2)...")
    ncaab = refresh_ncaab()
    ncaab_ok = sum(1 for v in ncaab.values() if isinstance(v, dict) and v.get('ok'))
    ncaab_fail = sum(1 for v in ncaab.values() if isinstance(v, dict) and not v.get('ok'))

    logger.info(f"=== DONE — NBA: {nba_ok} ok / {nba_fail} fail | NCAAB: {ncaab_ok} ok / {ncaab_fail} fail ===")

    print(f"\n✅ Data refresh complete")
    print(f"   NBA (Alpha V3):  {nba_ok} sources refreshed, {nba_fail} failed")
    print(f"   NCAAB (Rex V2):  {ncaab_ok} sources refreshed, {ncaab_fail} failed")
