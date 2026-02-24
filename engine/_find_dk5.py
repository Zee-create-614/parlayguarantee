"""Capture ALL network requests from DK NCAAB page."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        def on_response(response):
            url = response.url
            if 'sportsbook-nash' in url or 'dkapis' in url:
                captured.append((response.status, url))

        page.on("response", on_response)

        await page.goto("https://sportsbook.draftkings.com/leagues/basketball/ncaab", wait_until="networkidle", timeout=45000)
        await asyncio.sleep(5)

        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(2)

        await browser.close()

    print(f"Captured {len(captured)} DK API calls:")
    for status, url in captured:
        print(f"  [{status}] {url[:250]}")

asyncio.run(main())
