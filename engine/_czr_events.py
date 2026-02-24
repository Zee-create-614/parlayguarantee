import asyncio, json, httpx

async def main():
    comp_id = "d246a1dd-72bf-45d1-bc86-efc519fa8e90"
    base = "https://api.americanwagering.com/regions/us/locations/oh/brands/czr/sb/v3"
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131",
        "Accept": "application/json",
        "Origin": "https://sportsbook.caesars.com",
        "Referer": "https://sportsbook.caesars.com/",
    }
    
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
        # Try different event endpoints
        urls = [
            (f"{base}/competitions/{comp_id}/events", {}),
            (f"{base}/competitions/{comp_id}/events", {"maxMarkets": "3"}),
            (f"{base}/events", {"competitionId": comp_id}),
            (f"{base}/events", {"competitionId": comp_id, "maxMarkets": "3", "marketSorts": "HH,HL,MR"}),
            (f"{base}/events", {"competitionIds": comp_id, "maxMarkets": "3"}),
            (f"{base}/coupon/events", {"competitionId": comp_id}),
            (f"{base}/coupon/coupon-events", {"competitionId": comp_id}),
        ]
        
        for url, params in urls:
            try:
                r = await c.get(url, headers=h, params=params)
                print(f"[{r.status_code}] {url}?{'&'.join(f'{k}={v}' for k,v in params.items())}", flush=True)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        print(f"  list[{len(data)}]", flush=True)
                        if data and isinstance(data[0], dict):
                            print(f"  keys: {list(data[0].keys())[:10]}", flush=True)
                    elif isinstance(data, dict):
                        print(f"  keys: {list(data.keys())[:8]}", flush=True)
                        for k, v in data.items():
                            if isinstance(v, list) and len(v) > 0:
                                print(f"  {k}: {len(v)} items", flush=True)
                    if r.status_code == 200 and len(r.text) > 1000:
                        with open("czr_events.json", "w") as f:
                            json.dump(data, f, indent=2)
                        print(f"  SAVED czr_events.json ({len(r.text)} bytes)", flush=True)
                        return
            except Exception as e:
                print(f"ERR: {e}", flush=True)

asyncio.run(main())
