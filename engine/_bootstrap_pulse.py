#!/usr/bin/env python3
"""Bootstrap Pulse self-learning: score Feb 24 NBA O/U picks, feed to AdaptiveLearner."""
import json, sys, os, math, re, requests
from pathlib import Path
from datetime import date
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).parent))
from adaptive_learner import AdaptiveLearner

ENGINE_DIR = Path(__file__).parent

PULSE_DEFAULTS = {
    'pace_mismatch': 0.12, 'ortg_matchup': 0.14, 'drtg_matchup': 0.14,
    'recent_form': 0.10, 'rest_b2b': 0.08, 'spread_context': 0.06,
    'home_away_splits': 0.06, 'streak_momentum': 0.05, 'referee_tendency': 0.03,
    'injury_scoring': 0.08, 'market_deviation': 0.10, 'pace_trend': 0.04,
}

def fetch_nba_scores(target_date: date):
    ds = target_date.strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={ds}"
    print(f"Fetching ESPN NBA scores for {target_date}...")
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
            info = {"team": t.get("team", {}).get("displayName", ""),
                    "score": int(t.get("score", 0)),
                    "homeAway": t.get("homeAway", "")}
            if info["homeAway"] == "home":
                home = info
            else:
                away = info
        if home and away:
            scores.append({"home": home["team"], "away": away["team"],
                          "home_score": home["score"], "away_score": away["score"],
                          "total": home["score"] + away["score"]})
    print(f"  Found {len(scores)} completed games")
    return scores


def convert_v3_picks_to_pulse(picks):
    converted = []
    for p in picks:
        edge = p.get("edge", 0)
        pick_dir = 1 if p.get("pick") == "OVER" else -1
        factors_raw = p.get("factors", {})
        posted = p.get("posted_total", 0)
        predicted = factors_raw.get("predicted", posted + edge)
        
        game_pace = factors_raw.get("game_pace", 97.5)
        pace_edge = (game_pace - 97.5) * 0.3
        
        home_pts = factors_raw.get("home_pts", 112)
        away_pts = factors_raw.get("away_pts", 112)
        expected_total = home_pts + away_pts
        
        factor_scores = {
            "pace_mismatch": pace_edge,
            "ortg_matchup": (expected_total - 224) / 10 * 0.5,
            "drtg_matchup": (expected_total - 224) / 10 * 0.5,
            "recent_form": factors_raw.get("form_adj", 0) * 0.5,
            "rest_b2b": 0,
            "spread_context": factors_raw.get("spread_adj", 0) * 0.3,
            "home_away_splits": (home_pts - 112) * 0.1,
            "streak_momentum": factors_raw.get("form_adj", 0) * 0.3,
            "referee_tendency": 0,
            "injury_scoring": 0,
            "market_deviation": (factors_raw.get("our_raw", posted) - posted) / max(posted, 1) * 10,
            "pace_trend": pace_edge * 0.3,
        }
        
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


def match_and_learn(picks, scores, engine_name="pulse"):
    learner = AdaptiveLearner(engine_name)
    weights = learner.get_weights(PULSE_DEFAULTS)
    
    score_lookup = {}
    for s in scores:
        h, a = normalize_team(s["home"]), normalize_team(s["away"])
        score_lookup[f"{h}|{a}"] = s
        score_lookup[f"{a}|{h}"] = s
    
    matched = []
    for p in picks:
        if p["pick"] in ("PASS", None):
            continue
        h = normalize_team(p["home"])
        a = normalize_team(p["away"])
        score = score_lookup.get(f"{h}|{a}")
        if not score:
            for s in scores:
                sh, sa = normalize_team(s["home"]), normalize_team(s["away"])
                if (h in sh or sh in h) and (a in sa or sa in a):
                    score = s
                    break
        if score:
            actual_total = score["total"]
            actual_result = "OVER" if actual_total > p["posted_total"] else "UNDER"
            covered = (p["pick"] == actual_result)
            matched.append((p, score, covered))
    
    print(f"\nMatched {len(matched)}/{len([p for p in picks if p['pick'] not in ('PASS',None)])} picks to scores")
    
    hits = sum(1 for _, _, c in matched if c)
    print(f"Results: {hits}-{len(matched)-hits} ({hits/len(matched)*100:.1f}%)")
    print()
    
    for p, s, covered in matched:
        actual = s["total"]
        emoji = "✅" if covered else "❌"
        print(f"  {emoji} {p['away']} @ {p['home']}: {p['pick']} {p['posted_total']} → Actual {actual} ({'+' if actual > p['posted_total'] else ''}{actual - p['posted_total']:.1f})")
    
    # Feed to learner
    history = learner._load_result_history()
    target_date = date(2026, 2, 24).isoformat()
    
    for p, s, covered in matched:
        history.append({
            "date": target_date,
            "home": p["home"], "away": p["away"],
            "pick": p["pick"], "spread": p["posted_total"],
            "covered": covered, "factor_scores": p["factor_scores"],
            "actual_total": s["total"], "posted_total": p["posted_total"],
        })
    
    learner._save_result_history(history)
    
    # Update weights
    LEARNING_RATE = 0.05
    MIN_WEIGHT = 0.005
    MAX_WEIGHT = 0.25
    RECENCY_HALFLIFE = 14
    today_ord = date.today().toordinal()
    
    factor_hits = {}
    for entry in history:
        try:
            days_ago = today_ord - date.fromisoformat(entry["date"]).toordinal()
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
    
    total = sum(new_weights.values())
    new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}
    
    hits_count = sum(1 for _, _, c in matched if c)
    meta = {
        "engine": "pulse",
        "last_update": date.today().isoformat(),
        "total_games_learned": len(history),
        "today_record": f"{hits_count}/{len(matched)}",
        "today_accuracy": round(hits_count / len(matched), 4) if matched else 0,
        "weights": new_weights,
    }
    
    weights_file = ENGINE_DIR / "learned_weights" / "pulse_weights.json"
    with open(weights_file, "w") as f:
        json.dump(meta, f, indent=2)
    
    history_file = ENGINE_DIR / "learned_weights" / "history" / f"pulse_{date.today().isoformat()}.json"
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
    picks_file = ENGINE_DIR / "totals_v3_nba_2026-02-24.json"
    print(f"Loading picks from {picks_file}")
    raw_picks = json.load(open(picks_file))
    print(f"  {len(raw_picks)} picks loaded")
    
    pulse_picks = convert_v3_picks_to_pulse(raw_picks)
    scores = fetch_nba_scores(date(2026, 2, 24))
    new_weights = match_and_learn(pulse_picks, scores)
    
    print(f"\n✅ Pulse is now self-learning! Run 'python nba_ou_pulse.py' for today's picks with learned weights.")
