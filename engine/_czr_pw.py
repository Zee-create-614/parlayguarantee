"""Caesars: longer wait + capture ALL network including websockets and XHR."""
import asyncio, json
from playwright.async_api import async_playwright

def p(msg):
    print(msg, flush=True)

async def main():
    captured = []
    all_urls = []
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131",
            locale="en-US", timezone_id="America/New_York", ignore_https_errors=True,
            geolocation={"latitude": 39.96, "longitude": -82.99},  # Columbus OH
            permissions=["geolocation"])
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            all_urls.append((response.status, u))
            ct = response.headers.get("content-type","")
            if "json" in ct and response.status == 200:
                skip = ["google","facebook","analytics","sentry","datadog","cookielaw","fullstory","onetrust",
                        "omtrdc","harrahs"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 1000:
                        captured.append((u, body, size))
                except:
                    pass

        page.on("response", on_resp)
        
        await page.goto("https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa",
                       wait_until="domcontentloaded", timeout=30000)
        
        # Wait 30 seconds for all deferred loads
        p("  Waiting 30s for events to load...")
        await asyncio.sleep(30)
        
        # Scroll
        for i in range(10):
            await page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(1)
        
        await asyncio.sleep(5)
        await browser.close()

    p(f"\nTotal responses: {len(all_urls)}")
    p(f"JSON captured: {len(captured)}")
    
    # Print americanwagering URLs
    for status, u in all_urls:
        if "americanwagering" in u:
            p(f"  [{status}] {u[:200]}")
    
    # Check for event-like data
    for u, body, size in sorted(captured, key=lambda x: -x[2])[:10]:
        p(f"\n  [{size}b] {u[:200]}")
        if isinstance(body, dict):
            for k, v in body.items():
                if isinstance(v, list) and len(v) > 3:
                    p(f"    {k}: {len(v)} items")
                    if v and isinstance(v[0], dict) and any(x in list(v[0].keys()) for x in ["name","home","away","team","event"]):
                        p(f"    *** EVENTS FOUND: {list(v[0].keys())[:10]}")

asyncio.run(main())
