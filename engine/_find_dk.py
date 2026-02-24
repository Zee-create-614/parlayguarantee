
import httpx, asyncio, re

async def main():
    client = httpx.AsyncClient(timeout=15, follow_redirects=True)
    r = await client.get('https://sportsbook.draftkings.com/leagues/basketball/ncaab',
                         headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131'})
    # Find all API-like URLs
    urls = re.findall(r'https://[a-zA-Z0-9._-]*draftkings[a-zA-Z0-9._/-]*api[a-zA-Z0-9._/-?=&]*', r.text)
    for u in sorted(set(urls))[:20]:
        print(u)

    # Also look for eventgroup IDs
    egs = re.findall(r'eventgroups?/(\d+)', r.text)
    print("Event group IDs:", sorted(set(egs)))

    # Look for any JSON config with API base
    configs = re.findall(r'"(https://[^"]*api[^"]*)"', r.text)
    for c in sorted(set(configs))[:20]:
        print("CONFIG:", c)

asyncio.run(main())
