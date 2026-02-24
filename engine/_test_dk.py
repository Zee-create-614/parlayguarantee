import httpx, asyncio, json

async def fetch():
    # Test DK main domain
    url = "https://sportsbook.draftkings.com/api/odds/v1/leagues/92483/offers/gamelines"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url, headers=headers)
        ct = r.headers.get("content-type", "")
        print(f"Status: {r.status_code}, CT: {ct}, Size: {len(r.content)}")
        if "json" in ct or r.text.strip().startswith("{") or r.text.strip().startswith("["):
            data = r.json()
            print(f"JSON! Type: {type(data).__name__}")
        else:
            print(f"First 300: {r.text[:300]}")

    # Try the eventgroup endpoint on main domain
    url2 = "https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/92483?format=json"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r2 = await c.get(url2, headers=headers)
        ct2 = r2.headers.get("content-type", "")
        print(f"\nEventgroup: {r2.status_code}, CT: {ct2}, Size: {len(r2.content)}")
        if "json" in ct2:
            print("JSON!")
        else:
            print(f"First 300: {r2.text[:300]}")

    # Try DK API v6
    url3 = "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/92483?format=json"
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        try:
            r3 = await c.get(url3, headers=headers)
            print(f"\nnash no-state: {r3.status_code}, Size: {len(r3.content)}")
        except Exception as e:
            print(f"\nnash no-state: {e}")

asyncio.run(fetch())
