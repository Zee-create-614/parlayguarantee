#!/usr/bin/env python3
"""
kalshi_client.py — Kalshi Prediction Market Integration (STANDALONE)
====================================================================
Fetches NBA game-by-game win probabilities from Kalshi's public API.
NOT auto-wired into the main engine pipeline. For manual A/B testing only.

Kalshi API: https://trading-api.readme.io/reference
- Series KXNBAGAME: Individual NBA game winner markets
- No NCAAB game markets available (only championship futures)
- No spread or totals markets — moneyline (win probability) only
- Prices are in cents (0-100), directly interpretable as win probability %

Usage:
    from kalshi_client import KalshiClient
    client = KalshiClient()
    games = client.fetch_nba_game_markets()
    matched = client.match_to_engine_picks(games, engine_picks)
"""

import json
import logging
import re
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi abbreviation -> common team name mapping
KALSHI_ABBREV_TO_TEAM = {
    'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
    'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
    'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
    'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
    'LAC': 'Los Angeles Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
    'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
    'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
    'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
    'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
    'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards',
}

# Reverse: team name -> abbreviation
TEAM_TO_ABBREV = {v: k for k, v in KALSHI_ABBREV_TO_TEAM.items()}

# Kalshi title fragments to full team names
KALSHI_CITY_TO_TEAM = {
    'Atlanta': 'Atlanta Hawks', 'Boston': 'Boston Celtics', 'Brooklyn': 'Brooklyn Nets',
    'Charlotte': 'Charlotte Hornets', 'Chicago': 'Chicago Bulls', 'Cleveland': 'Cleveland Cavaliers',
    'Dallas': 'Dallas Mavericks', 'Denver': 'Denver Nuggets', 'Detroit': 'Detroit Pistons',
    'Golden State': 'Golden State Warriors', 'Houston': 'Houston Rockets', 'Indiana': 'Indiana Pacers',
    'Los Angeles C': 'Los Angeles Clippers', 'Los Angeles L': 'Los Angeles Lakers',
    'Memphis': 'Memphis Grizzlies', 'Miami': 'Miami Heat', 'Milwaukee': 'Milwaukee Bucks',
    'Minnesota': 'Minnesota Timberwolves', 'New Orleans': 'New Orleans Pelicans',
    'New York': 'New York Knicks', 'Oklahoma City': 'Oklahoma City Thunder',
    'Orlando': 'Orlando Magic', 'Philadelphia': 'Philadelphia 76ers', 'Phoenix': 'Phoenix Suns',
    'Portland': 'Portland Trail Blazers', 'Sacramento': 'Sacramento Kings',
    'San Antonio': 'San Antonio Spurs', 'Toronto': 'Toronto Raptors', 'Utah': 'Utah Jazz',
    'Washington': 'Washington Wizards',
}


class KalshiClient:
    """Fetches and parses Kalshi sports prediction market data."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'ParlayGuarantee-Engine/1.0',
        })

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{KALSHI_API_BASE}{endpoint}"
        try:
            r = self.session.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Kalshi API error ({endpoint}): {e}")
            return {}

    def fetch_nba_game_events(self) -> List[dict]:
        """Fetch all active NBA game events from Kalshi."""
        data = self._get("/events", params={
            'status': 'open',
            'series_ticker': 'KXNBAGAME',
            'limit': 100,
        })
        events = data.get('events', [])
        logger.info(f"Kalshi: {len(events)} NBA game events found")
        return events

    def fetch_markets_for_event(self, event_ticker: str) -> List[dict]:
        """Fetch market details (prices) for a specific event."""
        data = self._get("/markets", params={
            'event_ticker': event_ticker,
            'limit': 10,
        })
        return data.get('markets', [])

    def _parse_event_ticker(self, ticker: str) -> Optional[dict]:
        """
        Parse event ticker like KXNBAGAME-26FEB23SASDET into components.
        Returns {away_abbrev, home_abbrev, date_str} or None.
        """
        # Format: KXNBAGAME-YYMMMDDAWYHOM
        m = re.match(r'KXNBAGAME-(\d{2})([A-Z]{3})(\d{2})([A-Z]{3})([A-Z]{3})', ticker)
        if not m:
            return None
        year, month_str, day, away_abbrev, home_abbrev = m.groups()
        months = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                  'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
        month_num = months.get(month_str)
        if not month_num:
            return None
        date_str = f"20{year}-{month_num:02d}-{int(day):02d}"
        return {
            'away_abbrev': away_abbrev,
            'home_abbrev': home_abbrev,
            'date_str': date_str,
            'away_team': KALSHI_ABBREV_TO_TEAM.get(away_abbrev, away_abbrev),
            'home_team': KALSHI_ABBREV_TO_TEAM.get(home_abbrev, home_abbrev),
        }

    def fetch_nba_game_markets(self, target_date: str = None) -> List[dict]:
        """
        Fetch all NBA game markets with win probabilities.
        
        Args:
            target_date: Optional YYYY-MM-DD to filter. If None, returns all active.
            
        Returns:
            List of dicts with: home_team, away_team, date, home_win_prob, away_win_prob,
                                home_last_price, away_last_price, volume, event_ticker
        """
        events = self.fetch_nba_game_events()
        results = []

        for event in events:
            ticker = event.get('event_ticker', '')
            parsed = self._parse_event_ticker(ticker)
            if not parsed:
                continue

            # Filter by date if specified
            if target_date and parsed['date_str'] != target_date:
                continue

            # Fetch market prices
            markets = self.fetch_markets_for_event(ticker)
            if len(markets) < 2:
                continue

            # Parse the two sides (home win / away win)
            home_team = parsed['home_team']
            away_team = parsed['away_team']
            home_price = away_price = None
            home_volume = away_volume = 0

            for mkt in markets:
                yes_sub = mkt.get('yes_sub_title', '')
                # Match by city name in yes_sub_title
                matched_team = KALSHI_CITY_TO_TEAM.get(yes_sub)
                if not matched_team:
                    # Try partial match
                    for city, team in KALSHI_CITY_TO_TEAM.items():
                        if city in yes_sub:
                            matched_team = team
                            break

                last_price = mkt.get('last_price', 0)  # cents (0-100)
                yes_bid = mkt.get('yes_bid', 0)
                yes_ask = mkt.get('yes_ask', 0)
                # Use midpoint of bid/ask for better estimate, fallback to last_price
                if yes_bid > 0 and yes_ask > 0:
                    mid_price = (yes_bid + yes_ask) / 2
                else:
                    mid_price = last_price

                vol = mkt.get('volume', 0)

                if matched_team == home_team:
                    home_price = mid_price
                    home_volume = vol
                elif matched_team == away_team:
                    away_price = mid_price
                    away_volume = vol

            if home_price is not None and away_price is not None:
                # Normalize to probabilities (devig)
                total = home_price + away_price
                if total > 0:
                    home_prob = home_price / total
                    away_prob = away_price / total
                else:
                    home_prob = away_prob = 0.5

                results.append({
                    'home_team': home_team,
                    'away_team': away_team,
                    'date': parsed['date_str'],
                    'home_win_prob': round(home_prob, 4),
                    'away_win_prob': round(away_prob, 4),
                    'home_last_price': home_price,
                    'away_last_price': away_price,
                    'total_volume': home_volume + away_volume,
                    'event_ticker': ticker,
                })
                logger.info(f"  {away_team} @ {home_team}: "
                           f"Home {home_prob:.0%} / Away {away_prob:.0%} "
                           f"(vol: {home_volume + away_volume})")

        logger.info(f"Kalshi: {len(results)} NBA games with prices" +
                    (f" for {target_date}" if target_date else ""))
        return results

    def match_to_engine_picks(self, kalshi_games: List[dict],
                               engine_picks: List[dict]) -> List[dict]:
        """
        Match Kalshi market data to engine picks by team names.
        
        Returns list of dicts combining engine pick + kalshi data.
        """
        # Build lookup by home team name (normalized)
        kalshi_by_home = {}
        for kg in kalshi_games:
            key = kg['home_team'].lower().strip()
            kalshi_by_home[key] = kg

        matched = []
        for pick in engine_picks:
            home = pick.get('home_team', pick.get('home', '')).strip()
            away = pick.get('away_team', pick.get('away', '')).strip()
            
            kalshi = kalshi_by_home.get(home.lower())
            if kalshi:
                matched.append({
                    'engine_pick': pick,
                    'kalshi': kalshi,
                    'matched': True,
                })
            else:
                matched.append({
                    'engine_pick': pick,
                    'kalshi': None,
                    'matched': False,
                })
                logger.debug(f"No Kalshi match for: {away} @ {home}")

        matched_count = sum(1 for m in matched if m['matched'])
        logger.info(f"Matched {matched_count}/{len(engine_picks)} engine picks to Kalshi markets")
        return matched


def get_kalshi_nba_probs(target_date: str = None) -> List[dict]:
    """Convenience function: fetch Kalshi NBA game probabilities."""
    client = KalshiClient()
    return client.fetch_nba_game_markets(target_date=target_date)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from datetime import date as d
    today = d.today().strftime('%Y-%m-%d')
    print(f"\nFetching Kalshi NBA markets for {today}...")
    games = get_kalshi_nba_probs(target_date=today)
    if not games:
        print("No Kalshi NBA game markets found for today. Trying all active...")
        games = get_kalshi_nba_probs()
    print(f"\n{len(games)} games found:")
    for g in games:
        print(f"  {g['away_team']} @ {g['home_team']}: "
              f"Home {g['home_win_prob']:.0%} / Away {g['away_win_prob']:.0%} "
              f"(vol: {g['total_volume']})")
