"""Use Playwright to intercept DK API calls."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    api_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        def on_response(response):
            url = response.url
            if 'eventgroup' in url.lower() or 'sportscontent' in url.lower() or 'event' in url.lower():
                if response.status == 200:
                    api_urls.append(url)
                    print(f"CAPTURED: {response.status} {url[:150]}")

        page.on("response", on_response)

        await page.goto("https://sportsbook.draftkings.com/leagues/basketball/ncaab", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Scroll to load more
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 2000)")
            await asyncio.sleep(1)

        await browser.close()

    print(f"\nTotal API URLs captured: {len(api_urls)}")
    for u in api_urls[:20]:
        print(f"  {u[:200]}")

asyncio.run(main())
