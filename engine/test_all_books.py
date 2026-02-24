"""Test scraping multiple sportsbook APIs for NCAAB"""
import httpx, asyncio, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test_betmgm():
    """BetMGM uses a public API"""
    urls = [
        'https://sports.mi.betmgm.com/cds-api/bettingoffer/fixtures?x-bwin-accessid=NmFjNmUwZjAtMGI3Yi00YzA3LTg3OTktNDgxMGIwM2RiYzYz&lang=en&country=US&userCountry=US&fixtureTypes=Standard&state=Latest&offerMapping=Ede&sportIds=7&competitionIds=264&skip=0&take=200',
        'https://sports.co.betmgm.com/cds-api/bettingoffer/fixtures?x-bwin-accessid=NmFjNmUwZjAtMGI3Yi00YzA3LTg3OTktNDgxMGIwM2RiYzYz&lang=en&country=US&userCountry=US&fixtureTypes=Standard&state=Latest&offerMapping=Ede&sportIds=7&competitionIds=264&skip=0&take=200',
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    fixtures = data.get('fixtures', [])
                    print(f'BetMGM: {len(fixtures)} fixtures')
                    for f in fixtures[:3]:
                        parts = f.get('participants', [])
                        names = [p.get('name', {}).get('value', '') for p in parts]
                        print(f'  {" vs ".join(names)}')
                    return len(fixtures)
                else:
                    print(f'BetMGM {r.status_code}: {url[:60]}')
            except Exception as e:
                print(f'BetMGM fail: {e}')
    return 0

async def test_caesars():
    """Caesars/William Hill API"""
    urls = [
        'https://api.americanwagering.com/regions/us/locations/mi/brands/czr/sb/v3/sports/basketball/events/schedule?competitionIds=cbb',
        'https://www.caesars.com/api/v1/sports/basketball/college-basketball/lines',
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=headers)
                print(f'Caesars {r.status_code}: {url[:80]}')
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list):
                        print(f'  List of {len(data)} items')
                    elif isinstance(data, dict):
                        print(f'  Keys: {list(data.keys())[:8]}')
                        events = data.get('competitions', data.get('events', []))
                        if events:
                            print(f'  Events: {len(events)}')
            except Exception as e:
                print(f'Caesars fail {url[:50]}: {e}')
    return 0

async def test_espnbet():
    """ESPN BET API"""
    urls = [
        'https://espnbet.com/api/v2/odds/college-basketball',
        'https://sportsbook-api.espnbet.com/api/v1/sports/basketball/college-basketball/events',
        'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates=20260221&limit=200',
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=headers)
                print(f'ESPN {r.status_code}: {url[:80]}')
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, dict):
                        events = data.get('events', [])
                        if events:
                            print(f'  Events: {len(events)}')
                            for e in events[:3]:
                                print(f'    {e.get("name", e.get("shortName", "?"))}')
            except Exception as e:
                print(f'ESPN fail: {e}')
    return 0

async def test_fanatics():
    """Fanatics Sportsbook API"""
    urls = [
        'https://api.fanatics.com/sportsbook/v1/sports/basketball/college/events',
        'https://sportsbook.fanatics.com/api/sports/basketball/college-basketball/events',
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=headers)
                print(f'Fanatics {r.status_code}: {url[:80]}')
                if r.status_code == 200:
                    data = r.json()
                    print(f'  Keys: {list(data.keys())[:8]}')
            except Exception as e:
                print(f'Fanatics fail: {e}')
    return 0

async def test_dk_playwright():
    """Use Playwright to get DK data"""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Capture API calls the page makes
            api_calls = []
            async def handle_response(response):
                url = response.url
                if 'eventgroup' in url.lower() or 'offer' in url.lower() or 'event' in url.lower():
                    if response.status == 200 and 'json' in (response.headers.get('content-type', '')):
                        api_calls.append(url)
            
            page.on('response', handle_response)
            await page.goto('https://sportsbook.draftkings.com/leagues/basketball/ncaab', wait_until='networkidle', timeout=45000)
            await asyncio.sleep(3)
            
            # Count game elements on page
            games = await page.query_selector_all('[class*="event-cell"], [class*="sportsbook-event"], tbody tr')
            print(f'DK Playwright: {len(games)} game elements on page')
            print(f'DK API calls captured: {len(api_calls)}')
            for u in api_calls[:5]:
                print(f'  {u[:120]}')
            
            await browser.close()
    except Exception as e:
        print(f'DK Playwright fail: {e}')

async def main():
    print('=== Testing All Sportsbook APIs ===\n')
    
    print('--- FanDuel (known working) ---')
    from sportsbook_scraper import FanDuelScraper
    fd = FanDuelScraper()
    games = await fd.scrape()
    print(f'FanDuel: {len(games)} games\n')
    
    print('--- BetMGM ---')
    await test_betmgm()
    print()
    
    print('--- Caesars ---')
    await test_caesars()
    print()
    
    print('--- ESPN Scoreboard ---')
    await test_espnbet()
    print()
    
    print('--- Fanatics ---')
    await test_fanatics()
    print()
    
    print('--- DraftKings (Playwright) ---')
    await test_dk_playwright()

asyncio.run(main())
