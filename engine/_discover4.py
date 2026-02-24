"""One-at-a-time API discovery with flush."""
import asyncio, json, sys
from playwright.async_api import async_playwright

def p(msg):
    print(msg, flush=True)

async def intercept(name, url, wait_secs=12):
    captured = []
    p(f"\n--- {name.upper()} ---")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US", timezone_id="America/New_York",
            ignore_https_errors=True,
        )
        page = await ctx.new_page()

        async def on_resp(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                u = response.url
                skip = ["google","facebook","tiktok","twitter","doubleclick","analytics","sentry",
                        "datadog","segment","optimizely","gtm","adobe","newrelic","cookielaw",
                        "fullstory","braze","branch","appsflyer","adjust","onetrust"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 2000:
                        captured.append((u, body, size))
                        p(f"  CAPTURED [{size} bytes] {u[:150]}")
                except:
                    pass

        page.on("response", on_resp)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        except Exception as e:
            p(f"  goto error: {e}")
        await asyncio.sleep(wait_secs)
        await browser.close()

    if captured:
        biggest = max(captured, key=lambda x: x[2])
        with open(f"{name}_sample.json", "w") as f:
            json.dump(biggest[1], f, indent=2)
        p(f"  Saved {name}_sample.json ({biggest[2]} bytes)")
    else:
        p(f"  No JSON data captured")

async def main():
    await intercept("betmgm", "https://sports.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211")
    await intercept("caesars", "https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa")
    await intercept("espnbet", "https://espnbet.com/sport/basketball/organization/united-states/competition/ncaa-mens-basketball")
    await intercept("fanatics", "https://sportsbook.fanatics.com/sports/basketball/college-basketball")

asyncio.run(main())
