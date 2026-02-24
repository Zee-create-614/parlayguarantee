"""Test sportsbook APIs (no Playwright) to find which ones work"""
import httpx, asyncio, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
    
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        # 1. FanDuel (known working)
        print('=== FanDuel ===')
        try:
            for state in ['mi', 'nj', 'pa', 'co', 'va']:
                url = f'https://sbapi.{state}.sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=ncaab&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx&timezone=America/New_York'
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    attachments = data.get('attachments', {})
                    events = attachments.get('events', {})
                    print(f'  {state}: {len(events)} events')
                    break
        except Exception as e:
            print(f'  Error: {e}')

        # 2. BetMGM / bwin
        print('\n=== BetMGM ===')
        for state in ['mi', 'co', 'nj', 'pa', 'va']:
            try:
                url = f'https://sports.{state}.betmgm.com/cds-api/bettingoffer/fixtures?x-bwin-accessid=NmFjNmUwZjAtMGI3Yi00YzA3LTg3OTktNDgxMGIwM2RiYzYz&lang=en&country=US&userCountry=US&fixtureTypes=Standard&state=Latest&offerMapping=Ede&sportIds=7&competitionIds=264&skip=0&take=200'
                r = await client.get(url, headers=headers)
                print(f'  {state}: {r.status_code}')
                if r.status_code == 200:
                    data = r.json()
                    fixtures = data.get('fixtures', [])
                    print(f'    {len(fixtures)} fixtures')
                    if fixtures:
                        for f in fixtures[:2]:
                            parts = f.get('participants', [])
                            names = [p.get('name', {}).get('value', '') for p in parts]
                            print(f'    {" vs ".join(names)}')
                    break
            except Exception as e:
                print(f'  {state}: {e}')

        # 3. ESPN Scoreboard (free, always works - gives us game list + odds)
        print('\n=== ESPN Scoreboard ===')
        try:
            url = 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260221&limit=200'
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                data = r.json()
                events = data.get('events', [])
                print(f'  {len(events)} events')
                odds_count = 0
                for e in events[:200]:
                    comps = e.get('competitions', [{}])
                    if comps and comps[0].get('odds'):
                        odds_count += 1
                print(f'  {odds_count} events with odds data')
                for e in events[:3]:
                    print(f'    {e.get("shortName", "?")}')
        except Exception as e:
            print(f'  Error: {e}')

        # 4. ESPN scoreboard page 2 (if paginated)
        print('\n=== ESPN Page 2 ===')
        try:
            url = 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260221&limit=200&page=2'
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                data = r.json()
                events = data.get('events', [])
                print(f'  Page 2: {len(events)} events')
        except Exception as e:
            print(f'  Error: {e}')

        # 5. Caesars
        print('\n=== Caesars ===')
        for url in [
            'https://api.americanwagering.com/regions/us/locations/mi/brands/czr/sb/v3/sports/basketball/events/schedule',
            'https://api.americanwagering.com/regions/us/locations/co/brands/czr/sb/v3/sports/basketball/events/schedule',
        ]:
            try:
                r = await client.get(url, headers=headers)
                print(f'  {r.status_code}: {url[-40:]}')
                if r.status_code == 200:
                    data = r.json()
                    print(f'    Type: {type(data).__name__}, keys: {list(data.keys())[:5] if isinstance(data,dict) else len(data)}')
            except Exception as e:
                print(f'  Error: {e}')

        # 6. DraftKings - try their public offer catalog
        print('\n=== DraftKings ===')
        for url in [
            'https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/92483/categories/486/subcategories/4518?format=json',
            'https://sportsbook.draftkings.com/sites/US-SB/api/v5/eventgroups/92483?format=json',
        ]:
            try:
                r = await client.get(url, headers={**headers, 'Accept': 'application/json'})
                print(f'  {r.status_code}: {url[-60:]}')
                if r.status_code == 200:
                    data = r.json()
                    print(f'    Keys: {list(data.keys())[:8]}')
            except Exception as e:
                print(f'  Error: {e}')

asyncio.run(main())
