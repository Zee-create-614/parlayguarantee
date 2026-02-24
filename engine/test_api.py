import sys
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"

def test_nba_api():
    print("Testing NBA API...")
    try:
        r = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/",
            params={
                "apiKey": API_KEY,
                "regions": "us",
                "markets": "h2h,spreads,totals",
                "dateFormat": "iso",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        print(f"✅ NBA API: {len(data)} games")
        if data:
            print(f"First game: {data[0]['home_team']} vs {data[0]['away_team']}")
        return True
    except Exception as e:
        print(f"❌ NBA API Error: {e}")
        return False

if __name__ == "__main__":
    test_nba_api()