"""BetMGM: try intercepting during redirect, or go to main page first."""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)  # non-headless might bypass
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
            geolocation={"latitude": 39.96, "longitude": -82.99}, permissions=["geolocation"])
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                skip = ["google", "analytics", "sentry", "launchdarkly", "segment",
                        "nr-data", "facebook", "doubleclick"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 1000:
                        captured.append((u, body, size))
                        print(f"  [{size}b] {u[:120]}")
                except:
                    pass

        page.on("response", on_resp)

        # Strategy: go to betmgm.com first, let it set cookies, then navigate
        print("Loading main page...")
        try:
            await page.goto("https://sports.oh.betmgm.com/en/sports", wait_until="domcontentloaded", timeout=20000)
            print(f"  Title: {await page.title()}")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"  Main page failed: {str(e)[:80]}")
            # Try without subdomain
            try:
                await page.goto("https://www.betmgm.com/en/sports", wait_until="domcontentloaded", timeout=20000)
                print(f"  Fallback title: {await page.title()}")
                await asyncio.sleep(5)
            except Exception as e2:
                print(f"  Fallback also failed: {str(e2)[:80]}")

        # Now try basketball
        print("Navigating to NCAAB...")
        try:
            await page.goto("https://sports.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
                           wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"  NCAAB failed: {str(e)[:80]}")

        # Check cookies
        cookies = await ctx.cookies()
        print(f"\nCookies: {len(cookies)}")
        for c in cookies[:5]:
            print(f"  {c['name']}: {c['value'][:50]}")

        await browser.close()

    print(f"\nCaptured: {len(captured)}")

asyncio.run(main())
