import asyncio, json
from playwright.async_api import async_playwright

async def main():
    captured = []
    all_urls = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0",
            locale="en-US", timezone_id="America/New_York",
            geolocation={"latitude": 39.96, "longitude": -82.99}, permissions=["geolocation"])
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            status = response.status
            ct = response.headers.get("content-type", "")
            all_urls.append((status, ct[:30], u[:150]))
            if "json" in ct and status == 200:
                skip = ["google", "facebook", "analytics", "sentry", "datadog",
                        "cookielaw", "fullstory", "onetrust", "omtrdc", "harrahs",
                        "cdn-settings", "segment", "nr-data"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 500:
                        captured.append((u, body, size))
                except:
                    pass

        page.on("response", on_resp)
        print("Loading Caesars...")
        await page.goto("https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa",
                        wait_until="domcontentloaded", timeout=30000)
        print("Waiting 20s...")
        await asyncio.sleep(20)

        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(1)

        await asyncio.sleep(5)

        # Check page title/content
        title = await page.title()
        print(f"Page title: {title}")

        await browser.close()

    print(f"\nTotal responses: {len(all_urls)}")
    print(f"JSON captured: {len(captured)}")

    # Show all non-analytics URLs
    for status, ct, u in all_urls:
        if any(s in u.lower() for s in ["americanwagering", "caesars.com/api", "kambi", "sbtech"]):
            print(f"  [{status}] {ct} {u}")

    # Show captured
    for u, body, size in sorted(captured, key=lambda x: -x[2])[:10]:
        print(f"\n  [{size}b] {u[:150]}")
        if isinstance(body, dict):
            print(f"    keys: {list(body.keys())[:10]}")
        elif isinstance(body, list):
            print(f"    list: {len(body)} items")

asyncio.run(main())
