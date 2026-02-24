"""
TONIGHT ONLY — evening games (6 PM EST+) that match DraftKings availability.
Lean output, no bloated files.
"""
import sys, json, itertools, requests, os
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DIR = os.path.dirname(__file__)
API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

# Only games tipping off 6PM EST (23:00 UTC) or later today
# This matches what DK would show as upcoming evening slate
EST_CUTOFF_HOUR = 18  # 6 PM EST
UTC_CUTOFF = datetime(2026, 2, 20, 23, 0, tzinfo=timezone.utc)  # 6PM EST = 11PM UTC
UTC_END = datetime(2026, 2, 21, 8, 0, tzinfo=timezone.utc)  # cap at 3AM EST

TANK_TEAMS = {"Washington Wizards", "Charlotte Hornets", "Brooklyn Nets", "Portland Trail Blazers", "Utah Jazz"}

def fetch(sport):
    r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds/",
        params={"apiKey": API_KEY, "regions": "us", "markets": "h2h,spreads,totals", "dateFormat": "iso"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    remaining = r.headers.get("x-requests-remaining", "?")
    evening = [g for g in data 
               if UTC_CUTOFF <= datetime.fromisoformat(g["commence_time"].replace("Z","+00:00")) <= UTC_END]
    print(f"  {sport}: {len(evening)} evening games (of {len(data)} total, API remaining: {remaining})")
    return evening

def avg_odds(bms, key, team):
    p = [o["price"] for bm in bms for m in bm.get("markets",[]) if m["key"]==key for o in m["outcomes"] if o["name"]==team]
    return sum(p)/len(p) if p else None

def avg_spread(bms, team):
    p = [o.get("point",0) for bm in bms for m in bm.get("markets",[]) if m["key"]=="spreads" for o in m["outcomes"] if o["name"]==team]
    return sum(p)/len(p) if p else 0

def get_ou(bms):
    lines, over_fav, total_bk = [], 0, 0
    for bm in bms:
        for m in bm.get("markets",[]):
            if m["key"]=="totals":
                for o in m["outcomes"]:
                    if o["name"]=="Over":
                        lines.append(o.get("point",0))
                        total_bk += 1
                        if o.get("price",-110) < -110: over_fav += 1
    if not lines: return None
    avg = sum(lines)/len(lines)
    pick = "OVER" if over_fav > total_bk/2 else "UNDER"
    conf = 0.52 + ((over_fav if pick=="OVER" else total_bk-over_fav)/total_bk * 0.18) if total_bk else 0.52
    return {"line": round(avg,1), "pick": pick, "confidence": round(conf,4)}

def build_spread(odds, sport):
    games = []
    for g in odds:
        h, a, bm = g["home_team"], g["away_team"], g.get("bookmakers",[])
        hh, ah = avg_odds(bm,"h2h",h), avg_odds(bm,"h2h",a)
        if not hh or not ah: continue
        rh, ra = 1/hh, 1/ah
        t = rh+ra
        hp, ap = rh/t, ra/t
        sp = avg_spread(bm, h)
        pick, wp = (h,hp) if hp>=ap else (a,ap)
        ct = g.get("commence_time","")
        dt = datetime.fromisoformat(ct.replace("Z","+00:00")) - timedelta(hours=5)
        games.append({"home":h,"away":a,"pick":pick,"win_prob":round(wp,4),"spread":round(sp,1),
                      "sport":sport,"type":"spread","time":dt.strftime("%I:%M %p"),"ct":ct})
    return sorted(games, key=lambda x:x["ct"])

def build_ou(odds, sport):
    games = []
    for g in odds:
        h, a, bm = g["home_team"], g["away_team"], g.get("bookmakers",[])
        td = get_ou(bm)
        if not td: continue
        ct = g.get("commence_time","")
        dt = datetime.fromisoformat(ct.replace("Z","+00:00")) - timedelta(hours=5)
        games.append({"home":h,"away":a,"pick":td["pick"],"win_prob":td["confidence"],
                      "total_line":td["line"],"sport":sport,"type":"over_under",
                      "time":dt.strftime("%I:%M %p"),"ct":ct})
    return sorted(games, key=lambda x:x["ct"])

def gen_parlays(games, product, max_legs=None):
    n = len(games)
    if max_legs is None:
        max_legs = min(n, 9)  # reasonable cap
    if n > 20: max_legs = min(max_legs, 4)
    elif n > 15: max_legs = min(max_legs, 5)
    
    out = {"date":"2026-02-20","product":product,"total_games":n,"games":games,"bets":{},"summary":{}}
    total = hc = 0
    for legs in range(1, min(max_legs+1, n+1)):
        tier = "single" if legs==1 else f"{legs}leg"
        bets = []
        for ci, combo in enumerate(itertools.combinations(range(n), legs)):
            picks = [games[i] for i in combo]
            prob = 1.0
            for p in picks: prob *= p["win_prob"]
            payout = round(100/prob,2) if prob>0 else 0
            ahc = all(p["win_prob"]>=0.60 for p in picks)
            if ahc: hc+=1
            bets.append({"bet_id":f"{product}_{tier}_{ci+1:04d}","legs":legs,
                "picks":[{"home":p["home"],"away":p["away"],"pick":p["pick"],
                          "win_prob":p["win_prob"],"sport":p["sport"],"type":p["type"],
                          "spread":p.get("spread"),"total_line":p.get("total_line"),
                          "time":p.get("time","")} for p in picks],
                "combined_prob":round(prob,6),"payout_per_100":payout,
                "all_high_conf":ahc,"result":None})
        bets.sort(key=lambda x:x["combined_prob"], reverse=True)
        out["bets"][tier] = bets
        total += len(bets)
        print(f"    {tier}: {len(bets):,}")
    out["summary"] = {"total_bets":total,"by_tier":{k:len(v) for k,v in out["bets"].items()},"high_conf":hc}
    return out

def save(data, fn):
    p = os.path.join(DIR, fn)
    json.dump(data, open(p,"w",encoding="utf-8"), separators=(',',':'), ensure_ascii=False)
    print(f"    -> {fn} ({os.path.getsize(p)/1024:.0f} KB, {data['summary']['total_bets']:,} bets)")

def main():
    print("=" * 60)
    print("TONIGHT'S SLATE — EVENING GAMES ONLY (6PM EST+)")
    print("=" * 60)

    print("\nFetching odds...")
    nba_raw = fetch("basketball_nba")
    ncaab_raw = fetch("basketball_ncaab")

    nba_sp = build_spread(nba_raw, "NBA")
    nba_ou = build_ou(nba_raw, "NBA")
    ncaab_sp = build_spread(ncaab_raw, "NCAAB")
    ncaab_ou = build_ou(ncaab_raw, "NCAAB")

    print(f"\n  NBA:   {len(nba_sp)} spread, {len(nba_ou)} O/U")
    print(f"  NCAAB: {len(ncaab_sp)} spread, {len(ncaab_ou)} O/U")
    
    print("\n--- NBA SPREAD ---")
    for g in nba_sp: print(f"  {g['time']} {g['away']} @ {g['home']} -> {g['pick']} ({g['win_prob']:.0%})")
    print("\n--- NBA O/U ---")
    for g in nba_ou: print(f"  {g['time']} {g['away']} @ {g['home']} -> {g['pick']} {g['total_line']} ({g['win_prob']:.0%})")
    print("\n--- NCAAB SPREAD ---")
    for g in ncaab_sp: print(f"  {g['time']} {g['away']} @ {g['home']} -> {g['pick']} ({g['win_prob']:.0%})")
    print("\n--- NCAAB O/U ---")
    for g in ncaab_ou: print(f"  {g['time']} {g['away']} @ {g['home']} -> {g['pick']} {g['total_line']} ({g['win_prob']:.0%})")

    products = {}
    print("\n" + "=" * 60)
    
    if nba_sp:
        print("\n1. NBA Spread")
        d = gen_parlays(nba_sp, "nba_spread")
        save(d, "tonight_nba_spread_2026-02-20.json")
        products["NBA Spread"] = d["summary"]["total_bets"]

    if nba_ou:
        print("\n2. NBA O/U")
        d = gen_parlays(nba_ou, "nba_ou")
        save(d, "tonight_nba_ou_2026-02-20.json")
        products["NBA O/U"] = d["summary"]["total_bets"]

    if ncaab_sp:
        print("\n3. NCAAB Spread")
        d = gen_parlays(ncaab_sp, "ncaab_spread")
        save(d, "tonight_ncaab_spread_2026-02-20.json")
        products["NCAAB Spread"] = d["summary"]["total_bets"]

    if ncaab_ou:
        print("\n4. NCAAB O/U")
        d = gen_parlays(ncaab_ou, "ncaab_ou")
        save(d, "tonight_ncaab_ou_2026-02-20.json")
        products["NCAAB O/U"] = d["summary"]["total_bets"]

    if nba_sp and nba_ou:
        print("\n5. NBA Mixed (Spread+O/U)")
        d = gen_parlays(nba_sp + nba_ou, "nba_mixed", max_legs=8)
        save(d, "tonight_nba_mixed_2026-02-20.json")
        products["NBA Mixed"] = d["summary"]["total_bets"]

    if ncaab_sp and ncaab_ou:
        print("\n6. NCAAB Mixed (Spread+O/U)")
        d = gen_parlays(ncaab_sp + ncaab_ou, "ncaab_mixed", max_legs=4)
        save(d, "tonight_ncaab_mixed_2026-02-20.json")
        products["NCAAB Mixed"] = d["summary"]["total_bets"]

    if nba_sp and ncaab_sp:
        print("\n7. Cross-Sport Spreads")
        d = gen_parlays(nba_sp + ncaab_sp, "cross_sport", max_legs=5)
        save(d, "tonight_cross_sport_2026-02-20.json")
        products["Cross-Sport"] = d["summary"]["total_bets"]

    if nba_sp and nba_ou and ncaab_sp and ncaab_ou:
        print("\n8. Ultimate Mixed")
        d = gen_parlays(nba_sp + nba_ou + ncaab_sp + ncaab_ou, "ultimate_mixed", max_legs=4)
        save(d, "tonight_ultimate_mixed_2026-02-20.json")
        products["Ultimate Mixed"] = d["summary"]["total_bets"]

    print("\n" + "=" * 60)
    print("TONIGHT'S REAL NUMBERS (Evening Slate Only)")
    print("=" * 60)
    grand = 0
    for name, count in products.items():
        print(f"  {name:<25} {count:>10,}")
        grand += count
    print("-" * 60)
    print(f"  {'TOTAL':<25} {grand:>10,}")
    print(f"\n  Revenue if every parlay sold @ $7.50 avg: ${grand*7.5:,.0f}")
    print("=" * 60)

if __name__ == "__main__":
    main()
