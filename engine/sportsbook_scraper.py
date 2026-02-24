"""
Sportsbook Scraper — DraftKings, FanDuel (Playwright), and Odds API.
Each scraper returns standardized game dicts.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("sportsbook_scraper")

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"


@dataclass
class GameLine:
    home_team: str
    away_team: str
    start_time: Optional[str]  # ISO format or descriptive
    spread_home: Optional[float]
    spread_away: Optional[float]
    total: Optional[float]
    moneyline_home: Optional[int]
    moneyline_away: Optional[int]
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# DraftKings Scraper — uses their public sportsbook API (JSON), no browser needed
# ---------------------------------------------------------------------------
class DraftKingsScraper:
    """
    Scrapes DraftKings NCAAB odds via their public API endpoints.
    DK exposes JSON APIs that power their frontend — much more reliable than DOM scraping.
    """

    # DK event group for NCAAB = 92483
    # Category IDs: 486 = game lines, 487 = spreads, etc.
    BASE_URL = "https://sportsbook-nash-usmi.draftkings.com/sites/US-MI-SB/api/v5/eventgroups/92483"
    ALT_URLS = [
        "https://sportsbook-nash-usva.draftkings.com/sites/US-VA-SB/api/v5/eventgroups/92483",
        "https://sportsbook-nash-usco.draftkings.com/sites/US-CO-SB/api/v5/eventgroups/92483",
        "https://sportsbook-nash-uspa.draftkings.com/sites/US-SB/api/v5/eventgroups/92483",
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://sportsbook.draftkings.com",
        "Referer": "https://sportsbook.draftkings.com/",
    }

    async def scrape(self) -> list[GameLine]:
        """Fetch all NCAAB games from DraftKings API."""
        games = []
        urls_to_try = [self.BASE_URL] + self.ALT_URLS

        for url in urls_to_try:
            try:
                games = await self._fetch_from_url(url)
                if games:
                    logger.info(f"DraftKings: got {len(games)} games from {url}")
                    return games
            except Exception as e:
                logger.warning(f"DraftKings URL {url} failed: {e}")
                continue

        # Fallback: try the category-based endpoint
        try:
            games = await self._fetch_category_endpoint()
            if games:
                logger.info(f"DraftKings (category): got {len(games)} games")
                return games
        except Exception as e:
            logger.warning(f"DraftKings category endpoint failed: {e}")

        logger.error("DraftKings: all endpoints failed")
        return games

    async def _fetch_from_url(self, url: str) -> list[GameLine]:
        params = {"format": "json"}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=self.HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
        return self._parse_eventgroup(data)

    async def _fetch_category_endpoint(self) -> list[GameLine]:
        """Try the subcategory/offer endpoint."""
        url = "https://sportsbook-nash-usmi.draftkings.com/sites/US-MI-SB/api/v5/eventgroups/92483/categories/486"
        params = {"format": "json"}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=self.HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
        return self._parse_eventgroup(data)

    def _parse_eventgroup(self, data: dict) -> list[GameLine]:
        games = []
        events = {}

        # Extract events
        event_group = data.get("eventGroup", {})
        for ev in event_group.get("events", []) or data.get("events", []):
            eid = ev.get("eventId")
            if not eid:
                continue
            # Parse team names from event name "Away @ Home" or "Away vs Home"
            name = ev.get("name", "")
            start = ev.get("startDate", "")
            teams = self._parse_event_name(name)
            if teams:
                events[eid] = {"away": teams[0], "home": teams[1], "start": start}

        if not events:
            # Try alternate structure
            for ev in data.get("events", []):
                eid = ev.get("eventId") or ev.get("id")
                if not eid:
                    continue
                name = ev.get("name", "")
                start = ev.get("startDate", "")
                teams = self._parse_event_name(name)
                if teams:
                    events[eid] = {"away": teams[0], "home": teams[1], "start": start}

        # Extract offer categories (spreads, totals, moneylines)
        offer_map = {}  # eventId → {spread_home, total, ml_home, ml_away, spread_away}
        offer_categories = data.get("offerCategories", []) or event_group.get("offerCategories", [])

        for cat in offer_categories:
            cat_name = (cat.get("name") or "").lower()
            for subcat in cat.get("offerSubcategoryDescriptors", []):
                for offer in subcat.get("offerSubcategory", {}).get("offers", []):
                    if isinstance(offer, list):
                        for o in offer:
                            self._extract_offer(o, offer_map, cat_name)
                    elif isinstance(offer, dict):
                        self._extract_offer(offer, offer_map, cat_name)

        # Build GameLine objects
        for eid, info in events.items():
            odds = offer_map.get(eid, {})
            games.append(GameLine(
                home_team=info["home"],
                away_team=info["away"],
                start_time=info["start"],
                spread_home=odds.get("spread_home"),
                spread_away=odds.get("spread_away"),
                total=odds.get("total"),
                moneyline_home=odds.get("ml_home"),
                moneyline_away=odds.get("ml_away"),
                source="draftkings",
            ))

        return games

    def _extract_offer(self, offer: dict, offer_map: dict, cat_name: str):
        eid = offer.get("eventId")
        if not eid:
            return
        if eid not in offer_map:
            offer_map[eid] = {}

        label = (offer.get("label") or "").lower()
        outcomes = offer.get("outcomes", [])

        if "spread" in label or "spread" in cat_name:
            for o in outcomes:
                line = o.get("line")
                ol = (o.get("label") or "").lower()
                participant = o.get("participant", "")
                if line is not None:
                    # DK labels outcomes by team name; we store both
                    if "home" in ol or o.get("type") == "home":
                        offer_map[eid]["spread_home"] = float(line)
                    elif "away" in ol or o.get("type") == "away":
                        offer_map[eid]["spread_away"] = float(line)
                    else:
                        # First outcome = away spread, second = home spread typically
                        if "spread_away" not in offer_map[eid]:
                            offer_map[eid]["spread_away"] = float(line)
                        else:
                            offer_map[eid]["spread_home"] = float(line)

        elif "total" in label or "total" in cat_name:
            for o in outcomes:
                line = o.get("line")
                if line is not None:
                    offer_map[eid]["total"] = float(line)
                    break

        elif "moneyline" in label or "money" in cat_name:
            for i, o in enumerate(outcomes):
                odds_am = o.get("oddsAmerican")
                if odds_am:
                    try:
                        val = int(odds_am.replace("+", ""))
                    except (ValueError, AttributeError):
                        val = None
                    if val is not None:
                        if i == 0:
                            offer_map[eid]["ml_away"] = val
                        else:
                            offer_map[eid]["ml_home"] = val

    def _parse_event_name(self, name: str) -> Optional[tuple[str, str]]:
        """Parse 'Away @ Home' or 'Away vs Home' into (away, home)."""
        for sep in [" @ ", " at ", " vs ", " vs. ", " v "]:
            if sep in name.lower():
                idx = name.lower().index(sep)
                away = name[:idx].strip()
                home = name[idx + len(sep):].strip()
                if away and home:
                    return (away, home)
        return None


# ---------------------------------------------------------------------------
# FanDuel Scraper — uses their public API
# ---------------------------------------------------------------------------
class FanDuelScraper:
    """
    Scrapes FanDuel odds via their public API.
    Supports: ncaab, nba, nhl
    """

    BASE_URL = "https://sbapi.mi.sportsbook.fanduel.com/api/content-managed-page"
    ALT_URLS = [
        "https://sbapi.va.sportsbook.fanduel.com/api/content-managed-page",
        "https://sbapi.co.sportsbook.fanduel.com/api/content-managed-page",
        "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page",
        "https://sbapi.pa.sportsbook.fanduel.com/api/content-managed-page",
    ]
    SPORT_PAGE_IDS = {
        "ncaab": "ncaab",
        "nba": "nba",
        "nhl": "nhl",
    }

    def __init__(self, sport: str = "ncaab"):
        self.sport = sport

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://sportsbook.fanduel.com",
        "Referer": "https://sportsbook.fanduel.com/",
    }

    async def scrape(self) -> list[GameLine]:
        urls = [self.BASE_URL] + self.ALT_URLS
        for url in urls:
            try:
                games = await self._fetch(url)
                if games:
                    logger.info(f"FanDuel: got {len(games)} games from {url}")
                    return games
            except Exception as e:
                logger.warning(f"FanDuel URL {url} failed: {e}")
                continue

        logger.error("FanDuel: all endpoints failed")
        return []

    async def _fetch(self, base_url: str) -> list[GameLine]:
        params = {
            "page": "CUSTOM",
            "customPageId": self.SPORT_PAGE_IDS.get(self.sport, self.sport),
            "pbHorizontal": "false",
            "_ak": "FhMFpcPWXMeyZxOx",
            "timezone": "America/New_York",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(base_url, headers=self.HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()

        return self._parse_response(data)

    def _parse_response(self, data: dict) -> list[GameLine]:
        games = []
        attachments = data.get("attachments", {})
        events = attachments.get("events", {})
        markets = attachments.get("markets", {})
        competitions = attachments.get("competitions", {})

        # Build market lookup by event
        event_markets: dict[str, dict] = {}  # eventId → {spread, total, ml}
        for mid, mkt in markets.items():
            eid = str(mkt.get("eventId", ""))
            if not eid:
                continue
            if eid not in event_markets:
                event_markets[eid] = {}
            mtype = (mkt.get("marketType") or "").upper()
            runners = mkt.get("runners", [])

            if "SPREAD" in mtype or "HANDICAP" in mtype:
                for r in runners:
                    handicap = r.get("handicap")
                    if handicap is not None:
                        result = r.get("result", {})
                        rtype = (result.get("type") or r.get("type", "")).upper()
                        if rtype == "HOME":
                            event_markets[eid]["spread_home"] = float(handicap)
                        elif rtype == "AWAY":
                            event_markets[eid]["spread_away"] = float(handicap)
                        else:
                            if "spread_away" not in event_markets[eid]:
                                event_markets[eid]["spread_away"] = float(handicap)
                            else:
                                event_markets[eid]["spread_home"] = float(handicap)

            elif "TOTAL" in mtype or "OVER_UNDER" in mtype:
                for r in runners:
                    handicap = r.get("handicap")
                    if handicap is not None:
                        event_markets[eid]["total"] = float(handicap)
                        break

            elif "MONEYLINE" in mtype or "MATCH_ODDS" in mtype or "MONEY" in mtype:
                for r in runners:
                    price = r.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                    if price is None:
                        # try decimal conversion
                        dec = r.get("winRunnerOdds", {}).get("trueOdds", {}).get("decimalOdds", {}).get("decimalOdds")
                        if dec:
                            price = self._decimal_to_american(float(dec))
                    if price is not None:
                        result = r.get("result", {})
                        rtype = (result.get("type") or r.get("type", "")).upper()
                        if rtype == "HOME":
                            event_markets[eid]["ml_home"] = int(price)
                        elif rtype == "AWAY":
                            event_markets[eid]["ml_away"] = int(price)

        # Build game objects
        for eid, ev in events.items():
            name = ev.get("name", "")
            home = ev.get("homeTeamName") or ""
            away = ev.get("awayTeamName") or ""

            if not home or not away:
                teams = self._parse_name(name)
                if teams:
                    away, home = teams
                else:
                    continue

            start = ev.get("openDate", "")
            odds = event_markets.get(eid, {})

            comp_id = str(ev.get("competitionId", ""))
            comp = competitions.get(comp_id, {})
            comp_name = (comp.get("name") or "").lower()

            # Filter to basketball / ncaab
            type_id = ev.get("typeId")
            # Accept all events from the ncaab page

            games.append(GameLine(
                home_team=home,
                away_team=away,
                start_time=start,
                spread_home=odds.get("spread_home"),
                spread_away=odds.get("spread_away"),
                total=odds.get("total"),
                moneyline_home=odds.get("ml_home"),
                moneyline_away=odds.get("ml_away"),
                source="fanduel",
            ))

        return games

    def _parse_name(self, name: str) -> Optional[tuple[str, str]]:
        for sep in [" @ ", " at ", " vs ", " v "]:
            if sep in name.lower():
                idx = name.lower().index(sep)
                away = name[:idx].strip()
                home = name[idx + len(sep):].strip()
                return (away, home)
        return None

    @staticmethod
    def _decimal_to_american(dec: float) -> int:
        if dec >= 2.0:
            return int(round((dec - 1) * 100))
        else:
            return int(round(-100 / (dec - 1)))


# ---------------------------------------------------------------------------
# Odds API Scraper
# ---------------------------------------------------------------------------
class OddsAPIScraper:
    """Uses the-odds-api.com as a third source. Supports ncaab, nba, nhl."""

    SPORT_KEYS = {
        "ncaab": "basketball_ncaab",
        "nba": "basketball_nba",
        "nhl": "icehockey_nhl",
    }

    def __init__(self, sport: str = "ncaab"):
        self.sport = sport
        self.BASE_URL = f"https://api.the-odds-api.com/v4/sports/{self.SPORT_KEYS.get(sport, sport)}/odds"

    async def scrape(self) -> list[GameLine]:
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "american",
            "bookmakers": "draftkings,fanduel",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        games = []
        for event in data:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            start = event.get("commence_time", "")

            spread_home = None
            spread_away = None
            total = None
            ml_home = None
            ml_away = None

            for bm in event.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    key = mkt.get("key", "")
                    outcomes = mkt.get("outcomes", [])

                    if key == "h2h":
                        for o in outcomes:
                            if o.get("name") == home:
                                ml_home = ml_home or o.get("price")
                            elif o.get("name") == away:
                                ml_away = ml_away or o.get("price")

                    elif key == "spreads":
                        for o in outcomes:
                            if o.get("name") == home:
                                spread_home = spread_home or o.get("point")
                            elif o.get("name") == away:
                                spread_away = spread_away or o.get("point")

                    elif key == "totals":
                        for o in outcomes:
                            if o.get("name") == "Over":
                                total = total or o.get("point")

            games.append(GameLine(
                home_team=home,
                away_team=away,
                start_time=start,
                spread_home=spread_home,
                spread_away=spread_away,
                total=total,
                moneyline_home=ml_home,
                moneyline_away=ml_away,
                source="odds_api",
            ))

        logger.info(f"OddsAPI: got {len(games)} games")
        return games


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------
async def scrape_all() -> dict[str, list[GameLine]]:
    """Run all scrapers and return results keyed by source."""
    dk = DraftKingsScraper()
    fd = FanDuelScraper()
    oa = OddsAPIScraper()

    results = await asyncio.gather(
        dk.scrape(),
        fd.scrape(),
        oa.scrape(),
        return_exceptions=True,
    )

    out = {}
    for scraper_name, result in zip(["draftkings", "fanduel", "odds_api"], results):
        if isinstance(result, Exception):
            logger.error(f"{scraper_name} failed: {result}")
            out[scraper_name] = []
        else:
            out[scraper_name] = result

    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(scrape_all())
    for source, games in results.items():
        print(f"\n{'='*60}")
        print(f"{source}: {len(games)} games")
        for g in games[:3]:
            print(f"  {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} ML={g.moneyline_home}/{g.moneyline_away}")
