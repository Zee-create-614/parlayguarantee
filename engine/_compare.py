import json

# Morning picks (7:49 AM)
morning = json.load(open("picks_2026-02-22/ncaab_spread_picks.json"))
# Afternoon re-run (4:02 PM) 
afternoon = json.load(open("picks_2026-02-22/ncaab_picks.json"))
# Current analyzed_games.json
current = json.load(open("analyzed_games.json"))

print("=== MORNING NCAAB SPREAD PICKS (7:49 AM) ===")
for g in morning[:10]:
    away = g.get("away_team", g.get("away", "?"))
    home = g.get("home_team", g.get("home", "?"))
    conf = g.get("confidence", g.get("win_probability", g.get("prob", "?")))
    spread = g.get("spread", "?")
    print(f"  {away} vs {home} | spread={spread} | conf={conf}")

print(f"\n  Total: {len(morning)} picks")

print("\n=== AFTERNOON NCAAB PICKS (4:02 PM) ===")
for g in afternoon[:10]:
    away = g.get("away_team", g.get("away", "?"))
    home = g.get("home_team", g.get("home", "?"))
    conf = g.get("confidence", g.get("win_probability", g.get("prob", "?")))
    spread = g.get("spread", "?")
    print(f"  {away} vs {home} | spread={spread} | conf={conf}")

print(f"\n  Total: {len(afternoon)} picks")

print("\n=== CURRENT analyzed_games.json ===")
for g in current[:10]:
    away = g.get("away_team", g.get("away", "?"))
    home = g.get("home_team", g.get("home", "?"))
    conf = g.get("confidence", g.get("win_probability", g.get("prob", "?")))
    spread = g.get("spread", "?")
    print(f"  {away} vs {home} | spread={spread} | conf={conf}")

print(f"\n  Total: {len(current)} games")

# Check morning NBA too
nba_morning = json.load(open("picks_2026-02-22/nba_spread_picks.json"))
nba_afternoon = json.load(open("picks_2026-02-22/nba_picks.json"))
print("\n=== MORNING NBA SPREAD PICKS ===")
for g in nba_morning[:5]:
    away = g.get("away_team", g.get("away", "?"))
    home = g.get("home_team", g.get("home", "?"))
    conf = g.get("confidence", g.get("win_probability", g.get("prob", "?")))
    print(f"  {away} vs {home} | conf={conf}")

print(f"\n=== AFTERNOON NBA PICKS ===")
for g in nba_afternoon[:5]:
    away = g.get("away_team", g.get("away", "?"))
    home = g.get("home_team", g.get("home", "?"))
    conf = g.get("confidence", g.get("win_probability", g.get("prob", "?")))
    print(f"  {away} vs {home} | conf={conf}")
