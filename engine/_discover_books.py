"""Discover API endpoints for BetMGM, Caesars, ESPN BET, Fanatics via Playwright intercept."""
import asyncio, json
from playwright.async_api import async_playwright

TARGETS = {
    "betmgm": "https://sports.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
    "caesars": "https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa",
    "espnbet": "https://espnbet.com/sport/basketball/organization/united-states/competition/ncaa-mens-basketball",
    "fanatics": "https://sportsbook.fanatics.com/sports/basketball/college-basketball",
}

async def discover(name, url):
    captured = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        page = await ctx.new_page()

        async def on_resp(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                u = response.url
                # Skip analytics/tracking
                skip = ["google", "facebook", "tiktok", "twitter", "doubleclick", "analytics", "sentry", "datadog", "segment", "optimizely", "gtm", "adobe", "newrelic"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 1000:  # Only meaningful responses
                        captured.append((u, body, size))
                except:
                    pass

        page.on("response", on_resp)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(12)
        except Exception as e:
            print(f"  [{name}] Navigation error: {e}")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"{name.upper()}: {len(captured)} JSON responses")
    for u, body, size in sorted(captured, key=lambda x: -x[2])[:8]:
        keys = list(body.keys())[:8] if isinstance(body, dict) else f"[list:{len(body)}]"
        # Check for event-like content
        has_events = False
        event_count = 0
        if isinstance(body, dict):
            for k in ["events", "competitions", "games", "fixtures", "items", "data", "results", "offerings"]:
                v = body.get(k)
                if isinstance(v, (list, dict)) and len(v) > 5:
                    has_events = True
                    event_count = len(v)
                    break
        marker = f" *** EVENTS({event_count})" if has_events else ""
        print(f"  [{size:>7} bytes] {u[:160]}")
        print(f"    keys={keys}{marker}")

    # Save the largest response
    if captured:
        biggest = max(captured, key=lambda x: x[2])
        fname = f"{name}_sample.json"
        with open(fname, "w") as f:
            json.dump(biggest[1], f, indent=2)
        print(f"  -> Saved biggest to {fname}")

async def main():
    for name, url in TARGETS.items():
        print(f"\nDiscovering {name}...")
        try:
            await discover(name, url)
        except Exception as e:
            print(f"  {name} FAILED: {e}")

asyncio.run(main())
