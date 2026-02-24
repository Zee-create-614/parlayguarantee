"""Save BetMGM fixture data via Playwright."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    fixtures = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
            geolocation={"latitude": 39.96, "longitude": -82.99}, permissions=["geolocation"])
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200 and "cds-api/bettingoffer/fixtures" in u:
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 10000 and "basketball" in u.lower() or "competitionId=211" in u or "sportId" not in u:
                        fixtures.append((u, body, size))
                except:
                    pass

        page.on("response", on_resp)

        # Step 1: go to home page to set cookies
        await page.goto("https://www.oh.betmgm.com/en/sports",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        # Step 2: navigate to NCAAB via click or URL
        await page.goto("https://www.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(15)
        
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 2000)")
            await asyncio.sleep(1)
        
        await asyncio.sleep(5)
        await browser.close()

    print(f"Captured {len(fixtures)} fixture responses")
    if fixtures:
        biggest = max(fixtures, key=lambda x: x[2])
        print(f"Biggest: {biggest[2]}b from {biggest[0][:150]}")
        with open("mgm_fixtures.json", "w") as f:
            json.dump(biggest[1], f, indent=2)
        
        data = biggest[1]
        if isinstance(data, dict):
            print(f"Keys: {list(data.keys())[:10]}")
            fix = data.get("fixtures", [])
            print(f"Fixtures: {len(fix)}")
            if fix:
                print(f"First fixture keys: {list(fix[0].keys())[:15]}")
                print(f"Sample: {json.dumps(fix[0])[:500]}")

asyncio.run(main())
