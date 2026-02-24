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

        await page.goto("https://sportsbook.draftkings.com/leagues/basketball/ncaab", wait_until="domcontentloaded", timeout=30000)
        # Wait for content to load
        await asyncio.sleep(15)

        await browser.close()

    print(f"Captured {len(captured)} DK API calls:")
    for status, url in captured:
        print(f"  [{status}] {url[:300]}")

asyncio.run(main())
