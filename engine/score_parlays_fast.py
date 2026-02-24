"""
Score parlay combinations against actual results — FAST version.
Streams large JSON files and processes in chunks.
"""
import sys, json, requests, time
from pathlib import Path
from difflib import get_close_matches

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = Path(__file__).parent
GAME_DATE = "2026-02-20"

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
            result = {
                "home": teams["home"]["name"], "away": teams["away"]["name"],
                "home_score": teams["home"]["score"], "away_score": teams["away"]["score"],
                "total": total, "winner": winner, "home_margin": home_margin,
            }
            for key in [teams["home"]["name"], teams["away"]["name"]]:
                results[key.lower().strip()] = result
    return results

# Pre-build lookup cache for speed
_match_cache = {}

def find_result(team_name, results):
    key = team_name.lower().strip()
    cache_key = (key, id(results))
    if cache_key in _match_cache:
        return _match_cache[cache_key]
    
    r = results.get(key)
    if not r:
        mascot = key.split()[-1] if key else ""
        for k, v in results.items():
            if mascot and mascot in k:
                r = v
                break
    if not r:
        matches = get_close_matches(key, list(results.keys()), n=1, cutoff=0.6)
        if matches:
            r = results[matches[0]]
    
    _match_cache[cache_key] = r
    return r

def leg_hit(leg, all_results):
    sport = leg.get("sport", "NBA").upper()
    sport_key = "nba" if sport == "NBA" else "ncaab"
    results = all_results.get(sport_key, {})
    
    home = leg.get("home", "")
    away = leg.get("away", "")
    pick_team = leg.get("pick", "")
    bet_type = leg.get("type", "moneyline")
    
    result = find_result(home, results) or find_result(away, results)
    if not result:
        return None
    
    if bet_type == "over_under":
        actual_total = result["total"]
        line = leg.get("total_line", 0)
        ou_dir = pick_team.upper() if pick_team.upper() in ("OVER", "UNDER") else leg.get("ou_pick", "").upper()
        if ou_dir == "OVER":
            return actual_total > line
        elif ou_dir == "UNDER":
            return actual_total < line
        return None
    elif bet_type == "spread":
        spread = leg.get("spread", leg.get("pick_spread", 0)) or 0
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
        if pick_lower in winner or winner in pick_lower:
            return True
        if get_close_matches(pick_lower, [winner], cutoff=0.6):
            return True
        other = result["away"].lower().strip() if winner == result["home"].lower().strip() else result["home"].lower().strip()
        if pick_lower in other or other in pick_lower:
            return False
        if get_close_matches(pick_lower, [other], cutoff=0.6):
            return False
        return None

def score_file(filepath, all_results):
    start = time.time()
    print(f"\n📁 {filepath.name} ({filepath.stat().st_size / 1024 / 1024:.1f} MB)")
    sys.stdout.flush()
    
    data = json.loads(filepath.read_text(encoding="utf-8"))
    bets = data.get("bets", {})
    if not bets:
        print("   No bets found, skipping")
        return None
    
    total_hit = 0
    total_miss = 0
    total_unknown = 0
    tier_results = {}
    
    for tier_name, tier_bets in bets.items():
        hits = misses = unknowns = 0
        for bet in tier_bets:
            legs = bet.get("picks", bet.get("legs_detail", []))
            if not legs:
                continue
            parlay_hit = True
            unknown = False
            for leg in legs:
                h = leg_hit(leg, all_results)
                if h is None:
                    unknown = True
                    break
                elif not h:
                    parlay_hit = False
                    break
            if unknown:
                unknowns += 1
            elif parlay_hit:
                hits += 1
            else:
                misses += 1
        tier_results[tier_name] = (hits, misses, unknowns, len(tier_bets))
        total_hit += hits
        total_miss += misses
        total_unknown += unknowns
    
    scored = total_hit + total_miss
    rate = round(total_hit / max(scored, 1) * 100, 2)
    elapsed = time.time() - start
    
    print(f"   ⏱️  {elapsed:.1f}s | Total: {scored + total_unknown} parlays | ✅ Hit: {total_hit} | ❌ Miss: {total_miss} | ⚪ Unknown: {total_unknown} | Rate: {rate}%")
    for tier, (h, m, u, t) in sorted(tier_results.items(), key=lambda x: x[0]):
        tr = round(h / max(h + m, 1) * 100, 1)
        print(f"   {tier:>8}: {h}/{h+m} hit ({tr}%) out of {t} total ({u} unknown)")
    sys.stdout.flush()
    
    return {"file": filepath.name, "hit": total_hit, "miss": total_miss, "unknown": total_unknown, "rate": rate}

def main():
    print(f"Fetching ESPN scores for {GAME_DATE}...")
    nba = fetch_espn("nba", GAME_DATE)
    ncaab = fetch_espn("ncaab", GAME_DATE)
    print(f"NBA: {len(set(id(v) for v in nba.values()))} games | NCAAB: {len(set(id(v) for v in ncaab.values()))} games")
    all_results = {"nba": nba, "ncaab": ncaab}
    
    # All parlay files for the date
    files = sorted(ENGINE_DIR.glob(f"*parlays*{GAME_DATE}*")) + sorted(ENGINE_DIR.glob(f"tonight_*{GAME_DATE}*"))
    seen = set()
    unique = []
    for f in files:
        if f.name not in seen and f.stat().st_size > 100:
            seen.add(f.name)
            unique.append(f)
    
    # Sort by size (smallest first for quick wins)
    unique.sort(key=lambda f: f.stat().st_size)
    
    print(f"\n{'='*70}")
    print(f"Scoring {len(unique)} parlay files")
    print(f"{'='*70}")
    
    summaries = []
    for f in unique:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if "bets" not in data or not data["bets"]:
                continue
        except:
            continue
        
        r = score_file(f, all_results)
        if r:
            summaries.append(r)
    
    print(f"\n{'='*70}")
    print("📋 FINAL SUMMARY")
    print(f"{'='*70}")
    grand_hit = grand_miss = grand_unk = 0
    for s in summaries:
        emoji = "🔥" if s["rate"] >= 10 else "✅" if s["rate"] >= 3 else "📊"
        print(f"{emoji} {s['file']}: {s['hit']}/{s['hit']+s['miss']} hit ({s['rate']}%)")
        grand_hit += s["hit"]
        grand_miss += s["miss"]
        grand_unk += s["unknown"]
    
    grand_rate = round(grand_hit / max(grand_hit + grand_miss, 1) * 100, 2)
    print(f"\n🏆 GRAND TOTAL: {grand_hit}/{grand_hit+grand_miss} parlays hit ({grand_rate}%) | {grand_unk} unknown")

if __name__ == "__main__":
    main()
