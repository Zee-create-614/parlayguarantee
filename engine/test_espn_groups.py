import httpx, asyncio, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    async with httpx.AsyncClient(timeout=20) as c:
        for g in ['50', '100', '', '80']:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260221&limit=400&groups={g}"
            r = await c.get(url)
            d = r.json()
            e = d.get('events', [])
            print(f"groups={g or 'none'}: {len(e)} events")

asyncio.run(main())
