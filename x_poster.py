"""
X/Twitter Poster for @ParlayGuarantee
Posts picks, results, and hype content to the ParlayGuarantee X account.

Usage:
  python x_poster.py picks       # Post today's picks
  python x_poster.py results     # Post yesterday's results scorecard
  python x_poster.py hype        # Post engagement/hype content
  python x_poster.py test        # Send a test tweet
"""

import tweepy
import json
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Twitter API Credentials (ParlayGuarantee) ──
CONSUMER_KEY = "JcR0JR1v5SSVMkzW6xKYz2foR"
CONSUMER_SECRET = "j3PLTHFavMm7RmBzSsjqbmgzHd2O5ShCvjUSUdIgjiTbtRevW2"
ACCESS_TOKEN = "2023375237639766016-PKn1MfAeeGMtUJ06j4IV5kqa0jC6GN"
ACCESS_TOKEN_SECRET = "Fln1miZTm50mYXumhsVAcc0P1kxyzL8SMybegMBELOkuY"

ENGINE_DIR = Path(__file__).parent / "engine"
RESULTS_DB = ENGINE_DIR / "results.db"
PICKS_FILE = ENGINE_DIR / "picks_output.json"

# ── Twitter Client ──

def get_client():
    """Get authenticated Twitter API v2 client."""
    client = tweepy.Client(
        consumer_key=CONSUMER_KEY,
        consumer_secret=CONSUMER_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET,
    )
    return client


def tweet(text: str):
    """Post a tweet. Returns the response."""
    client = get_client()
    print(f"Posting tweet ({len(text)} chars):\n{text}\n")
    resp = client.create_tweet(text=text)
    tweet_id = resp.data["id"]
    print(f"✅ Posted! https://x.com/ParlayGuarantee/status/{tweet_id}")
    return resp


def tweet_thread(texts: list[str]):
    """Post a thread of tweets."""
    client = get_client()
    prev_id = None
    for i, text in enumerate(texts):
        print(f"Posting tweet {i+1}/{len(texts)} ({len(text)} chars)")
        resp = client.create_tweet(text=text, in_reply_to_tweet_id=prev_id)
        prev_id = resp.data["id"]
        print(f"  → https://x.com/ParlayGuarantee/status/{prev_id}")
    return prev_id


# ── Load Data ──

def load_picks(date_str: str = None):
    """Load picks from picks_output.json."""
    if not PICKS_FILE.exists():
        print(f"No picks file at {PICKS_FILE}")
        return None
    with open(PICKS_FILE) as f:
        data = json.load(f)
    if date_str and data.get("target_date") != date_str:
        # Try date-specific file
        dated = ENGINE_DIR / f"picks_output_{date_str}.json"
        if dated.exists():
            with open(dated) as f:
                data = json.load(f)
    return data


def load_results(date_str: str = None):
    """Load results from results.db."""
    if not RESULTS_DB.exists():
        return None, None
    conn = sqlite3.connect(str(RESULTS_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    picks = cur.execute(
        "SELECT * FROM pick_results WHERE date = ? ORDER BY pick_number",
        (date_str,),
    ).fetchall()
    summary = cur.execute(
        "SELECT * FROM daily_summaries WHERE date = ?", (date_str,)
    ).fetchone()
    conn.close()
    return picks, summary


# ── Formatting ──

TEAM_ABBREV = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def abbrev(team: str) -> str:
    return TEAM_ABBREV.get(team, team[:3].upper())


def confidence_emoji(prob: float) -> str:
    if prob >= 0.7:
        return "🔒"
    elif prob >= 0.6:
        return "🔥"
    elif prob >= 0.55:
        return "💪"
    return "📊"


# ── Post Functions ──

def post_picks():
    """Post today's picks to X."""
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_picks(today)
    if not data:
        print("No picks data available.")
        return

    games = data.get("all_games", [])
    if not games:
        print("No games in picks data.")
        return

    target_date = data.get("target_date", today)
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_display = dt.strftime("%B %d").replace(" 0", " ")

    # Sort by confidence descending
    games_sorted = sorted(games, key=lambda g: g.get("win_prob", 0), reverse=True)

    # Build the main tweet
    lines = [f"🏀 NBA Picks — {date_display}\n"]
    for g in games_sorted:
        pick = g["pick"]
        prob = g.get("win_prob", 0)
        emoji = confidence_emoji(prob)
        away = abbrev(g["away"])
        home = abbrev(g["home"])
        matchup = f"{away} @ {home}"
        pct = int(prob * 100)
        lines.append(f"{emoji} {abbrev(pick)} ({pct}%) — {matchup}")

    lines.append("")
    lines.append("Full analysis + parlays → parlayguarantee.com")
    lines.append("#NBA #NBABets #GamblingX #FreePicks")

    text = "\n".join(lines)

    # If too long, split into thread
    if len(text) <= 280:
        tweet(text)
    else:
        # Split: header + top picks in first tweet, rest in reply
        top_n = 4
        tweet1_lines = [f"🏀 NBA Picks — {date_display}\n"]
        for g in games_sorted[:top_n]:
            pick = g["pick"]
            prob = g.get("win_prob", 0)
            emoji = confidence_emoji(prob)
            away = abbrev(g["away"])
            home = abbrev(g["home"])
            pct = int(prob * 100)
            tweet1_lines.append(f"{emoji} {abbrev(pick)} ({pct}%) — {away} @ {home}")
        tweet1_lines.append(f"\n⬇️ +{len(games_sorted) - top_n} more picks below")
        tweet1 = "\n".join(tweet1_lines)

        tweet2_lines = []
        for g in games_sorted[top_n:]:
            pick = g["pick"]
            prob = g.get("win_prob", 0)
            emoji = confidence_emoji(prob)
            away = abbrev(g["away"])
            home = abbrev(g["home"])
            pct = int(prob * 100)
            tweet2_lines.append(f"{emoji} {abbrev(pick)} ({pct}%) — {away} @ {home}")
        tweet2_lines.append("")
        tweet2_lines.append("Full analysis + parlays 👇")
        tweet2_lines.append("parlayguarantee.com")
        tweet2_lines.append("#NBA #NBABets #GamblingX #FreePicks")
        tweet2 = "\n".join(tweet2_lines)

        tweets = [tweet1, tweet2]
        # Further split tweet2 if needed
        if len(tweet2) > 280:
            mid = len(games_sorted[top_n:]) // 2 + top_n
            t2a_lines = []
            for g in games_sorted[top_n:mid]:
                pick = g["pick"]
                prob = g.get("win_prob", 0)
                emoji = confidence_emoji(prob)
                away = abbrev(g["away"])
                home = abbrev(g["home"])
                pct = int(prob * 100)
                t2a_lines.append(f"{emoji} {abbrev(pick)} ({pct}%) — {away} @ {home}")
            t2b_lines = []
            for g in games_sorted[mid:]:
                pick = g["pick"]
                prob = g.get("win_prob", 0)
                emoji = confidence_emoji(prob)
                away = abbrev(g["away"])
                home = abbrev(g["home"])
                pct = int(prob * 100)
                t2b_lines.append(f"{emoji} {abbrev(pick)} ({pct}%) — {away} @ {home}")
            t2b_lines.append("")
            t2b_lines.append("parlayguarantee.com")
            t2b_lines.append("#NBA #NBABets #GamblingX")
            tweets = [tweet1, "\n".join(t2a_lines), "\n".join(t2b_lines)]

        tweet_thread(tweets)


def post_results(date_str: str = None):
    """Post results scorecard for a given date (default: yesterday)."""
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    picks, summary = load_results(date_str)

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    date_display = dt.strftime("%B %d").replace(" 0", " ")

    if summary:
        total = summary["total_picks"]
        correct = summary["correct_picks"]
        acc = summary["accuracy"]
        acc_pct = int(acc * 100) if acc <= 1 else int(acc)

        if acc_pct >= 70:
            header = f"🔥 DOMINANT night! {correct}-{total - correct} ({acc_pct}%)"
        elif acc_pct >= 60:
            header = f"💪 Solid night! {correct}-{total - correct} ({acc_pct}%)"
        elif acc_pct >= 50:
            header = f"📊 {correct}-{total - correct} ({acc_pct}%)"
        else:
            header = f"😤 Tough night. {correct}-{total - correct} ({acc_pct}%)"

        lines = [f"📋 Results — {date_display}\n", header, ""]

        if picks:
            for p in picks:
                icon = "✅" if p["correct"] else "❌"
                pred = abbrev(p["predicted_winner"]) if p["predicted_winner"] else "?"
                lines.append(f"{icon} {pred}")

        lines.append("")
        lines.append("We go again tonight → parlayguarantee.com")
        lines.append("#NBA #NBABets #GamblingX")

        text = "\n".join(lines)
        if len(text) <= 280:
            tweet(text)
        else:
            # Truncated version
            short = f"📋 Results — {date_display}\n\n{header}\n\nWe go again tonight → parlayguarantee.com\n#NBA #NBABets #GamblingX"
            tweet(short)
    elif picks:
        correct = sum(1 for p in picks if p["correct"])
        total = len(picks)
        acc_pct = int(correct / total * 100) if total else 0
        text = f"📋 Results — {date_display}\n\n{correct}-{total - correct} ({acc_pct}%)\n\nWe go again → parlayguarantee.com\n#NBA #NBABets"
        tweet(text)
    else:
        print(f"No results found for {date_str}")


def post_hype():
    """Post engagement/hype content based on recent performance."""
    # Try to pull aggregate stats from results.db
    stats_text = None
    if RESULTS_DB.exists():
        conn = sqlite3.connect(str(RESULTS_DB))
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT date, total_picks, correct_picks, accuracy FROM daily_summaries ORDER BY date DESC LIMIT 7"
        ).fetchall()
        conn.close()

        if rows:
            total_picks = sum(r[1] for r in rows)
            total_correct = sum(r[2] for r in rows)
            if total_picks > 0:
                overall_acc = int(total_correct / total_picks * 100)
                days = len(rows)
                # Check for win streaks (days with >50% accuracy)
                streak = 0
                for r in rows:
                    if r[3] and (r[3] > 0.5 if r[3] <= 1 else r[3] > 50):
                        streak += 1
                    else:
                        break
                stats_text = f"📈 Last {days} days: {total_correct}/{total_picks} ({overall_acc}%)"
                if streak >= 3:
                    stats_text += f"\n🔥 {streak}-day winning streak!"

    # Rotating hype tweets
    hype_options = [
        f"🧠 Our AI crunches odds from 9+ sportsbooks every single day.\n\nNo gut feelings. No bias. Just math.\n\n{'stats_ph' if stats_text else ''}\n\nFree picks daily → parlayguarantee.com\n#NBA #NBABets #SportsBetting #GamblingX",
        f"💰 Stop guessing. Start winning.\n\nAI-powered NBA picks delivered daily.\nFirst pack is FREE.\n\n{'stats_ph' if stats_text else ''}\n\nparlayguarantee.com\n#NBA #NBABets #FreePicks #GamblingX",
        f"🏀 Tonight's slate is loaded.\n\nOur algorithm already has the edge.\n\n{'stats_ph' if stats_text else ''}\n\nGet your picks → parlayguarantee.com\n#NBA #NBABets #GamblingX",
        f"🎯 While you're scrolling, our AI is analyzing 50+ data points per game.\n\nLet the machine do the work.\n\n{'stats_ph' if stats_text else ''}\n\nparlayguarantee.com\n#NBA #SportsBetting #GamblingX",
    ]

    import random
    text = random.choice(hype_options)
    if stats_text:
        text = text.replace("stats_ph", stats_text)
    else:
        text = text.replace("\n\nstats_ph", "").replace("stats_ph\n\n", "").replace("stats_ph", "")

    # Clean up any double newlines
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    tweet(text.strip())


def post_test():
    """Send a test tweet to verify API connection."""
    tweet("🔥 ParlayGuarantee.com is LIVE. AI-powered sports picks. First pack FREE. Let's eat. 🏀")


# ── CLI ──

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "picks":
        post_picks()
    elif cmd == "results":
        date_arg = sys.argv[2] if len(sys.argv) > 2 else None
        post_results(date_arg)
    elif cmd == "hype":
        post_hype()
    elif cmd == "test":
        post_test()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
