import json, sys

def format_picks(filepath, sport_label, top_n=None):
    with open(filepath) as f:
        data = json.load(f)
    
    picks = data.get("picks", data) if isinstance(data, dict) else data
    picks_sorted = sorted(picks, key=lambda x: x.get("cover_prob", 0), reverse=True)
    
    if top_n:
        picks_sorted = picks_sorted[:top_n]
    
    print(f"\n{'='*50}")
    print(f"  {sport_label} — FULL PICTURE")
    print(f"{'='*50}\n")
    
    for i, p in enumerate(picks_sorted, 1):
        away = p.get("away", "")
        home = p.get("home", "")
        pick = p.get("pick", "")
        cover = p.get("cover_prob", 0)
        ml = p.get("ml_prob", 0)
        edge = p.get("edge", 0)
        upset_score = p.get("upset_score", 0)
        upset_flip = p.get("upset_flip", False)
        is_upset = p.get("is_upset_play", False)
        time = p.get("game_time", "")
        spread_str = p.get("spread_str", "")
        spread = p.get("spread", 0)
        
        # THE ONE TRUTH: when ML says team wins AND they cover the spread, that's gold
        # ML prob = chance they win outright. Cover prob = chance they beat the spread.
        # The convergence tells you everything.
        ml_cover_agreement = "YES" if ml > 0.55 and cover > 0.52 else "THIN" if ml > 0.50 and cover > 0.50 else "NO"
        
        flag = ""
        if upset_flip:
            flag = " FLIPPED"
        elif is_upset:
            flag = " UPSET PLAY"
        
        # Tier based on convergence
        if ml > 0.65 and cover > 0.54:
            tier = "LOCK"
        elif ml > 0.58 and cover > 0.52:
            tier = "STRONG"
        elif ml > 0.52 and cover > 0.51:
            tier = "LEAN"
        else:
            tier = "FADE"
        
        print(f"{i}. {away} @ {home} | {time}")
        print(f"   PICK: {pick} ({spread_str})")
        print(f"   ML Win Prob: {ml:.1%} | Cover Prob: {cover:.1%} | Edge: {edge:.1%}")
        print(f"   Upset Score: {upset_score} | ML+Cover Agree: {ml_cover_agreement} | Tier: {tier}{flag}")
        print()

base = r"C:\Users\joshs\.openclaw\workspace\parlayguarantee\engine\picks_2026-02-23"
format_picks(f"{base}\\nba_picks.json", "NBA", top_n=None)
format_picks(f"{base}\\ncaab_picks.json", "NCAAB — TOP 15", top_n=15)
