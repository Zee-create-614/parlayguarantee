# ParlayGuarantee Engine Map

## Spread Engines

| Engine | File | Sport | Learner ID | Factors | Status |
|--------|------|-------|-----------|---------|--------|
| **Alpha** v3 | `nba_engine_alpha_v3.py` | NBA | `alpha` | 20 | ✅ Production |
| **Rex** v2 | `ncaab_engine_rex_v2.py` | NCAAB | `rex` | 12+ | ✅ Production |

## Over/Under Engines

| Engine | File | Sport | Learner ID | Factors | Status |
|--------|------|-------|-----------|---------|--------|
| **Pulse** v1 | `nba_ou_pulse.py` | NBA | `pulse` | 12 | ✅ Production |
| **Tempo** v1 | `ncaab_ou_tempo.py` | NCAAB | `tempo` | 16 | ✅ Production |
| Totals v3 (legacy) | `totals_engine_v3.py` | NBA/NCAAB | — | 4 | ⚠️ Superseded by Pulse/Tempo |

## Self-Learning System

| File | Purpose |
|------|---------|
| `adaptive_learner.py` | Bayesian weight optimizer — shared by all engines |
| `feed_results.py` | Feed spread results → Alpha + Rex (also triggers O/U) |
| `feed_ou_results.py` | Feed O/U results → Pulse + Tempo |

### Weight Storage
```
learned_weights/
  alpha_weights.json      # Alpha spread weights
  rex_weights.json        # Rex spread weights
  pulse_weights.json      # Pulse O/U weights
  tempo_weights.json      # Tempo O/U weights
  alpha_results.json      # Alpha result history (90 days)
  rex_results.json
  pulse_results.json
  tempo_results.json
  history/                # Daily snapshots
```

## CLI Quick Reference

```bash
# Run engines
python nba_engine_alpha_v3.py                  # Alpha NBA spreads
python ncaab_engine_rex_v2.py                  # Rex NCAAB spreads
python nba_ou_pulse.py                         # Pulse NBA O/U
python ncaab_ou_tempo.py                       # Tempo NCAAB O/U

# Specific date
python nba_ou_pulse.py --date 2026-02-25
python ncaab_ou_tempo.py --date 2026-02-25

# Score past predictions
python nba_ou_pulse.py --score 2026-02-24
python ncaab_ou_tempo.py --score 2026-02-24

# Backtest
python nba_ou_pulse.py --backtest 7
python ncaab_ou_tempo.py --backtest 7

# Feed results (daily — run day after games)
python feed_results.py                         # All engines
python feed_ou_results.py                      # O/U engines only
python feed_ou_results.py --summary            # Learning progress

# Legacy
python totals_engine_v3.py                     # Old combined O/U engine
```

## Factor Architecture

### Pulse (NBA O/U) — 12 Factors
| Factor | Weight | Description |
|--------|--------|-------------|
| pace_mismatch | 0.12 | Fast vs slow team matchups |
| ortg_matchup | 0.14 | Offense vs opponent defense |
| drtg_matchup | 0.14 | Defense vs opponent offense |
| recent_form | 0.10 | Streak-based scoring form |
| rest_b2b | 0.08 | Back-to-back / 3-in-4 fatigue |
| spread_context | 0.06 | Blowout → under, tight → over |
| home_away_splits | 0.06 | Home/away scoring patterns |
| streak_momentum | 0.05 | Win/loss streak momentum |
| referee_tendency | 0.03 | High/low whistle crew (stub) |
| injury_scoring | 0.08 | Key scorers out → under |
| market_deviation | 0.10 | Our raw vs Vegas line |
| pace_trend | 0.04 | L10 pace vs season pace |

### Tempo (NCAAB O/U) — 16 Factors
All 12 Pulse factors (adjusted for college) PLUS:
| Factor | Weight | Description |
|--------|--------|-------------|
| tempo_variance | 0.06 | Wide NCAAB pace range (55-75) |
| conference_style | 0.05 | Conference pace profiles |
| home_court_college | 0.06 | Stronger HCA in college (3-4 pts) |
| three_pt_variance | 0.04 | Streakier college 3pt shooting |
| rivalry_factor | 0.04 | Rivalry games → under lean |

## Confidence Tiers
| Tier | Edge | Confidence |
|------|------|------------|
| 🔒 LOCK | ≥5.0 pts | 72% |
| 🎯 STRONG | ≥3.5 pts | 65% |
| 📊 VALUE | ≥2.5 pts | 60% |
| 📈 LEAN | ≥1.5 pts | 56% |
| ⏭️ PASS | <1.5 pts | — |
