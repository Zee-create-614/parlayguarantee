import asyncio, json
from playwright.async_api import async_playwright

async def main():
    captured = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        async def on_response(response):
            url = response.url
            if 'sportsbook-nash' in url:
                try:
                    body = await response.json()
                    captured.append((url, body))
                except:
                    pass

        page.on("response", on_response)

        await page.goto("https://sportsbook.draftkings.com/leagues/basketball/ncaab", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(15)

        # Scroll to trigger more loads
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(3)

        await browser.close()

    print(f"Captured {len(captured)} API responses")
    for url, body in captured:
        print(f"\nURL: {url[:200]}")
        if isinstance(body, dict):
            print(f"  Top keys: {list(body.keys())[:10]}")
            # Count events if present
            events = body.get('events', [])
            if events:
                print(f"  Events: {len(events)}")
                if events:
                    e = events[0]
                    print(f"  Sample event keys: {list(e.keys())[:10]}")
                    print(f"  Sample: {e.get('name', e.get('teamName1',''))}")
            offers = body.get('offers', body.get('offerCategories', []))
            if offers:
                print(f"  Offers/categories: {len(offers)}")
        # Save first big response
        if isinstance(body, dict) and len(json.dumps(body)) > 5000:
            with open('dk_sample.json', 'w') as f:
                json.dump(body, f, indent=2)
            print("  -> Saved to dk_sample.json")

asyncio.run(main())
