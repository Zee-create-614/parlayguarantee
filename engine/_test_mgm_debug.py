import asyncio, json
from playwright.async_api import async_playwright

async def main():
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
            geolocation={"latitude": 39.96, "longitude": -82.99}, permissions=["geolocation"],
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
        
        # Try setting cookies first
        await ctx.add_cookies([
            {"name": "selectedState", "value": "oh", "domain": ".betmgm.com", "path": "/"},
            {"name": "jurisdiction", "value": "oh", "domain": ".betmgm.com", "path": "/"},
        ])
        
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 1000:
                        captured.append((u, body, size))
                        print(f"  [{size}b] {u[:120]}")
                except:
                    pass

        page.on("response", on_resp)

        # Try different BetMGM URLs
        urls = [
            "https://sports.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
            "https://sports.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211?jurisdiction=oh",
        ]
        for url in urls:
            try:
                print(f"Trying: {url[:80]}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                print(f"  Loaded! Title: {await page.title()}")
                await asyncio.sleep(10)
                break
            except Exception as e:
                print(f"  Failed: {str(e)[:80]}")

        await browser.close()

    print(f"\nCaptured: {len(captured)}")

asyncio.run(main())
