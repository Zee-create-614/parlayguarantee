"""Try BetMGM's underlying Roar Digital / Entain API directly."""
import httpx, asyncio, json

async def main():
    # BetMGM uses bff (backend for frontend) API under sports.*.betmgm.com
    # The actual API is at cds-api.betmgm.com or similar
    urls = [
        # BetMGM content delivery
        "https://cds-api.betmgm.com/bettingoffer/fixtures?x-bwin-accessid=NmFjNmUwZjAtMGUxZi00MzI5LTg3MjctOGRjYmM2NjM2YjBl&lang=en-us&country=US&userCountry=US&subdivision=US-OH&offerMapping=All&sportIds=7&competitionIds=211&fixtureTypes=Standard",
        # roar digital endpoint
        "https://sports.oh.betmgm.com/cds-api/bettingoffer/fixtures?x-bwin-accessid=NmFjNmUwZjAtMGUxZi00MzI5LTg3MjctOGRjYmM2NjM2YjBl&lang=en-us&country=US&userCountry=US&subdivision=US-OH&offerMapping=All&sportIds=7&competitionIds=211&fixtureTypes=Standard",
        # Alternate: bwin-based API (same parent company)
        "https://cds-api.betmgm.com/bettingoffer/fixtures?x-bwin-accessid=NmFjNmUwZjAtMGUxZi00MzI5LTg3MjctOGRjYmM2NjM2YjBl&lang=en-us&country=US&offerMapping=All&sportIds=7",
        # Try the ms endpoint
        "https://sports.oh.betmgm.com/en/api/offering/v2018/betoffers/fixtures?sportIds=7&competitionId=211",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        "Accept": "application/json",
    }
    
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        for url in urls:
            try:
                r = await c.get(url, headers=headers)
                ct = r.headers.get("content-type", "")
                print(f"[{r.status_code}] {ct[:30]} {len(r.content)}b {url[:100]}")
                if "json" in ct and r.status_code == 200:
                    data = r.json()
                    if isinstance(data, dict):
                        print(f"  Keys: {list(data.keys())[:10]}")
                        fixtures = data.get("fixtures", [])
                        if fixtures:
                            print(f"  Fixtures: {len(fixtures)}")
                            print(f"  Sample: {json.dumps(fixtures[0])[:200]}")
                elif r.status_code == 200:
                    print(f"  Body: {r.text[:200]}")
            except Exception as e:
                print(f"FAIL: {str(e)[:80]} {url[:100]}")

asyncio.run(main())
