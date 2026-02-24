import httpx, asyncio, json

async def main():
    client = httpx.AsyncClient(timeout=15, follow_redirects=True)
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131', 'Accept': '*/*'}

    # The gateway endpoint found in the page source
    urls = [
        "https://gateway.northamerica-northeast2.prod.dkapis.com/dkusoh/sportsbook-nash/v1/eventgroups/92483?includePromotions=true&appname=web",
        "https://gwa.us-east4.prod.dkapis.com/dkusoh/sportsbook-nash/v1/eventgroups/92483",
    ]

    for url in urls:
        try:
            r = await client.get(url, headers=h)
            print(f"{r.status_code} {url[:100]}")
            if r.status_code == 200:
                data = r.json()
                print(f"  Keys: {list(data.keys())[:10]}")
                # Check for events
                for k in ['eventGroup', 'events', 'data']:
                    if k in data:
                        v = data[k]
                        if isinstance(v, dict):
                            print(f"  {k} keys: {list(v.keys())[:8]}")
                            if 'events' in v:
                                print(f"  events count: {len(v['events'])}")
                        elif isinstance(v, list):
                            print(f"  {k} count: {len(v)}")
        except Exception as e:
            print(f"FAIL: {e}")

asyncio.run(main())
