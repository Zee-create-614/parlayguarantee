"""
Score all parlay combinations against actual results.
Reads ESPN scores and checks every parlay in every *_parlays_2026-02-20.json file.
"""
import sys, json, sqlite3, requests
from pathlib import Path
from datetime import date
from difflib import get_close_matches

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = Path(__file__).parent
GAME_DATE = "2026-02-20"

# ── Fetch actual results from ESPN ──
def fetch_espn(sport, game_date):
    urls = {
        "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
        "ncaab": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
    }
    params = {"dates": game_date.replace("-", "")}
    if sport == "ncaab":
        params["limit"] = 500
        params["groups"] = 50
    resp = requests.get(urls[sport], params=params, timeout=30)
    resp.raise_for_status()
    results = {}
    for event in resp.json().get("events", []):
        comp = event["competitions"][0]
        if comp["status"]["type"]["name"] != "STATUS_FINAL":
            continue
        teams = {}
        for t in comp["competitors"]:
            name = t["team"]["displayName"]
            score = int(t.get("score", 0))
            ha = t["homeAway"]
            teams[ha] = {"name": name, "score": score}
        if "home" in teams and "away" in teams:
            total = teams["home"]["score"] + teams["away"]["score"]
            winner = teams["home"]["name"] if teams["home"]["score"] > teams["away"]["score"] else teams["away"]["name"]
            home_margin = teams["home"]["score"] - teams["away"]["score"]
            key_home = teams["home"]["name"].lower().strip()
            key_away = teams["away"]["name"].lower().strip()
            result = {
                "home": teams["home"]["name"], "away": teams["away"]["name"],
                "home_score": teams["home"]["score"], "away_score": teams["away"]["score"],
                "total": total, "winner": winner, "home_margin": home_margin,
            }
            results[key_home] = result
            results[key_away] = result
    return results

# ── Fuzzy team lookup ──
def find_result(team_name, results):
    key = team_name.lower().strip()
    if key in results:
        return results[key]
    # Try last word (mascot)
    mascot = key.split()[-1] if key else ""
    for k, v in results.items():
        if mascot and mascot in k:
            return v
    # difflib
    matches = get_close_matches(key, list(results.keys()), n=1, cutoff=0.6)
    if matches:
        return results[matches[0]]
    return None

# ── Check if a single leg hit ──
def leg_hit(pick, results):
    """Returns True if leg hit, False if missed, None if no data."""
    home = pick.get("home", "")
    away = pick.get("away", "")
    pick_team = pick.get("pick", "")
    bet_type = pick.get("type", "moneyline")
    
    # Find the game result
    result = find_result(home, results) or find_result(away, results)
    if not result:
        return None
    
    if bet_type == "over_under":
        actual_total = result["total"]
        line = pick.get("total_line", 0)
        ou_dir = pick_team.upper() if pick_team.upper() in ("OVER", "UNDER") else ""
        if not ou_dir:
            # pick might be the team name for spread, or "OVER"/"UNDER" string
            ou_dir = pick.get("ou_pick", pick.get("pick", "")).upper()
        if ou_dir == "OVER":
            return actual_total > line
        elif ou_dir == "UNDER":
            return actual_total < line
        return None
    
    elif bet_type == "spread":
        spread = pick.get("spread", pick.get("pick_spread", 0))
        if spread is None:
            spread = 0
        # Determine which team was picked
        pick_lower = pick_team.lower().strip()
        home_lower = result["home"].lower().strip()
        if pick_lower in home_lower or home_lower in pick_lower or get_close_matches(pick_lower, [home_lower], cutoff=0.6):
            pick_margin = result["home_margin"]
        else:
            pick_margin = -result["home_margin"]
        return (pick_margin + spread) > 0
    
    else:  # moneyline
        winner = result["winner"].lower().strip()
        pick_lower = pick_team.lower().strip()
        # Fuzzy match winner to pick
        if pick_lower in winner or winner in pick_lower:
            return True
        if get_close_matches(pick_lower, [winner], cutoff=0.6):
            return True
        # Check if pick matches the loser
        loser_home = result["home"].lower().strip()
        loser_away = result["away"].lower().strip()
        other = loser_away if winner == loser_home else loser_home
        if pick_lower in other or other in pick_lower:
            return False
        if get_close_matches(pick_lower, [other], cutoff=0.6):
            return False
        return None

def score_parlay_file(filepath, all_results):
    """Score all parlays in a file. Returns summary dict."""
    data = json.loads(filepath.read_text(encoding="utf-8"))
    bets = data.get("bets", {})
    summary = data.get("summary", {})
    total_bets = summary.get("total_bets", 0)
    product = data.get("product", filepath.stem)
    
    tier_results = {}
    total_hit = 0
    total_miss = 0
    total_unknown = 0
    
    for tier_name, tier_bets in bets.items():
        hits = 0
        misses = 0
        unknowns = 0
        
        for bet in tier_bets:
            legs = bet.get("picks", bet.get("legs_detail", []))
            if not legs:
                continue
            
            all_hit = True
            any_unknown = False
            
            for leg in legs:
                sport = leg.get("sport", "NBA").upper()
                sport_key = "nba" if sport == "NBA" else "ncaab"
                result_set = all_results.get(sport_key, {})
                
                hit = leg_hit(leg, result_set)
                if hit is None:
                    any_unknown = True
                    all_hit = False
                    break
                elif not hit:
                    all_hit = False
                    break
            
            if any_unknown:
                unknowns += 1
            elif all_hit:
                hits += 1
            else:
                misses += 1
        
        tier_results[tier_name] = {"hits": hits, "misses": misses, "unknowns": unknowns, "total": len(tier_bets)}
        total_hit += hits
        total_miss += misses
        total_unknown += unknowns
    
    return {
        "file": filepath.name,
        "product": product,
        "total_bets": total_bets,
        "total_hit": total_hit,
        "total_miss": total_miss,
        "total_unknown": total_unknown,
        "hit_rate": round(total_hit / max(total_hit + total_miss, 1) * 100, 1),
        "tiers": tier_results,
    }

def main():
    print(f"Fetching ESPN scores for {GAME_DATE}...")
    nba_results = fetch_espn("nba", GAME_DATE)
    ncaab_results = fetch_espn("ncaab", GAME_DATE)
    print(f"NBA: {len(set(id(v) for v in nba_results.values()))} games, NCAAB: {len(set(id(v) for v in ncaab_results.values()))} games")
    
    all_results = {"nba": nba_results, "ncaab": ncaab_results}
    
    # Find all parlay files for the date
    parlay_files = sorted(ENGINE_DIR.glob(f"*parlays*{GAME_DATE}*"))
    # Also check tonight_ files
    parlay_files += sorted(ENGINE_DIR.glob(f"tonight_*{GAME_DATE}*"))
    # Deduplicate
    seen = set()
    unique = []
    for f in parlay_files:
        if f.name not in seen:
            seen.add(f.name)
            unique.append(f)
    
    print(f"\nFound {len(unique)} parlay files to score\n")
    print("=" * 70)
    
    all_summaries = []
    for f in unique:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "bets" not in data:
                continue
            print(f"\n📁 {f.name}")
            result = score_parlay_file(f, all_results)
            all_summaries.append(result)
            
            print(f"   Total: {result['total_bets']} parlays | Hit: {result['total_hit']} | Miss: {result['total_miss']} | Unknown: {result['total_unknown']} | Rate: {result['hit_rate']}%")
            for tier, tr in result["tiers"].items():
                if tr["total"] > 0:
                    rate = round(tr["hits"] / max(tr["hits"] + tr["misses"], 1) * 100, 1)
                    print(f"   {tier:>8}: {tr['hits']}/{tr['total']} hit ({rate}%) | {tr['unknowns']} unknown")
        except Exception as e:
            print(f"   ERROR: {e}")
    
    print("\n" + "=" * 70)
    print("📋 SUMMARY OF ALL PARLAY FILES")
    print("=" * 70)
    for s in all_summaries:
        emoji = "🔥" if s["hit_rate"] >= 10 else "✅" if s["hit_rate"] >= 5 else "📊"
        print(f"{emoji} {s['file']}: {s['total_hit']}/{s['total_hit']+s['total_miss']} ({s['hit_rate']}%) of {s['total_bets']} parlays")

if __name__ == "__main__":
    main()
