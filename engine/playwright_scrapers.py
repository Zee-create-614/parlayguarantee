"""
Phase 2: Playwright-based sportsbook scrapers.
Intercepts API responses that the browser fetches after handling geo-checks.
Works from Ohio (or anywhere) — browser handles geo/JS verification, we capture the data.

Supports: DraftKings, Caesars/ESPN BET, BetMGM
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger("playwright_scrapers")

# Re-use the existing GameLine dataclass
try:
    from sportsbook_scraper import GameLine
except ImportError:
    from dataclasses import dataclass, asdict

    @dataclass
    class GameLine:
        home_team: str
        away_team: str
        start_time: Optional[str]
        spread_home: Optional[float]
        spread_away: Optional[float]
        total: Optional[float]
        moneyline_home: Optional[int]
        moneyline_away: Optional[int]
        source: str

        def to_dict(self) -> dict:
            return asdict(self)


# ─── Browser context helpers ───────────────────────────────────────────────

async def _make_context(pw, headless=True):
    """Create a browser context that looks like a real user in Ohio."""
    browser = await pw.chromium.launch(headless=headless)
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="America/New_York",
        ignore_https_errors=True,
        geolocation={"latitude": 39.9612, "longitude": -82.9988},  # Columbus OH
        permissions=["geolocation"],
        viewport={"width": 1920, "height": 1080},
    )
    return browser, ctx


def _parse_event_name(name: str) -> Optional[tuple[str, str]]:
    """Parse 'Away @ Home' or 'Away vs Home' → (away, home)."""
    for sep in [" @ ", " at ", " vs ", " vs. ", " v "]:
        low = name.lower()
        if sep in low:
            idx = low.index(sep)
            away = name[:idx].strip()
            home = name[idx + len(sep):].strip()
            if away and home:
                return (away, home)
    return None


# ─── DraftKings ────────────────────────────────────────────────────────────

async def scrape_draftkings(sport: str = "ncaab", headless: bool = True) -> list[GameLine]:
    """
    Scrape DraftKings via Playwright interception.
    Opens the NCAAB page, captures sportsbook-nash API calls.
    """
    sport_urls = {
        "ncaab": "https://sportsbook.draftkings.com/leagues/basketball/ncaab",
        "nba": "https://sportsbook.draftkings.com/leagues/basketball/nba",
        "nhl": "https://sportsbook.draftkings.com/leagues/hockey/nhl",
        "mlb": "https://sportsbook.draftkings.com/leagues/baseball/mlb",
    }
    url = sport_urls.get(sport, sport_urls["ncaab"])
    captured = []

    async with async_playwright() as pw:
        browser, ctx = await _make_context(pw, headless)
        page = await ctx.new_page()

        async def on_response(response):
            u = response.url
            if "sportsbook-nash" in u and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    try:
                        body = await response.json()
                        size = len(json.dumps(body))
                        if size > 5000:
                            captured.append((u, body))
                    except Exception:
                        pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(10)

            # Scroll to trigger lazy loads
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 3000)")
                await asyncio.sleep(2)

            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"DraftKings page load failed: {e}")
        finally:
            await browser.close()

    if not captured:
        logger.warning("DraftKings: no API responses captured")
        return []

    # Parse the biggest response (usually the eventgroup data)
    captured.sort(key=lambda x: -len(json.dumps(x[1])))
    games = []

    for url_str, data in captured:
        parsed = _parse_dk_response(data)
        if parsed:
            games.extend(parsed)

    # Dedupe by home+away
    seen = set()
    unique = []
    for g in games:
        key = (g.home_team.lower(), g.away_team.lower())
        if key not in seen:
            seen.add(key)
            unique.append(g)

    logger.info(f"DraftKings: {len(unique)} games scraped via Playwright")
    return unique


def _parse_dk_response(data: dict) -> list[GameLine]:
    """Parse DK JSON into GameLine objects. Handles BOTH formats:
    - Legacy: eventGroup → events + offerCategories
    - New (Ohio): flat events[] + markets[] + selections[]
    """
    # Detect new flat format
    if "markets" in data and "selections" in data and "events" in data:
        return _parse_dk_flat(data)

    # Legacy eventGroup format
    games = []
    events = {}
    event_group = data.get("eventGroup", data)

    for ev in event_group.get("events", []) or data.get("events", []):
        eid = ev.get("eventId") or ev.get("id")
        if not eid:
            continue
        name = ev.get("name", "")
        start = ev.get("startDate", ev.get("startEventDate", ""))

        participants = ev.get("participants", [])
        home = away = None
        for p in participants:
            role = (p.get("venueRole") or "").lower()
            pname = p.get("name", "")
            if role == "home":
                home = pname
            elif role == "away":
                away = pname

        if not home or not away:
            teams = _parse_event_name(name)
            if teams:
                away, home = teams
            else:
                continue

        events[str(eid)] = {"away": away, "home": home, "start": start}

    if not events:
        return games

    offer_map = {}
    offer_categories = event_group.get("offerCategories", []) or data.get("offerCategories", [])

    for cat in offer_categories:
        cat_name = (cat.get("name") or "").lower()
        for subcat in cat.get("offerSubcategoryDescriptors", []):
            offers_list = subcat.get("offerSubcategory", {}).get("offers", [])
            for offer in offers_list:
                if isinstance(offer, list):
                    for o in offer:
                        _extract_dk_offer(o, offer_map, cat_name)
                elif isinstance(offer, dict):
                    _extract_dk_offer(offer, offer_map, cat_name)

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


def _parse_dk_flat(data: dict) -> list[GameLine]:
    """Parse DK's new flat format: events[] + markets[] + selections[]."""
    games = []

    # Index events by id
    events = {}
    for ev in data.get("events", []):
        eid = str(ev.get("id", ""))
        if not eid:
            continue
        name = ev.get("name", "")
        start = ev.get("startEventDate", "")

        participants = ev.get("participants", [])
        home = away = None
        for p in participants:
            role = (p.get("venueRole") or "").lower()
            pname = p.get("name", "")
            if role == "home":
                home = pname
            elif role == "away":
                away = pname

        if not home or not away:
            teams = _parse_event_name(name)
            if teams:
                away, home = teams
            else:
                continue

        events[eid] = {"away": away, "home": home, "start": start}

    # Index markets by id, grouped by eventId
    market_map = {}  # marketId → {eventId, type}
    for m in data.get("markets", []):
        mid = str(m.get("id", ""))
        eid = str(m.get("eventId", ""))
        mtype = (m.get("marketType", {}).get("name") or m.get("name") or "").lower()
        market_map[mid] = {"eventId": eid, "type": mtype}

    # Process selections to extract odds
    odds_map = {}  # eventId → {spread_home, spread_away, total, ml_home, ml_away}
    for s in data.get("selections", []):
        mid = str(s.get("marketId", ""))
        mkt = market_map.get(mid)
        if not mkt:
            continue
        eid = mkt["eventId"]
        mtype = mkt["type"]

        if eid not in odds_map:
            odds_map[eid] = {}

        outcome_type = (s.get("outcomeType") or "").lower()
        points = s.get("points")
        display_odds = s.get("displayOdds", {})
        american = display_odds.get("american", "")

        # Parse American odds
        am_val = None
        if american:
            try:
                am_val = int(american.replace("\u2212", "-").replace("+", "").replace("−", "-"))
                # Re-add the negative if it was there
                if "\u2212" in american or "−" in american or american.startswith("-"):
                    am_val = -abs(am_val)
            except (ValueError, TypeError):
                pass

        if "spread" in mtype:
            if points is not None:
                if outcome_type == "home":
                    odds_map[eid]["spread_home"] = float(points)
                elif outcome_type == "away":
                    odds_map[eid]["spread_away"] = float(points)

        elif "total" in mtype:
            if points is not None and outcome_type in ("over", ""):
                odds_map[eid]["total"] = float(points)

        elif "moneyline" in mtype or "money" in mtype:
            if am_val is not None:
                if outcome_type == "home":
                    odds_map[eid]["ml_home"] = am_val
                elif outcome_type == "away":
                    odds_map[eid]["ml_away"] = am_val

    # Build GameLine objects
    for eid, info in events.items():
        odds = odds_map.get(eid, {})
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


def _extract_dk_offer(offer: dict, offer_map: dict, cat_name: str):
    eid = str(offer.get("eventId", ""))
    if not eid:
        return
    if eid not in offer_map:
        offer_map[eid] = {}

    label = (offer.get("label") or "").lower()
    outcomes = offer.get("outcomes", [])

    if "spread" in label or "spread" in cat_name:
        for o in outcomes:
            line = o.get("line")
            if line is not None:
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
                    val = int(str(odds_am).replace("+", ""))
                except (ValueError, AttributeError):
                    continue
                if i == 0:
                    offer_map[eid]["ml_away"] = val
                else:
                    offer_map[eid]["ml_home"] = val


# ─── Caesars / ESPN BET ────────────────────────────────────────────────────

async def scrape_caesars(sport: str = "ncaab", headless: bool = True) -> list[GameLine]:
    """
    Scrape Caesars/ESPN BET via Playwright interception.
    Captures americanwagering.com API responses.
    """
    sport_urls = {
        "ncaab": "https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-ncaa",
        "nba": "https://sportsbook.caesars.com/us/oh/bet/basketball/events/basketball-usa-nba",
        "nhl": "https://sportsbook.caesars.com/us/oh/bet/ice-hockey/events/ice-hockey-usa-nhl",
    }
    url = sport_urls.get(sport, sport_urls["ncaab"])
    captured = []

    async with async_playwright() as pw:
        browser, ctx = await _make_context(pw, headless)
        page = await ctx.new_page()

        async def on_response(response):
            u = response.url
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                # Skip analytics/tracking
                skip = ["google", "facebook", "analytics", "sentry", "datadog",
                        "cookielaw", "fullstory", "onetrust", "omtrdc", "harrahs"]
                if any(s in u.lower() for s in skip):
                    return
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 2000:
                        captured.append((u, body, size))
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(15)

            # Scroll to load more events
            for _ in range(10):
                await page.evaluate("window.scrollBy(0, 1000)")
                await asyncio.sleep(1)

            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Caesars page load failed: {e}")
        finally:
            await browser.close()

    if not captured:
        logger.warning("Caesars: no API responses captured")
        return []

    # Find the event data in captured responses
    games = []
    for url_str, body, size in sorted(captured, key=lambda x: -x[2]):
        parsed = _parse_caesars_response(body)
        if parsed:
            games.extend(parsed)

    # Dedupe
    seen = set()
    unique = []
    for g in games:
        key = (g.home_team.lower(), g.away_team.lower())
        if key not in seen:
            seen.add(key)
            unique.append(g)

    logger.info(f"Caesars: {len(unique)} games scraped via Playwright")
    return unique


def _parse_caesars_response(data) -> list[GameLine]:
    """Parse Caesars event data. Structure varies by endpoint."""
    games = []

    # Try: list of competitions with events
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "competitions" in item:
                for comp in item["competitions"]:
                    for ev in comp.get("events", []):
                        g = _parse_caesars_event(ev)
                        if g:
                            games.append(g)
            elif isinstance(item, dict) and "events" in item:
                for ev in item["events"]:
                    g = _parse_caesars_event(ev)
                    if g:
                        games.append(g)
        return games

    if not isinstance(data, dict):
        return games

    # Try: dict with events list
    if "events" in data:
        for ev in data["events"]:
            g = _parse_caesars_event(ev)
            if g:
                games.append(g)

    # Try: dict with competitions
    if "competitions" in data:
        for comp in data["competitions"]:
            for ev in comp.get("events", []):
                g = _parse_caesars_event(ev)
                if g:
                    games.append(g)

    return games


def _parse_caesars_event(ev: dict) -> Optional[GameLine]:
    """Parse a single Caesars event into a GameLine."""
    name = ev.get("name", "")
    start = ev.get("startTime", ev.get("startDate", ""))

    # Get teams
    competitors = ev.get("competitors", [])
    home = away = None
    for c in competitors:
        role = (c.get("type") or c.get("homeAwayStatus") or "").lower()
        cname = c.get("name", "")
        if "home" in role:
            home = cname
        elif "away" in role:
            away = cname

    if not home or not away:
        teams = _parse_event_name(name)
        if teams:
            away, home = teams
        else:
            # Try " v " or " vs " in name
            parts = re.split(r'\s+(?:v|vs|@|at)\s+', name, flags=re.IGNORECASE)
            if len(parts) == 2:
                away, home = parts[0].strip(), parts[1].strip()
            else:
                return None

    # Get markets/odds
    spread_home = spread_away = total = ml_home = ml_away = None
    markets = ev.get("markets", ev.get("displayGroups", []))

    if isinstance(markets, list):
        for mkt in markets:
            if isinstance(mkt, dict):
                mtype = (mkt.get("type") or mkt.get("templateMarketName") or mkt.get("name") or "").lower()
                outcomes = mkt.get("outcomes", mkt.get("selections", []))

                if "spread" in mtype or "handicap" in mtype:
                    for o in outcomes:
                        line = o.get("line") or o.get("handicap") or o.get("points")
                        if line is not None:
                            oname = (o.get("name") or o.get("label") or "").lower()
                            if home and home.lower() in oname:
                                spread_home = float(line)
                            elif away and away.lower() in oname:
                                spread_away = float(line)
                            elif spread_away is None:
                                spread_away = float(line)
                            else:
                                spread_home = float(line)

                elif "total" in mtype or "over" in mtype:
                    for o in outcomes:
                        line = o.get("line") or o.get("handicap") or o.get("points")
                        if line is not None:
                            total = float(line)
                            break

                elif "moneyline" in mtype or "money" in mtype or "winner" in mtype:
                    for o in outcomes:
                        price = o.get("price") or o.get("americanOdds") or o.get("odds")
                        if price is not None:
                            oname = (o.get("name") or o.get("label") or "").lower()
                            try:
                                val = int(float(str(price).replace("+", "")))
                            except (ValueError, TypeError):
                                continue
                            if home and home.lower() in oname:
                                ml_home = val
                            elif away and away.lower() in oname:
                                ml_away = val
                            elif ml_away is None:
                                ml_away = val
                            else:
                                ml_home = val

    return GameLine(
        home_team=home,
        away_team=away,
        start_time=start,
        spread_home=spread_home,
        spread_away=spread_away,
        total=total,
        moneyline_home=ml_home,
        moneyline_away=ml_away,
        source="caesars",
    )


# ─── BetMGM ───────────────────────────────────────────────────────────────

async def scrape_betmgm(sport: str = "ncaab", headless: bool = False) -> list[GameLine]:
    """
    Scrape BetMGM via Playwright interception.
    Uses www.oh.betmgm.com (NOT sports.oh.betmgm.com) with headless=False.
    Requires 2-step navigation: home first, then sport page.
    """
    sport_urls = {
        "ncaab": "https://www.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/college-basketball-211",
        "nba": "https://www.oh.betmgm.com/en/sports/basketball-7/betting/usa-9/nba-6004",
        "nhl": "https://www.oh.betmgm.com/en/sports/ice-hockey-12/betting/usa-9/nhl-34",
    }
    # Competition IDs for filtering
    sport_comp_ids = {
        "ncaab": "211", "nba": "6004", "nhl": "34",
    }
    url = sport_urls.get(sport, sport_urls["ncaab"])
    comp_id = sport_comp_ids.get(sport, "211")
    captured = []

    async with async_playwright() as pw:
        browser, ctx = await _make_context(pw, headless)
        page = await ctx.new_page()

        async def on_response(response):
            u = response.url
            ct = response.headers.get("content-type", "")
            if response.status == 200 and "json" in ct and "cds-api" in u:
                try:
                    body = await response.json()
                    size = len(json.dumps(body))
                    if size > 5000:
                        captured.append((u, body, size))
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            # Step 1: Home page to set cookies
            await page.goto("https://www.oh.betmgm.com/en/sports",
                           wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

            # Step 2: Navigate to sport page
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(15)

            for _ in range(5):
                await page.evaluate("window.scrollBy(0, 2000)")
                await asyncio.sleep(1)

            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"BetMGM page load failed: {e}")
        finally:
            await browser.close()

    if not captured:
        logger.warning("BetMGM: no API responses captured")
        return []

    games = []
    # Process fixture-view and fixtures responses
    for url_str, body, size in sorted(captured, key=lambda x: -x[2]):
        parsed = _parse_betmgm_response(body)
        if parsed:
            games.extend(parsed)

    # Dedupe
    seen = set()
    unique = []
    for g in games:
        key = (g.home_team.lower(), g.away_team.lower())
        if key not in seen:
            seen.add(key)
            unique.append(g)

    # Filter to basketball only if we got all-sport data
    # (fixture-view responses from NCAAB page should already be filtered)
    logger.info(f"BetMGM: {len(unique)} games scraped via Playwright")
    return unique


def _parse_betmgm_response(data) -> list[GameLine]:
    """Parse BetMGM fixture/event data."""
    games = []

    if isinstance(data, dict):
        # BetMGM uses "fixtures" or "widgets" structure
        fixtures = data.get("fixtures", data.get("events", []))
        if not fixtures and "widgets" in data:
            for w in data["widgets"]:
                fixtures.extend(w.get("fixtures", w.get("events", [])))

        for fix in fixtures:
            g = _parse_betmgm_fixture(fix)
            if g:
                games.append(g)

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                g = _parse_betmgm_fixture(item)
                if g:
                    games.append(g)

    return games


def _parse_betmgm_fixture(fix: dict) -> Optional[GameLine]:
    """Parse a single BetMGM fixture."""
    name = fix.get("name", {})
    if isinstance(name, dict):
        name = name.get("value", "")

    start = fix.get("startDate", fix.get("startTime", ""))

    # Get participants — BetMGM includes players too, we want teams only
    participants = fix.get("participants", [])
    home = away = None

    # BetMGM uses "name" format "Away at Home" in the fixture name
    # Participants don't have venueRole, but we can parse from name
    if isinstance(name, str) and " at " in name.lower():
        teams = _parse_event_name(name)
        if teams:
            away, home = teams

    # If still no teams, try first two participants (usually team entries)
    if not home or not away:
        team_participants = [p for p in participants
                           if p.get("source", {}).get("name", "") not in ("", ) and
                           "(" not in (p.get("name", {}).get("value", "") if isinstance(p.get("name"), dict) else p.get("name", ""))]
        if not team_participants:
            # Just take first two
            team_participants = participants[:2]

        for i, p in enumerate(team_participants[:2]):
            pname = p.get("name", {})
            if isinstance(pname, dict):
                pname = pname.get("value", "")
            # Skip player names (contain parentheses like "Player (TEAM)")
            if "(" in pname:
                continue
            if i == 0 and not away:
                away = pname
            elif i == 1 and not home:
                home = pname

    if not home or not away:
        return None

    # Get odds from games/results
    spread_home = spread_away = total = ml_home = ml_away = None
    games_list = fix.get("games", [])

    for game in games_list:
        gname = game.get("name", {})
        if isinstance(gname, dict):
            gname = gname.get("value", "")
        gname = (gname or "").lower()

        results = game.get("results", [])

        if "spread" in gname or "handicap" in gname:
            for r in results:
                rname = r.get("name", {})
                if isinstance(rname, dict):
                    rname = rname.get("value", "")
                rname = (rname or "").lower()
                hcp = r.get("handicap")
                if hcp is not None:
                    if home and home.lower()[:8] in rname:
                        spread_home = float(hcp)
                    elif away and away.lower()[:8] in rname:
                        spread_away = float(hcp)
                    elif spread_away is None:
                        spread_away = float(hcp)
                    else:
                        spread_home = float(hcp)

        elif "total" in gname:
            for r in results:
                rname = r.get("name", {})
                if isinstance(rname, dict):
                    rname = rname.get("value", "")
                if "over" in (rname or "").lower():
                    hcp = r.get("handicap")
                    if hcp is not None:
                        total = float(hcp)
                        break

        elif "moneyline" in gname or "money line" in gname:
            for r in results:
                rname = r.get("name", {})
                if isinstance(rname, dict):
                    rname = rname.get("value", "")
                rname = (rname or "").lower()
                price = r.get("americanOdds")
                if price is not None:
                    try:
                        val = int(price)
                    except (ValueError, TypeError):
                        continue
                    if home and home.lower()[:8] in rname:
                        ml_home = val
                    elif away and away.lower()[:8] in rname:
                        ml_away = val
                    elif ml_away is None:
                        ml_away = val
                    else:
                        ml_home = val

    return GameLine(
        home_team=home,
        away_team=away,
        start_time=start,
        spread_home=spread_home,
        spread_away=spread_away,
        total=total,
        moneyline_home=ml_home,
        moneyline_away=ml_away,
        source="betmgm",
    )


# ─── Unified scraper ──────────────────────────────────────────────────────

async def scrape_all_playwright(sport: str = "ncaab", headless: bool = True) -> dict[str, list[GameLine]]:
    """Run all Playwright scrapers concurrently."""
    # Run sequentially to avoid browser conflicts
    results = {}

    for name, fn in [("draftkings", scrape_draftkings), ("caesars", scrape_caesars), ("betmgm", scrape_betmgm)]:
        try:
            games = await fn(sport=sport, headless=headless)
            results[name] = games
            logger.info(f"{name}: {len(games)} games")
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            results[name] = []

    return results


# ─── CLI test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    sport = sys.argv[1] if len(sys.argv) > 1 else "ncaab"
    book = sys.argv[2] if len(sys.argv) > 2 else "all"

    async def main():
        if book == "all":
            results = await scrape_all_playwright(sport=sport)
            for source, games in results.items():
                print(f"\n{'='*60}")
                print(f"{source}: {len(games)} games")
                for g in games[:3]:
                    print(f"  {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} ML={g.moneyline_home}/{g.moneyline_away}")
        elif book == "dk":
            games = await scrape_draftkings(sport=sport)
            print(f"DraftKings: {len(games)} games")
            for g in games[:5]:
                print(f"  {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} ML={g.moneyline_home}/{g.moneyline_away}")
        elif book == "caesars":
            games = await scrape_caesars(sport=sport)
            print(f"Caesars: {len(games)} games")
            for g in games[:5]:
                print(f"  {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} ML={g.moneyline_home}/{g.moneyline_away}")
        elif book == "betmgm":
            games = await scrape_betmgm(sport=sport)
            print(f"BetMGM: {len(games)} games")
            for g in games[:5]:
                print(f"  {g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} ML={g.moneyline_home}/{g.moneyline_away}")

    asyncio.run(main())
