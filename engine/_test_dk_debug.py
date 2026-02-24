"""Capture DK data and dump structure for debugging."""
import asyncio, json, logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)

async def main():
    captured = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0",
            locale="en-US", timezone_id="America/New_York",
            geolocation={"latitude": 39.96, "longitude": -82.99}, permissions=["geolocation"])
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            if "sportsbook-nash" in u and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = await response.json()
                        size = len(json.dumps(body))
                        if size > 1000:
                            captured.append((u, body, size))
                    except:
                        pass

        page.on("response", on_resp)
        await page.goto("https://sportsbook.draftkings.com/leagues/basketball/ncaab",
                        wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(12)
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(2)
        await asyncio.sleep(3)
        await browser.close()

    print(f"Captured {len(captured)} responses")
    for url, body, size in sorted(captured, key=lambda x: -x[2]):
        print(f"\n[{size}b] {url[:150]}")
        if isinstance(body, dict):
            print(f"  Top keys: {list(body.keys())[:15]}")
            eg = body.get("eventGroup", {})
            if eg:
                print(f"  eventGroup keys: {list(eg.keys())[:15]}")
                events = eg.get("events", [])
                print(f"  events: {len(events)}")
                oc = eg.get("offerCategories", [])
                print(f"  offerCategories: {len(oc)}")
                if oc:
                    for c in oc[:3]:
                        print(f"    cat: {c.get('name')} subcats: {len(c.get('offerSubcategoryDescriptors', []))}")
                        for sc in c.get("offerSubcategoryDescriptors", [])[:2]:
                            osc = sc.get("offerSubcategory", {})
                            offers = osc.get("offers", [])
                            print(f"      subcat: {sc.get('name')} offers: {len(offers)}")
                            if offers and offers[0]:
                                first = offers[0]
                                if isinstance(first, list) and first:
                                    first = first[0]
                                if isinstance(first, dict):
                                    print(f"        offer keys: {list(first.keys())[:10]}")
                                    print(f"        label: {first.get('label')}")
                                    print(f"        eventId: {first.get('eventId')}")
                                    outs = first.get("outcomes", [])
                                    if outs:
                                        print(f"        outcomes[0] keys: {list(outs[0].keys())[:10]}")
                                        print(f"        outcomes[0]: {json.dumps(outs[0])[:200]}")

    # Save biggest
    if captured:
        biggest = max(captured, key=lambda x: x[2])
        with open("dk_debug_full.json", "w") as f:
            json.dump(biggest[1], f, indent=2)
        print(f"\nSaved biggest ({biggest[2]}b) to dk_debug_full.json")

asyncio.run(main())
