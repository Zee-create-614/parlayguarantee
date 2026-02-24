# Time Window Fix — Feb 21, 2026

## Problem
Parlay picks combined games from different time slots (e.g., Louisville at 2:15 PM + Gonzaga at 9 PM).
DraftKings won't let customers add already-started games to a parlay slip, so parlays mixing early/late games were unplaceable.

## Solution
Added time-window grouping to ALL parlay generation paths. Games are grouped into windows and only combined within the same window.

### Time Windows
- **Early** (12–6 PM ET): Afternoon games (mostly NCAAB)
- **Late** (6 PM+ ET): Evening games (NBA + NCAAB)
- **Full Slate**: All games combined (only when all start after cutoff)

### Buffer Rule
Games must start at least **60 minutes** after pick publication time. This gives customers time to:
1. Receive the picks
2. Open DraftKings
3. Build the parlay slip
4. Place the bet

## Files Changed

### New Files
- `engine/time_windows.py` — Shared utility: window classification, game filtering, validation
- `engine/daily_mega_run.py` — New generalized daily runner (replaces hardcoded `mega_run_feb21.py`)
- `engine/TIME_WINDOW_FIX_SUMMARY.md` — This file

### Modified Files
- `engine/tier_engine_v2.py`
  - `analyze_game()` now includes `commence_time` (ISO UTC) in output
  - `generate_parlays()` now groups games by time window before combining
  - Parlays include `window` and `window_label` fields

- `src/lib/parlay-engine.ts` (TypeScript live engine)
  - Added `ParlayWindow` type, `classifyWindow()`, `isGameEligible()`, `groupEventsByWindow()`
  - `generateParlays()` now generates per-window parlays
  - `generateUniqueParlay()` now accepts `preferredWindow` param and filters by eligibility
  - `getAvailableGameCount()` only counts eligible games
  - `Parlay` interface includes `window` and `windowLabel` fields

- `src/app/api/picks/route.ts` (Customer API)
  - `generateUserParlays()` now groups games by window before building parlays
  - Added `isGameEligibleForParlay()` — filters games starting within 60 min
  - Each parlay includes `window` and `window_label` in API response
  - Added `classifyGameWindow()` and `groupGamesByWindow()` helpers

## How It Works (3 PM Cron)
1. `daily_mega_run.py --publish-hour 15` runs at 3 PM ET
2. Fetches all upcoming games from Odds API
3. Filters out games starting before 4 PM ET (3 PM + 60 min buffer)
4. Groups remaining games into Early/Late windows
5. Generates parlays ONLY within same-window games
6. Labels each parlay with its window for customer clarity

## Output Format Change
Each parlay now includes:
```json
{
  "window": "late",
  "window_label": "🌙 Late Window (6 PM+ ET)",
  "legs": [...]
}
```

Each leg now includes `commence_time` (ISO UTC).
