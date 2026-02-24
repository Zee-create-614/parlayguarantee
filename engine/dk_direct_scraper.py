"""
DraftKings Direct Scraper — Playwright API Intercept
Scrapes NCAAB + NBA spreads, totals, moneylines from DK sportsbook.
"""
import sys, json, os, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

DATE_STR = "2026-02-22"
PICKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"picks_{DATE_STR}")
os.makedirs(PICKS_DIR, exist_ok=True)

URLS = {
    "ncaab": "https://sportsbook.draftkings.com/leagues/basketball/ncaab",
    "nba": "https://sportsbook.draftkings.com/leagues/basketball/nba",
}


def parse_dk_api_response(data):
    """Parse DK's new API format: events + markets + selections."""
    events = {e["id"]: e for e in data.get("events", [])}
    markets = data.get("markets", [])
    selections = data.get("selections", [])
    
    # Index selections by marketId
    sel_by_market = {}
    for s in selections:
        mid = s["marketId"]
        sel_by_market.setdefault(mid, []).append(s)
    
    # Index markets by eventId and type
    market_by_event = {}
    for m in markets:
        eid = m["eventId"]
        mtype = m["marketType"]["name"].lower()
        market_by_event.setdefault(eid, {})[mtype] = m
    
    games = []
    for eid, evt in events.items():
        participants = evt.get("participants", [])
        home = next((p for p in participants if p.get("venueRole") == "Home"), None)
        away = next((p for p in participants if p.get("venueRole") == "Away"), None)
        
        if not home or not away:
            continue
        
        home_name = home["name"]
        away_name = away["name"]
        commence = evt.get("startEventDate", "")
        
        mkts = market_by_event.get(eid, {})
        
        game = {
            "home_team": home_name,
            "away_team": away_name,
            "commence_time": commence,
            "spread_home": None,
            "spread_away": None,
            "home_spread_price": None,
            "away_spread_price": None,
            "total": None,
            "over_price": None,
            "under_price": None,
            "home_ml": None,
            "away_ml": None,
        }
        
        # Spread
        if "spread" in mkts:
            sels = sel_by_market.get(mkts["spread"]["id"], [])
            for s in sels:
                if s.get("outcomeType") == "Home":
                    game["spread_home"] = s.get("points")
                    game["home_spread_price"] = s["displayOdds"]["american"]
                elif s.get("outcomeType") == "Away":
                    game["spread_away"] = s.get("points")
                    game["away_spread_price"] = s["displayOdds"]["american"]
        
        # Total
        if "total" in mkts:
            sels = sel_by_market.get(mkts["total"]["id"], [])
            for s in sels:
                if s.get("outcomeType") == "Over":
                    game["total"] = s.get("points")
                    game["over_price"] = s["displayOdds"]["american"]
                elif s.get("outcomeType") == "Under":
                    game["under_price"] = s["displayOdds"]["american"]
        
        # Moneyline
        if "moneyline" in mkts:
            sels = sel_by_market.get(mkts["moneyline"]["id"], [])
            for s in sels:
                if s.get("outcomeType") == "Home":
                    game["home_ml"] = s["displayOdds"]["american"]
                elif s.get("outcomeType") == "Away":
                    game["away_ml"] = s["displayOdds"]["american"]
        
        games.append(game)
    
    return games


def scrape_sport(browser, sport_key, url):
    """Scrape a single sport from DK via API intercept."""
    print(f"\n{'='*50}")
    print(f"Scraping {sport_key.upper()} from DraftKings...")
    
    api_responses = []
    
    def handle_response(response):
        u = response.url
        if any(k in u.lower() for k in ['sportscontent', 'eventgroup', 'market']):
            try:
                ct = response.headers.get('content-type', '')
                if response.status == 200 and 'json' in ct:
                    data = response.json()
                    api_responses.append({"url": u, "data": data})
                    print(f"  [API] {u[:150]}")
            except:
                pass
    
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )
    page = context.new_page()
    page.on("response", handle_response)
    
    print(f"  Navigating to {url} ...")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(12)
    
    # Scroll to trigger lazy loading
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)
    
    context.close()
    
    # Parse all captured API responses
    games = []
    for resp in api_responses:
        data = resp["data"]
        if "events" in data and "markets" in data and "selections" in data:
            parsed = parse_dk_api_response(data)
            if parsed:
                games.extend(parsed)
                print(f"  Parsed {len(parsed)} games from API response")
    
    # Dedupe by home+away
    seen = set()
    unique = []
    for g in games:
        key = f"{g['home_team']}|{g['away_team']}"
        if key not in seen:
            seen.add(key)
            unique.append(g)
    
    print(f"  Total unique games: {len(unique)}")
    return unique


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        all_games = {}
        for sport_key, url in URLS.items():
            games = scrape_sport(browser, sport_key, url)
            all_games[sport_key] = games
            
            out_file = os.path.join(PICKS_DIR, f"dk_raw_{sport_key}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=2)
            print(f"  Saved to {out_file}")
        
        browser.close()
    
    print(f"\n{'='*50}")
    print("SCRAPE COMPLETE")
    for k, v in all_games.items():
        print(f"  {k.upper()}: {len(v)} games")


if __name__ == "__main__":
    main()
