"""Caesars: try v3 endpoints that work, or wait for WAF challenge to resolve."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
            geolocation={"latitude": 39.96, "longitude": -82.99}, permissions=["geolocation"])
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            ct = response.headers.get("content-type", "")
            if response.status == 200 and "json" in ct:
                skip = ["google", "facebook", "analytics", "sentry", "datadog",
                        "cookielaw", "fullstory", "onetrust", "omtrdc", "harrahs",
                        "segment", "nr-data", "demdex", "awswaf", "dvc.american"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 1000:
                        captured.append((u, body, size))
                        print(f"  CAPTURED [{size}b]: {u[:120]}")
                except:
                    pass

        page.on("response", on_resp)

        # Go to the page and wait long enough for WAF to resolve
        print("Loading...")
        await page.goto("https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa",
                        wait_until="networkidle", timeout=60000)
        print("Page loaded. Waiting 10s...")
        await asyncio.sleep(10)

        # Try scrolling to trigger lazy loads
        for i in range(15):
            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(0.5)
        
        print("Scrolled. Waiting 10s more...")
        await asyncio.sleep(10)

        # Try clicking on basketball/ncaab tabs if they exist
        try:
            content = await page.content()
            # Count how many event cards are visible
            count = await page.evaluate("document.querySelectorAll('[class*=event], [class*=Event], [data-testid*=event]').length")
            print(f"Event-like elements: {count}")
        except:
            pass

        await browser.close()

    print(f"\nTotal captured: {len(captured)}")
    # Check for event data
    for u, body, size in sorted(captured, key=lambda x: -x[2])[:5]:
        print(f"\n[{size}b] {u[:150]}")
        if isinstance(body, dict):
            for k, v in body.items():
                if isinstance(v, list) and len(v) > 3:
                    print(f"  {k}: {len(v)} items")

asyncio.run(main())
