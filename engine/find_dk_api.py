import httpx, asyncio, json, sys, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def extract_dk():
    url = 'https://sportsbook.draftkings.com/leagues/basketball/ncaab'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, headers=headers)
        text = r.text
        if '__NEXT_DATA__' in text:
            start = text.index('__NEXT_DATA__')
            script_start = text.index('>', start) + 1
            script_end = text.index('</script>', script_start)
            data = json.loads(text[script_start:script_end])
            props = data.get('props', {}).get('pageProps', {})
            print(f'pageProps keys: {list(props.keys())[:10]}')
            for k, v in props.items():
                if isinstance(v, dict):
                    print(f'  {k}: dict keys={list(v.keys())[:8]}')
                elif isinstance(v, list) and len(v) > 0:
                    print(f'  {k}: list len={len(v)}, first type={type(v[0]).__name__}')
                else:
                    print(f'  {k}: {type(v).__name__} = {str(v)[:100]}')
        else:
            # Look for API URLs in page source
            api_urls = re.findall(r'https://[^"]+eventgroup[^"]+', text)
            print(f'Found {len(api_urls)} eventgroup URLs')
            for u in api_urls[:5]:
                print(f'  {u[:120]}')
            # Also look for any JSON-like data blocks
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', text[:500000], re.DOTALL)
            for i, s in enumerate(scripts):
                if 'eventGroup' in s or 'ncaab' in s.lower():
                    print(f'Script {i}: contains relevant data, length={len(s)}')

asyncio.run(extract_dk())
