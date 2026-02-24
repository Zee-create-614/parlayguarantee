"""Dig into Caesars events + try BetMGM alternatives."""
import asyncio, json, sys
from playwright.async_api import async_playwright

def p(msg):
    print(msg, flush=True)

async def caesars_deep():
    """Caesars: navigate to NCAAB page and capture event data."""
    p("\n=== CAESARS DEEP ===")
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
                        p(f"  [{size}b] {u[:180]}")
                    except:
                        pass

        page.on("response", on_resp)
        try:
            await page.goto("https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa", 
                          wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            p(f"  goto: {e}")
        
        await asyncio.sleep(15)
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 3000)")
            await asyncio.sleep(2)
        
        await browser.close()

    for u, body, size in captured:
        if isinstance(body, dict):
            keys = list(body.keys())[:8]
            p(f"  keys={keys}")
            for k,v in body.items():
                if isinstance(v, list) and len(v) > 3 and v and isinstance(v[0], dict):
                    p(f"    {k}[{len(v)}] sample keys: {list(v[0].keys())[:8]}")
        elif isinstance(body, list) and body:
            p(f"  list[{len(body)}] sample keys: {list(body[0].keys())[:8] if isinstance(body[0],dict) else type(body[0])}")

    if captured:
        # Save biggest that looks like events
        for u, body, size in sorted(captured, key=lambda x: -x[2]):
            with open("caesars_events.json", "w") as f:
                json.dump(body, f, indent=2)
            p(f"  Saved caesars_events.json")
            break

async def betmgm_alt():
    """Try BetMGM with different URL patterns."""
    p("\n=== BETMGM ALT ===")
    captured = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131",
            locale="en-US", timezone_id="America/New_York", ignore_https_errors=True,
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
        page = await ctx.new_page()

        async def on_resp(response):
            u = response.url
            if response.status == 200:
                ct = response.headers.get("content-type","")
                if "json" in ct:
                    skip = ["google","facebook","analytics","sentry","datadog","cookielaw","fullstory","onetrust"]
                    if any(s in u.lower() for s in skip):
                        return
                    try:
                        body = await response.json()
                        size = len(json.dumps(body))
                        if size > 3000:
                            captured.append((u, body, size))
                            p(f"  [{size}b] {u[:180]}")
                    except:
                        pass

        page.on("response", on_resp)
        
        # Try different BetMGM URLs
        for url in [
            "https://sports.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
            "https://sports.on.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
        ]:
            p(f"  Trying: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(8)
            except Exception as e:
                p(f"  error: {e}")
        
        await browser.close()

    if captured:
        biggest = max(captured, key=lambda x: x[2])
        with open("betmgm_sample.json", "w") as f:
            json.dump(biggest[1], f, indent=2)
        p(f"  Saved betmgm_sample.json")
    else:
        p("  No data captured")

async def main():
    await caesars_deep()
    await betmgm_alt()

asyncio.run(main())
