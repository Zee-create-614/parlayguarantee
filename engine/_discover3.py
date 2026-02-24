"""Use Playwright to discover APIs by intercepting actual browser requests."""
import asyncio, json
from playwright.async_api import async_playwright

async def intercept_book(name, url, wait_secs=15):
    captured = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await ctx.new_page()

        async def on_resp(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                u = response.url
                skip = ["google", "facebook", "tiktok", "twitter", "doubleclick", "analytics",
                        "sentry", "datadog", "segment", "optimizely", "gtm", "adobe", "newrelic",
                        "cookielaw", "fullstory", "braze", "branch", "appsflyer", "adjust"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 2000:
                        captured.append((u, body, size))
                except:
                    pass

        page.on("response", on_resp)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [{name}] goto error: {e}")
        
        await asyncio.sleep(wait_secs)
        
        # Scroll
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 2000)")
            await asyncio.sleep(2)

        await browser.close()

    print(f"\n{'='*60}")
    print(f"{name.upper()}: {len(captured)} JSON responses")
    for u, body, size in sorted(captured, key=lambda x: -x[2])[:5]:
        keys = list(body.keys())[:8] if isinstance(body, dict) else f"list[{len(body)}]"
        print(f"  [{size:>8} bytes] {u[:200]}")
        print(f"    keys={keys}")
        # Detect event data
        if isinstance(body, dict):
            for k, v in body.items():
                if isinstance(v, list) and len(v) > 5:
                    if v and isinstance(v[0], dict):
                        ek = list(v[0].keys())[:6]
                        print(f"    -> {k}[{len(v)}] first item keys: {ek}")

    if captured:
        biggest = max(captured, key=lambda x: x[2])
        with open(f"{name}_sample.json", "w") as f:
            json.dump(biggest[1], f, indent=2)
        print(f"  Saved to {name}_sample.json ({biggest[2]} bytes)")
    
    return captured

async def main():
    # BetMGM - try Ohio subdomain
    await intercept_book("betmgm", "https://sports.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211")

    # Caesars 
    await intercept_book("caesars", "https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa")

    # ESPN BET
    await intercept_book("espnbet", "https://espnbet.com/sport/basketball/organization/united-states/competition/ncaa-mens-basketball")

    # Fanatics
    await intercept_book("fanatics", "https://sportsbook.fanatics.com/sports/basketball/college-basketball")

asyncio.run(main())
