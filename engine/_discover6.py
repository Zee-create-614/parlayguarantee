"""Find Caesars NCAAB competition ID and scrape events."""
import asyncio, json, sys
from playwright.async_api import async_playwright

def p(msg):
    print(msg, flush=True)

async def main():
    # First check the sports menu for NCAAB
    menu = json.load(open("caesars_events.json"))  # This is actually teamMetadata
    
    # Load the actual sports menu we captured
    import httpx
    
    p("=== Finding NCAAB competition ID ===")
    
    captured = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131",
            locale="en-US", timezone_id="America/New_York", ignore_https_errors=True)
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            if "americanwagering" in u and response.status == 200:
                ct = response.headers.get("content-type","")
                if "json" in ct:
                    try:
                        body = await response.json()
                        size = len(json.dumps(body))
                        captured.append((u, body, size))
                        # Log ALL americanwagering requests
                        p(f"  [{size}b] {u}")
                    except:
                        pass

        page.on("response", on_resp)
        
        # Navigate to the NCAAB page and wait for events to load
        await page.goto("https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa",
                       wait_until="domcontentloaded", timeout=30000)
        
        # Wait longer for SPA to load events
        p("  Waiting for SPA to load events...")
        await asyncio.sleep(20)
        
        # Scroll aggressively
        for i in range(10):
            await page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(1)
        
        await asyncio.sleep(5)
        await browser.close()
    
    p(f"\nTotal API calls: {len(captured)}")
    
    # Check for event data
    for u, body, size in captured:
        if size > 5000 and isinstance(body, dict):
            for k, v in body.items():
                if isinstance(v, list) and len(v) > 3:
                    if v and isinstance(v[0], dict):
                        sample_keys = list(v[0].keys())[:10]
                        p(f"  {k}[{len(v)}] → {sample_keys}")
        elif size > 5000 and isinstance(body, list) and body and isinstance(body[0], dict):
            p(f"  list[{len(body)}] → {list(body[0].keys())[:10]}")
            with open("caesars_data.json", "w") as f:
                json.dump(body, f, indent=2)
            p(f"  Saved caesars_data.json")

asyncio.run(main())
