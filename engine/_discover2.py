"""Direct API discovery for all books."""
import asyncio, json, httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

async def try_url(client, name, url, params=None, extra_headers=None):
    h = {**HEADERS, **(extra_headers or {})}
    try:
        r = await client.get(url, headers=h, params=params)
        print(f"  [{r.status_code}] {name}: {url[:120]}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                print(f"    keys={list(data.keys())[:8]}")
                for k in ["events", "competitions", "games", "fixtures", "items", "data", "results", "offerings", "leagues"]:
                    v = data.get(k)
                    if isinstance(v, (list, dict)) and len(v) > 3:
                        print(f"    {k}: {len(v)} items")
            elif isinstance(data, list):
                print(f"    list of {len(data)} items")
            return data
    except Exception as e:
        print(f"  [ERR] {name}: {e}")
    return None

async def main():
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        # === CAESARS ===
        print("\n=== CAESARS ===")
        # Already know the API base
        caesars = await try_url(c, "caesars-menu", "https://api.americanwagering.com/regions/us/locations/oh/brands/czr/sb/v3/sports-menu")
        
        # Find NCAAB competition ID from menu
        if caesars and isinstance(caesars, list):
            for sport in caesars:
                name = sport.get("name","").lower()
                if "basketball" in name:
                    for comp in sport.get("competitions", []):
                        cname = comp.get("name","").lower()
                        if "ncaa" in cname or "college" in cname:
                            cid = comp.get("id")
                            print(f"  NCAAB comp ID: {cid} ({comp.get('name')})")

        # Try events endpoint
        await try_url(c, "caesars-events", 
            "https://api.americanwagering.com/regions/us/locations/oh/brands/czr/sb/v3/events",
            params={"competitionIds": "007d7c61-07a7-4e18-bb40-15104b6eac92", "perPage": "200", "page": "1"})
        
        # Try offerings endpoint
        await try_url(c, "caesars-offerings",
            "https://api.americanwagering.com/regions/us/locations/oh/brands/czr/sb/v3/sports/basketball/events/competition/007d7c61-07a7-4e18-bb40-15104b6eac92")

        # === BETMGM ===
        print("\n=== BETMGM ===")
        # BetMGM uses Entain's API
        await try_url(c, "betmgm-sports",
            "https://sports.oh.betmgm.com/cds-api/bettingoffer/fixtures",
            params={"x-bwin-accessid": "NmFjOTM0MjEtZjBjNC00NjI0LWIyNTctNjc2Zjk5NjE4NjE2", "lang": "en-us", "country": "US", "userCountry": "US", "state": "OH", "offerMapping": "All", "sportIds": "7", "regionIds": "9", "competitionIds": "211"})
        
        # Try alternate
        await try_url(c, "betmgm-v4",
            "https://sports.oh.betmgm.com/cds-api/bettingoffer/fixtures",
            params={"x-bwin-accessid": "NmFjOTM0MjEtZjBjNC00NjI0LWIyNTctNjc2Zjk5NjE4NjE2", "lang": "en-us", "country": "US", "state": "OH", "offerMapping": "Ede95b000-1009-4f00-b0dd-08e8aef2f589", "sportIds": "7", "competitionIds": "211"})

        # === ESPN BET ===
        print("\n=== ESPN BET ===")
        await try_url(c, "espnbet",
            "https://espnbet.com/api/sportsbook/v1/competitions/ncaa-mens-basketball/events")
        await try_url(c, "espnbet-penn",
            "https://api.espnbet.com/sportsbook/v1/competitions/ncaa-mens-basketball/events")
        # Penn Entertainment/theScore API
        await try_url(c, "espnbet-score",
            "https://api.thescore.com/ncaab/events")

        # === FANATICS ===  
        print("\n=== FANATICS ===")
        await try_url(c, "fanatics",
            "https://sportsbook.fanatics.com/api/sports/basketball/college-basketball/events")
        # Fanatics uses PointsBet's backend (acquired)
        await try_url(c, "fanatics-pb",
            "https://api.fanatics.com/sportsbook/v1/sports/basketball/events")

asyncio.run(main())
