#!/usr/bin/env python3
"""
Bootstrap Tempo self-learning: retroactively score Feb 24 totals picks,
convert to Tempo-compatible format, feed to adaptive learner.
Then run Tempo for today with learned weights.
"""
import json, sys, os, sqlite3, requests, re, math
from pathlib import Path
from datetime import date, timedelta
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).parent))
from adaptive_learner import AdaptiveLearner

ENGINE_DIR = Path(__file__).parent
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Tempo default weights
TEMPO_DEFAULTS = {
    "pace_mismatch": 0.08, "ortg_matchup": 0.10, "drtg_matchup": 0.10,
    "recent_form": 0.08, "rest_b2b": 0.06, "spread_context": 0.05,
    "home_away_splits": 0.05, "streak_momentum": 0.04, "referee_tendency": 0.02,
    "injury_scoring": 0.06, "market_deviation": 0.08, "pace_trend": 0.03,
    "tempo_variance": 0.06, "conference_style": 0.05, "home_court_college": 0.06,
    "three_pt_variance": 0.04, "rivalry_factor": 0.04,
}

def fetch_ncaab_scores(target_date: date):
    """Fetch NCAAB scores from ESPN for a given date."""
    ds = target_date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={ds}&limit=200"
    print(f"Fetching ESPN NCAAB scores for {target_date}...")
    r = requests.get(url, timeout=30)
    data = r.json()
    scores = []
    for ev in data.get("events", []):
        comps = ev.get("competitions", [{}])[0]
        teams = comps.get("competitors", [])
        if len(teams) < 2:
            continue
        home = away = None
        for t in teams:
            info = {
                "team": t.get("team", {}).get("displayName", ""),
                "score": int(t.get("score", 0)),
                "homeAway": t.get("homeAway", "")
            }
            if info["homeAway"] == "home":
                home = info
            else:
                away = info
        if home and away:
            total = home["score"] + away["score"]
            scores.append({
                "home": home["team"], "away": away["team"],
                "home_score": home["score"], "away_score": away["score"],
                "total": total
            })
    print(f"  Found {len(scores)} completed games")
    return scores


def convert_v2_picks_to_tempo(picks):
    """
    Convert ncaab_totals_v2 picks (which have raw factors dict)
    into Tempo-compatible picks with factor_scores.
    We synthesize factor_scores from the raw data.
    """
    converted = []
    for p in picks:
        edge = p.get("edge", 0)
        pick_dir = 1 if p.get("pick") == "OVER" else -1
        factors_raw = p.get("factors", {})
        
        # Create synthetic factor_scores based on what drove the prediction
        # Each factor gets a portion of the total edge proportional to its contribution
        predicted = factors_raw.get("final_predicted", factors_raw.get("base_total", 0))
        posted = p.get("posted_total", 0)
        base = factors_raw.get("base_total", predicted)
        
        # Individual adjustments from the raw factors
        factor_scores = {}
        
        # Pace/tempo → pace_mismatch + tempo_variance
        game_pace = factors_raw.get("game_pace", 68)
        pace_edge = (game_pace - 68) * 0.3  # pace deviation from avg
        factor_scores["pace_mismatch"] = pace_edge * 0.5
        factor_scores["tempo_variance"] = pace_edge * 0.5
        
        # Offense ratings → ortg_matchup
        home_exp = factors_raw.get("home_expected", 74)
        away_exp = factors_raw.get("away_expected", 74)
        expected_total = home_exp + away_exp
        ortg_edge = (expected_total - 148.8) / 10  # normalized
        factor_scores["ortg_matchup"] = ortg_edge * 0.5
        factor_scores["drtg_matchup"] = ortg_edge * 0.5
        
        # Home advantage
        ha = factors_raw.get("home_advantage", 3.5)
        factor_scores["home_court_college"] = (ha - 3.5) * 0.2
        
        # Conference style
        conf_adj = factors_raw.get("conference_adj", 0)
        factor_scores["conference_style"] = conf_adj * 0.1
        
        # Streak
        streak = factors_raw.get("streak_impact", 0)
        factor_scores["streak_momentum"] = streak * 0.1
        factor_scores["recent_form"] = streak * 0.1
        
        # Blowout
        blowout = factors_raw.get("blowout_adj", 0)
        factor_scores["spread_context"] = blowout * 0.1
        
        # Rivalry
        rivalry = factors_raw.get("rivalry_adj", 0)
        factor_scores["rivalry_factor"] = rivalry * 0.1
        
        # Market deviation (our predicted vs posted)
        factor_scores["market_deviation"] = (predicted - posted) / max(posted, 1) * pick_dir
        
        # Fill remaining factors with small neutral values
        for f in TEMPO_DEFAULTS:
            if f not in factor_scores:
                factor_scores[f] = edge * pick_dir * TEMPO_DEFAULTS[f] / sum(TEMPO_DEFAULTS.values())
        
        converted.append({
            "home": p.get("home_team", ""),
            "away": p.get("away_team", ""),
            "pick": p.get("pick"),
            "posted_total": posted,
            "predicted_total": predicted,
            "edge": edge,
            "factor_scores": factor_scores,
        })
    return converted


def normalize_team(name):
    return re.sub(r'[^a-z]', '', name.lower())


def match_and_learn(picks, scores, engine_name="tempo"):
    """Match picks to scores and feed to adaptive learner."""
    learner = AdaptiveLearner(engine_name)
    weights = learner.get_weights(TEMPO_DEFAULTS)
    
    # Build score lookup
    score_lookup = {}
    for s in scores:
        h, a = normalize_team(s["home"]), normalize_team(s["away"])
        score_lookup[f"{h}|{a}"] = s
        score_lookup[f"{a}|{h}"] = s
    
    matched = []
    for p in picks:
        h = normalize_team(p["home"])
        a = normalize_team(p["away"])
        key = f"{h}|{a}"
        score = score_lookup.get(key)
        
        if not score:
            # Fuzzy
            for s in scores:
                sh, sa = normalize_team(s["home"]), normalize_team(s["away"])
                if (h in sh or sh in h) and (a in sa or sa in a):
                    score = s
                    break
        
        if score:
            actual_total = score["total"]
            posted = p["posted_total"]
            actual_result = "OVER" if actual_total > posted else "UNDER"
            covered = (p["pick"] == actual_result)
            matched.append((p, score, covered))
    
    print(f"\nMatched {len(matched)}/{len(picks)} picks to scores")
    
    hits = sum(1 for _, _, c in matched if c)
    misses = len(matched) - hits
    print(f"Results: {hits}-{misses} ({hits/len(matched)*100:.1f}%)")
    print()
    
    # Show each result
    for p, s, covered in matched:
        actual = s["total"]
        emoji = "✅" if covered else "❌"
        print(f"  {emoji} {p['away']} @ {p['home']}: {p['pick']} {p['posted_total']} → Actual {actual} ({'+' if actual > p['posted_total'] else ''}{actual - p['posted_total']:.1f})")
    
    # Feed to learner
    history = learner._load_result_history()
    target_date = date(2026, 2, 24).isoformat()
    
    for p, s, covered in matched:
        entry = {
            "date": target_date,
            "home": p["home"],
            "away": p["away"],
            "pick": p["pick"],
            "spread": p["posted_total"],
            "covered": covered,
            "factor_scores": p["factor_scores"],
            "actual_total": s["total"],
            "posted_total": p["posted_total"],
        }
        history.append(entry)
    
    learner._save_result_history(history)
    
    # Now update weights using the O/U learning logic
    LEARNING_RATE = 0.05
    MIN_WEIGHT = 0.005
    MAX_WEIGHT = 0.25
    RECENCY_HALFLIFE = 14
    today_ord = date.today().toordinal()
    
    factor_hits = {}
    for entry in history:
        try:
            entry_date = date.fromisoformat(entry["date"])
            days_ago = today_ord - entry_date.toordinal()
        except:
            days_ago = 30
        recency = math.exp(-0.693 * days_ago / RECENCY_HALFLIFE)
        cov = entry.get("covered", False)
        
        for factor, edge in entry.get("factor_scores", {}).items():
            if factor not in factor_hits:
                factor_hits[factor] = {"correct": 0.0, "incorrect": 0.0}
            if abs(edge) < 0.02:
                continue
            pick_dir = 1 if entry.get("pick") == "OVER" else -1
            factor_agreed = (edge * pick_dir) > 0
            if (factor_agreed and cov) or (not factor_agreed and not cov):
                factor_hits[factor]["correct"] += recency
            else:
                factor_hits[factor]["incorrect"] += recency
    
    old_weights = deepcopy(weights)
    new_weights = dict(weights)
    
    for factor, stats in factor_hits.items():
        if factor not in new_weights:
            continue
        total_signal = stats["correct"] + stats["incorrect"]
        if total_signal < 1.0:
            continue
        accuracy = stats["correct"] / total_signal
        adjustment = (accuracy - 0.5) * LEARNING_RATE * 2
        new_weights[factor] = max(MIN_WEIGHT, min(MAX_WEIGHT, new_weights[factor] + adjustment))
    
    # Normalize
    total = sum(new_weights.values())
    new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}
    
    # Save weights
    weights_file = ENGINE_DIR / "learned_weights" / "tempo_weights.json"
    meta = {
        "engine": "tempo",
        "last_update": date.today().isoformat(),
        "total_games_learned": len(history),
        "today_record": f"{hits}/{len(matched)}",
        "today_accuracy": round(hits / len(matched), 4) if matched else 0,
        "weights": new_weights,
    }
    with open(weights_file, "w") as f:
        json.dump(meta, f, indent=2)
    
    # Save snapshot
    history_file = ENGINE_DIR / "learned_weights" / "history" / f"tempo_{date.today().isoformat()}.json"
    with open(history_file, "w") as f:
        json.dump(meta, f, indent=2)
    
    print(f"\n📊 Weights updated and saved!")
    print(f"\nWeight changes:")
    for k in sorted(new_weights):
        old = old_weights.get(k, 0)
        new = new_weights[k]
        if abs(new - old) > 0.001:
            arrow = "↑" if new > old else "↓"
            print(f"  {k}: {old:.4f} → {new:.4f} {arrow}")
    
    return new_weights


if __name__ == "__main__":
    # Step 1: Load Feb 24 picks
    picks_file = ENGINE_DIR / "ncaab_totals_picks_v2_2026-02-24.json"
    print(f"Loading picks from {picks_file}")
    with open(picks_file) as f:
        raw_picks = json.load(f)
    print(f"  {len(raw_picks)} picks loaded")
    
    # Step 2: Convert to Tempo format
    tempo_picks = convert_v2_picks_to_tempo(raw_picks)
    print(f"  {len(tempo_picks)} converted to Tempo format")
    
    # Step 3: Fetch actual scores
    scores = fetch_ncaab_scores(date(2026, 2, 24))
    
    # Step 4: Match and learn
    new_weights = match_and_learn(tempo_picks, scores)
    
    print(f"\n✅ Tempo is now self-learning! Run 'python ncaab_ou_tempo.py' for today's picks with learned weights.")
