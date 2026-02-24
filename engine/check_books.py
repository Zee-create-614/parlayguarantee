import sys, requests, json
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

# Check which bookmakers are available per game
url = 'https://api.the-odds-api.com/v4/sports/basketball_ncaab/odds'
params = {'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1', 'regions': 'us', 'markets': 'totals,spreads,h2h'}
r = requests.get(url, params=params, timeout=30)
games = r.json()
remaining = r.headers.get('x-requests-remaining', '?')
print(f"API remaining: {remaining}")

# Count which books appear and how many games each covers
book_counts = Counter()
games_per_book = {}
for g in games:
    books = [b['key'] for b in g.get('bookmakers', [])]
    for b in books:
        book_counts[b] += 1
        if b not in games_per_book:
            games_per_book[b] = 0
        games_per_book[b] += 1

print(f"\nTotal NCAAB games: {len(games)}")
print(f"\nBookmaker coverage:")
for book, count in book_counts.most_common():
    pct = count / len(games) * 100
    print(f"  {book}: {count}/{len(games)} games ({pct:.0f}%)")

# Check a specific game to see book details
print(f"\nSample game bookmakers:")
g = games[0]
print(f"  {g['away_team']} @ {g['home_team']}")
for b in g.get('bookmakers', []):
    markets = [m['key'] for m in b.get('markets', [])]
    print(f"    {b['key']}: {markets}")

# Now check NBA
url2 = 'https://api.the-odds-api.com/v4/sports/basketball_nba/odds'
params2 = {'apiKey': 'f3c9f91dc369f56dea1b523d3071e1f1', 'regions': 'us', 'markets': 'totals,spreads,h2h'}
r2 = requests.get(url2, params=params2, timeout=30)
nba = r2.json()
nba_books = Counter()
for g in nba:
    for b in g.get('bookmakers', []):
        nba_books[b['key']] += 1
print(f"\nNBA bookmaker coverage ({len(nba)} games):")
for book, count in nba_books.most_common():
    print(f"  {book}: {count}/{len(nba)} games")
