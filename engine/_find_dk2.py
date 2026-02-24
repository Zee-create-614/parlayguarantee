
import httpx, asyncio, json

async def main():
    client = httpx.AsyncClient(timeout=20, follow_redirects=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131',
        'Accept': 'application/json',
    }

    # Try sportscontent views endpoint for NCAAB
    urls = [
        "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/42648",
        "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/92483",
        "https://sportsbook-nash.draftkings.com/sites/US-OH-SB/api/v5/eventgroups/92483",
        "https://sportsbook-nash.draftkings.com/sites/US-OH-SB/api/v5/eventgroups/92483?format=json",
    ]

    for url in urls:
        try:
            r = await client.get(url, headers=headers)
            print(f"{r.status_code} {url[:80]}")
            if r.status_code == 200:
                data = r.json() if 'json' in r.headers.get('content-type','') else {}
                print(f"  Keys: {list(data.keys())[:10] if isinstance(data, dict) else type(data)}")
                if isinstance(data, dict) and 'events' in data:
                    evts = data['events']
                    if isinstance(evts, list):
                        print(f"  Events count: {len(evts)}")
                    elif isinstance(evts, dict):
                        print(f"  Events count: {len(evts)}")
        except Exception as e:
            print(f"FAIL {url[:80]}: {e}")

    # Try the navigation endpoint to find NCAAB league/group ID
    try:
        r = await client.get("https://sportsbook-nash.draftkings.com/api/sportscontent/navigation/dkusoh/v1/nav/sports/6", headers=headers)
        print(f"\nNav sports/6: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            # Look for NCAAB
            text = json.dumps(data)
            if 'ncaa' in text.lower():
                # Find the league entries
                for key in ['leagues', 'children', 'categories', 'subcategories']:
                    if key in data:
                        items = data[key]
                        for item in (items if isinstance(items, list) else []):
                            name = str(item.get('name', item.get('label', ''))).lower()
                            if 'ncaa' in name or 'college' in name:
                                print(f"  Found: {item.get('name')} id={item.get('id', item.get('leagueId'))}")
    except Exception as e:
        print(f"Nav failed: {e}")

asyncio.run(main())
