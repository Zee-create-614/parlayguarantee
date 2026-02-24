"""Save BetMGM fixture data — headless=False, capture ALL cds-api responses."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    cds_data = []

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
            if "json" in ct and response.status == 200 and "cds-api" in u:
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 5000:
                        cds_data.append((u, body, size))
                        print(f"  [{size}b] {u[:120]}", flush=True)
                except:
                    pass

        page.on("response", on_resp)

        print("Loading home...", flush=True)
        await page.goto("https://www.oh.betmgm.com/en/sports",
                        wait_until="domcontentloaded", timeout=30000)
        print("Home loaded. Waiting 5s...", flush=True)
        await asyncio.sleep(5)

        print("Navigating to NCAAB...", flush=True)
        await page.goto("https://www.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
                        wait_until="domcontentloaded", timeout=30000)
        print("NCAAB loaded. Waiting 15s...", flush=True)
        await asyncio.sleep(15)

        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 2000)")
            await asyncio.sleep(1)

        await asyncio.sleep(5)
        await browser.close()

    print(f"\nCaptured {len(cds_data)} CDS responses")
    
    # Find fixture data
    for u, body, size in sorted(cds_data, key=lambda x: -x[2])[:5]:
        print(f"\n[{size}b] {u[:150]}")
        if isinstance(body, dict):
            print(f"  Keys: {list(body.keys())[:10]}")
            fix = body.get("fixtures", [])
            if fix:
                print(f"  Fixtures: {len(fix)}")
                f0 = fix[0]
                print(f"  Sample keys: {list(f0.keys())[:15]}")
                # Save
                with open("mgm_fixtures.json", "w") as f:
                    json.dump(body, f, indent=2)
                print(f"  Saved to mgm_fixtures.json")
                break

asyncio.run(main())
