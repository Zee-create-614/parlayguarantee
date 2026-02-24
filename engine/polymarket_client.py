#!/usr/bin/env python3
"""
polymarket_client.py — Polymarket Prediction Market Integration
================================================================
Fetches sports-related prediction markets from Polymarket's Gamma API
and maps them to ParlayGuarantee games for edge detection.

When our model disagrees with market consensus, that signals potential edge.

API Docs: https://docs.polymarket.com
Gamma API: https://gamma-api.polymarket.com

NOTE (2026-02-23): Polymarket currently has very few individual game-outcome
markets for NBA/NCAAB. Most sports markets are season-long (championship winner,
MVP, etc.). This module is built to handle both:
  1. Game-level markets (when available) — direct probability comparison
  2. Season-level markets (championship, etc.) — team strength signal

The integration is ready for when Polymarket expands sports coverage.
"""

import json, logging, re, requests, time
from datetime import datetime, date, timedelta, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("polymarket")

GAMMA_API = "https://gamma-api.polymarket.com"
EST = timezone(timedelta(hours=-5))

# ─── Team Name Normalization ──────────────────────────────────────────
# Maps Polymarket question text variants to our canonical team names
TEAM_ALIASES = {
    # NBA
    "celtics": "Boston Celtics", "boston": "Boston Celtics",
    "lakers": "Los Angeles Lakers", "la lakers": "Los Angeles Lakers",
    "clippers": "LA Clippers", "la clippers": "LA Clippers",
    "warriors": "Golden State Warriors", "golden state": "Golden State Warriors",
    "bucks": "Milwaukee Bucks", "milwaukee": "Milwaukee Bucks",
    "76ers": "Philadelphia 76ers", "sixers": "Philadelphia 76ers", "philly": "Philadelphia 76ers",
    "nets": "Brooklyn Nets", "brooklyn": "Brooklyn Nets",
    "knicks": "New York Knicks", "ny knicks": "New York Knicks",
    "heat": "Miami Heat", "miami": "Miami Heat",
    "bulls": "Chicago Bulls", "chicago": "Chicago Bulls",
    "cavs": "Cleveland Cavaliers", "cavaliers": "Cleveland Cavaliers", "cleveland": "Cleveland Cavaliers",
    "pistons": "Detroit Pistons", "detroit": "Detroit Pistons",
    "pacers": "Indiana Pacers", "indiana": "Indiana Pacers",
    "magic": "Orlando Magic", "orlando": "Orlando Magic",
    "raptors": "Toronto Raptors", "toronto": "Toronto Raptors",
    "hawks": "Atlanta Hawks", "atlanta": "Atlanta Hawks",
    "hornets": "Charlotte Hornets", "charlotte": "Charlotte Hornets",
    "wizards": "Washington Wizards", "washington": "Washington Wizards",
    "mavericks": "Dallas Mavericks", "mavs": "Dallas Mavericks", "dallas": "Dallas Mavericks",
    "rockets": "Houston Rockets", "houston": "Houston Rockets",
    "grizzlies": "Memphis Grizzlies", "memphis": "Memphis Grizzlies",
    "pelicans": "New Orleans Pelicans", "new orleans": "New Orleans Pelicans",
    "spurs": "San Antonio Spurs", "san antonio": "San Antonio Spurs",
    "nuggets": "Denver Nuggets", "denver": "Denver Nuggets",
    "timberwolves": "Minnesota Timberwolves", "wolves": "Minnesota Timberwolves", "minnesota": "Minnesota Timberwolves",
    "thunder": "Oklahoma City Thunder", "okc": "Oklahoma City Thunder", "oklahoma city": "Oklahoma City Thunder",
    "trail blazers": "Portland Trail Blazers", "blazers": "Portland Trail Blazers", "portland": "Portland Trail Blazers",
    "jazz": "Utah Jazz", "utah": "Utah Jazz",
    "kings": "Sacramento Kings", "sacramento": "Sacramento Kings",
    "suns": "Phoenix Suns", "phoenix": "Phoenix Suns",
}


def normalize_team(text: str) -> Optional[str]:
    """Try to match text to a canonical team name."""
    text_lower = text.lower().strip()
    # Direct alias match
    for alias, canonical in TEAM_ALIASES.items():
        if alias in text_lower:
            return canonical
    # Fuzzy match against canonical names
    for canonical in set(TEAM_ALIASES.values()):
        if SequenceMatcher(None, text_lower, canonical.lower()).ratio() > 0.8:
            return canonical
    return None


# ─── API Client ───────────────────────────────────────────────────────

class PolymarketClient:
    """Client for Polymarket's Gamma API."""

    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.timeout = timeout
        self._cache = {}

    def _get(self, endpoint: str, params: dict = None) -> list:
        """GET request with retry."""
        url = f"{GAMMA_API}/{endpoint}"
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params or {}, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                log.warning(f"Polymarket API attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        return []

    def search_markets(self, query: str, limit: int = 50, active_only: bool = True) -> list:
        """Search markets by text query."""
        params = {"_q": query, "_limit": limit}
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"
        return self._get("markets", params)

    def search_events(self, query: str, limit: int = 20, active_only: bool = True) -> list:
        """Search events (groups of related markets)."""
        params = {"_q": query, "_limit": limit}
        if active_only:
            params["active"] = "true"
            params["closed"] = "false"
        return self._get("events", params)

    def get_sports_markets(self, sports: List[str] = None) -> Dict[str, list]:
        """
        Fetch all available sports markets from Polymarket.
        Searches for game-level and season-level markets.
        
        Returns dict keyed by sport: {'NBA': [...], 'NCAAB': [...], ...}
        """
        if sports is None:
            sports = ["NBA", "NCAAB", "NHL", "UFC", "NFL", "MLB"]

        search_terms = []
        for sport in sports:
            search_terms.extend([
                sport,
                f"{sport} winner",
                f"{sport} champion",
                f"{sport} game",
                f"{sport} finals",
            ])
        # Also search team names for game-level markets
        game_terms = [
            "Celtics", "Lakers", "Warriors", "Bucks", "Thunder",
            "Nuggets", "Suns", "Knicks", "Cavaliers", "Grizzlies",
        ]
        search_terms.extend(game_terms)

        all_markets = {}
        seen_ids = set()

        for term in search_terms:
            markets = self.search_markets(term, limit=20)
            for m in markets:
                mid = m.get("id")
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)

                # Classify as sports-related
                question = m.get("question", "").lower()
                description = m.get("description", "").lower()
                text = question + " " + description

                sport_match = None
                for sport in sports:
                    if sport.lower() in text or any(
                        alias in text for alias, canon in TEAM_ALIASES.items()
                        if sport == "NBA"  # Only check NBA aliases for now
                    ):
                        sport_match = sport
                        break

                if sport_match:
                    m["_matched_sport"] = sport_match
                    m["_market_type"] = self._classify_market_type(m)
                    all_markets.setdefault(sport_match, []).append(m)

        log.info(f"Found {sum(len(v) for v in all_markets.values())} sports markets across {len(all_markets)} sports")
        return all_markets

    def _classify_market_type(self, market: dict) -> str:
        """Classify market as 'game', 'championship', 'mvp', 'playoff', or 'other'."""
        q = market.get("question", "").lower()
        if any(kw in q for kw in ["champion", "win the", "finals"]):
            return "championship"
        elif any(kw in q for kw in ["mvp", "most valuable"]):
            return "mvp"
        elif any(kw in q for kw in ["playoff", "make the playoff"]):
            return "playoff"
        elif any(kw in q for kw in [" vs ", " beat ", " win against", " defeat"]):
            return "game"
        else:
            return "other"

    def get_game_markets(self, target_date: str = None) -> List[dict]:
        """
        Find individual game outcome markets for a specific date.
        Returns list of dicts with: home, away, date, market_prob_home, market_prob_away.
        
        NOTE: Polymarket rarely has individual game markets as of 2026-02.
        This is built for future expansion.
        """
        if target_date is None:
            target_date = datetime.now(EST).strftime("%Y-%m-%d")

        game_markets = []
        sports_markets = self.get_sports_markets(["NBA", "NCAAB"])

        for sport, markets in sports_markets.items():
            for m in markets:
                if m.get("_market_type") != "game":
                    continue

                # Parse teams from question
                q = m.get("question", "")
                teams = self._extract_teams_from_question(q)
                if not teams:
                    continue

                # Check if market date matches
                end_date = m.get("endDateIso", "")
                if target_date and end_date and end_date != target_date:
                    continue

                # Extract probabilities
                try:
                    prices = json.loads(m.get("outcomePrices", "[]"))
                    outcomes = json.loads(m.get("outcomes", "[]"))
                except:
                    continue

                if len(prices) >= 2 and len(outcomes) >= 2:
                    prob_map = {}
                    for outcome, price in zip(outcomes, prices):
                        team = normalize_team(outcome)
                        if team:
                            prob_map[team] = float(price)

                    if prob_map:
                        game_markets.append({
                            "sport": sport,
                            "market_id": m.get("id"),
                            "question": q,
                            "teams": teams,
                            "probabilities": prob_map,
                            "volume": m.get("volumeNum", 0),
                            "liquidity": m.get("liquidityNum", 0),
                        })

        log.info(f"Found {len(game_markets)} game-level markets for {target_date}")
        return game_markets

    def get_championship_signals(self) -> Dict[str, float]:
        """
        Get championship market probabilities as a team strength signal.
        Higher championship probability = stronger team overall.
        Returns dict of {team_name: championship_probability}.
        """
        signals = {}
        events = self.search_events("NBA champion", limit=10)
        events.extend(self.search_events("NBA championship", limit=10))

        seen = set()
        for event in events:
            for market in event.get("markets", []):
                mid = market.get("id")
                if mid in seen:
                    continue
                seen.add(mid)

                q = market.get("question", "")
                try:
                    prices = json.loads(market.get("outcomePrices", "[]"))
                    outcomes = json.loads(market.get("outcomes", "[]"))
                except:
                    continue

                for outcome, price in zip(outcomes, prices):
                    team = normalize_team(outcome)
                    if team and float(price) > 0:
                        signals[team] = max(signals.get(team, 0), float(price))

        log.info(f"Championship signals for {len(signals)} teams")
        return signals

    def _extract_teams_from_question(self, question: str) -> List[str]:
        """Extract team names from a market question like 'Will Celtics beat Lakers?'"""
        teams = []
        for alias, canonical in TEAM_ALIASES.items():
            if alias in question.lower() and canonical not in teams:
                teams.append(canonical)
        return teams[:2]  # Max 2 teams per game


# ─── Integration with ParlayGuarantee ────────────────────────────────

def compare_with_model(picks: List[dict], polymarket: PolymarketClient) -> List[dict]:
    """
    Compare our model's picks with Polymarket consensus.
    
    For each pick, adds:
      - pm_market_found: bool — whether Polymarket has a relevant market
      - pm_game_prob: float — Polymarket's game-level probability (if available)
      - pm_championship_signal: float — team's championship probability (strength proxy)
      - pm_divergence: float — our prob minus Polymarket prob (positive = we're more bullish)
      - pm_edge_flag: bool — True if divergence exceeds threshold (potential edge)
    
    Returns enriched picks list.
    """
    # Get championship signals as team strength proxy
    championship_signals = polymarket.get_championship_signals()

    # Get any game-level markets
    game_markets = polymarket.get_game_markets()
    game_lookup = {}
    for gm in game_markets:
        for team in gm.get("teams", []):
            game_lookup[team] = gm

    DIVERGENCE_THRESHOLD = 0.10  # 10% disagreement = edge flag

    enriched = []
    for pick in picks:
        p = dict(pick)  # Don't mutate original

        pick_team = p.get("pick", "")
        home = p.get("home", "")
        away = p.get("away", "")
        our_ml_prob = p.get("ml_prob", 0.5)

        # Check for game-level market
        game_market = game_lookup.get(home) or game_lookup.get(away)
        if game_market:
            probs = game_market.get("probabilities", {})
            pm_prob = probs.get(pick_team, None)
            if pm_prob is not None:
                p["pm_market_found"] = True
                p["pm_game_prob"] = pm_prob
                p["pm_divergence"] = round(our_ml_prob - pm_prob, 4)
                p["pm_edge_flag"] = abs(p["pm_divergence"]) >= DIVERGENCE_THRESHOLD
                p["pm_source"] = "game_market"
                enriched.append(p)
                continue

        # Fall back to championship signal as strength proxy
        pick_signal = championship_signals.get(pick_team, 0)
        opp_team = away if pick_team == home else home
        opp_signal = championship_signals.get(opp_team, 0)

        if pick_signal > 0 or opp_signal > 0:
            # Convert championship odds to relative game strength
            total = pick_signal + opp_signal
            if total > 0:
                pm_implied = pick_signal / total
            else:
                pm_implied = 0.5

            p["pm_market_found"] = True
            p["pm_championship_pick"] = pick_signal
            p["pm_championship_opp"] = opp_signal
            p["pm_implied_strength"] = round(pm_implied, 4)
            p["pm_divergence"] = round(our_ml_prob - pm_implied, 4)
            p["pm_edge_flag"] = abs(p["pm_divergence"]) >= DIVERGENCE_THRESHOLD
            p["pm_source"] = "championship_proxy"
        else:
            p["pm_market_found"] = False
            p["pm_divergence"] = 0
            p["pm_edge_flag"] = False
            p["pm_source"] = "none"

        enriched.append(p)

    return enriched


# ─── Standalone Usage ─────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    client = PolymarketClient()

    print("\n═══ Polymarket Sports Market Scan ═══\n")

    # Scan all sports markets
    sports_markets = client.get_sports_markets()
    for sport, markets in sports_markets.items():
        print(f"\n{sport}: {len(markets)} markets found")
        for m in markets[:5]:
            q = m.get("question", "")[:80]
            vol = m.get("volumeNum", 0)
            mtype = m.get("_market_type", "?")
            print(f"  [{mtype}] {q}  (vol: ${vol:,.0f})")

    # Championship signals
    print("\n═══ Championship Strength Signals ═══\n")
    signals = client.get_championship_signals()
    for team, prob in sorted(signals.items(), key=lambda x: -x[1])[:15]:
        print(f"  {team}: {prob:.1%}")

    # Game-level markets
    print("\n═══ Game Markets (Today) ═══\n")
    games = client.get_game_markets()
    if games:
        for g in games:
            print(f"  {g['question']}  →  {g['probabilities']}")
    else:
        print("  No individual game markets found on Polymarket today.")
        print("  (Polymarket focuses on politics/events; sports game markets are rare)")
