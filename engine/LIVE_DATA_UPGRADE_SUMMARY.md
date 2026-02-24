# Live Data Engine Upgrade — 2026-02-20

## Changes Made

### 1. ✅ Line Movement Tracker — `get_line_movement_score()` (NEW)
- Added `get_line_movement_score()` function to `line_movement_tracker.py`
- Compares opening spread (from SQLite snapshots) vs current spread
- Calculates directional movement: toward dog = positive score, toward fav = negative
- Scoring: 3+ pts toward dog = +0.5, 1.5+ pts = +0.3, moved toward fav = -0.15
- Integrated into `find_upset_candidates()` — auto-boosts upset score on sharp dog action

### 2. ✅ Injury Pipeline Fixed
- `tier_engine.py` line ~527: `force_refresh=False` → `force_refresh=True` — injuries ALWAYS fresh
- `injury_scraper.py`: `CACHE_TTL_MINUTES` reduced from 30 → **10 minutes**
- Added `scrape_nba_official_injuries()` — scrapes https://official.nba.com/nba-injury-report-2024-25-season/
- NBA Official data merges as secondary source: updates statuses from CBS/ESPN with authoritative data, adds any missing players

### 3. ✅ Injuries Wired INTO Upset Composite
- `find_upset_candidates()` now accepts `injuries` parameter
- If FAVORITE has a star OUT (from `STAR_IMPACT` dict): upset score boosted +0.3 to +0.6 based on star rating
- If DOG has star OUT: upset score reduced proportionally
- Reasons include player name and status for transparency

### 4. ✅ Line Movement Wired INTO Upset Composite
- Engine takes a line movement snapshot before upset analysis (stores to `line_movement.db`)
- `find_upset_candidates()` calls `get_line_movement_score()` for each game
- Sharp money on dog boosts upset score; money on favorite reduces it
- Movement details stored in each game dict as `game['line_movement']`

### 5. ✅ Real H2H Data
- Added `_fetch_h2h_factor()` method to `TierEngine`
- Fetches actual season series from ESPN schedule API for each matchup
- Replaces the hardcoded `0.5` neutral default
- Dog winning recent H2H = higher upset factor; losing = lower
- Results cached in-memory per session to avoid repeat API calls

### 6. ✅ Fresh Data on Every Run
- Odds: ✅ Already live via Odds API (no change needed)
- Injuries: ✅ Now `force_refresh=True` + 10min cache TTL
- ESPN standings/stats: ✅ Already live — `ReliableDataFetcher.fetch_team_stats()` hits ESPN API directly with no file cache
- Line movement: ✅ New snapshot taken at start of each engine run

## Data Status

| Data Source | Status | Method |
|---|---|---|
| Odds/Spreads | 🟢 LIVE | Odds API on every run |
| Injuries | 🟢 LIVE | CBS + ESPN + Rotowire + NBA Official, 10min cache |
| Team Stats (W/L, PPG, etc.) | 🟢 LIVE | ESPN API on every run |
| H2H Season Series | 🟢 LIVE | ESPN schedule API, per-session cache |
| Line Movement | 🟢 LIVE | Odds API snapshots stored in SQLite |
| Home/Road Splits | 🟢 LIVE | From ESPN standings API |
| Streaks & L10 | 🟢 LIVE | From ESPN standings API |
| 3PT Matchup | 🟡 STATIC | Still defaults to 0.5 (needs shooting stats source) |
| Post-ASB Factor | 🟡 SEMI | Date-based heuristic, not data-driven |
