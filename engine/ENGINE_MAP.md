# ENGINE MAP — ParlayGuarantee Pick Engines
> Updated: Feb 23, 2026. Keep this file current when adding/removing engines.

## ACTIVE ENGINES

### Spread / Moneyline
| File | Purpose | Status |
|------|---------|--------|
| `autopilot.py` | Main daily pipeline. Odds-consensus picks + upset composite + injury adj + factor adjustments | ✅ LIVE |
| `nba_upset_composite.py` | NBA upset detection (called by autopilot) | ✅ LIVE |
| `factor_adjuster.py` | Applies learned weight adjustments to spread picks (called by autopilot) | ✅ LIVE |

### Over/Under (Totals)
| File | Purpose | Status |
|------|---------|--------|
| `totals_engine_v3.py` | **V3.1** — Core O/U engine. Market-blended with DRtg dampen, ORtg boost, pace reduction. Toggle: `USE_V31` | ✅ LIVE |
| `ou_adaptive_engine.py` | **V4** — O/U self-learning. Analyzes O/U results, learns factor weights, detects bias | ✅ NEW |

### Learning / Self-Improvement
| File | Purpose | Status |
|------|---------|--------|
| `adaptive_engine.py` | Spread/ML self-learning (13 weight adjustments). Run weekly. | ✅ LIVE |
| `engine_learner.py` | Bayesian per-factor weight tracking | ✅ LIVE |
| `self_learner.py` | Base factor weight system (predictions DB) | ✅ LIVE |
| `adaptive_factors.py` | Seasonal awareness, degraded factor detection | ✅ LIVE |
| `roster_tracker.py` | NBA trades/injuries, NCAAB transfers tracking | ✅ LIVE |

### Support
| File | Purpose |
|------|---------|
| `result_tracker.py` | Scores yesterday's picks vs actual outcomes |
| `injury_scraper.py` | CBS Sports injury data |
| `odds_fetcher.py` | Odds API wrapper |
| `team_name_mapper.py` | Fuzzy team name matching |
| `push_to_turso.py` | Push picks to Turso cloud DB |

### Weight Files
| File | Purpose |
|------|---------|
| `learned_weights.json` | Spread/ML learned factor weights (from adaptive_engine) |
| `ou_learned_weights.json` | O/U learned weights (from ou_adaptive_engine) |
| `ou_learning_log.json` | Last O/U learning cycle report |
| `learning_log.json` | Last spread/ML learning cycle report |

## CLEANUP LOG
- **2026-02-23**: Archived 475 files and 9 directories into `archive/cleanup_20260223/`. Kept 75 active files. Old picks, backtests, debug scripts, one-off generators, old engine versions, dated outputs, logs, and unused scripts all moved to archive.

## ARCHIVED (in `archive/old_ou_engines/`)
- `totals_engine.py` (V1), `totals_engine_v2.py` (V2), `totals_model.py`, `demo_totals_model.py`
- `ncaab_totals_engine.py`, `ncaab_totals_engine_v2.py`
- `backtest_ou_v2.py`, `totals_backtest.py`
- Various test scripts

## KEY RULES
1. **Autopilot runs ONCE per day at 10 AM.** Never re-run it.
2. **Morning picks are source of truth.** Later crons READ from morning files only.
3. **V3.1 toggle:** Set `USE_V31 = False` in `totals_engine_v3.py` to revert O/U to V3.
4. **Factor adjuster toggle:** Remove import in `autopilot.py` to disable learned weight adjustments.
5. **All old O/U engines archived.** Only V3.1 and V4 adaptive are active.
