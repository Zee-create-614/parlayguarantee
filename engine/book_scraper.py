"""
book_scraper.py — Unified sportsbook scraper for ParlayGuarantee NCAAB.
FanDuel + ESPN scrapers returning standardized GameLine objects.
"""

import asyncio
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("book_scraper")


@dataclass
class GameLine:
    home_team: str
    away_team: str
    start_time: Optional[str]  # ISO 8601
    spread_home: Optional[float] = None
    spread_away: Optional[float] = None
    total: Optional[float] = None
    over_odds: Optional[int] = None
    under_odds: Optional[int] = None
    moneyline_home: Optional[int] = None
    moneyline_away: Optional[int] = None
    source: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # ESPN extras
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: Optional[str] = None  # pre, in, post

    def to_dict(self) -> dict:
        return asdict(self)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# FanDuel
# ---------------------------------------------------------------------------
class FanDuelScraper:
    STATES = ["mi", "nj", "pa", "co", "va"]
    MAX_RETRIES = 3

    def _url(self, state: str) -> str:
        return f"https://sbapi.{state}.sportsbook.fanduel.com/api/content-managed-page"

    async def scrape(self) -> list[GameLine]:
        for state in self.STATES:
            url = self._url(state)
            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    games = await self._fetch(url, state)
                    if games:
                        logger.info(f"FanDuel ({state}): {len(games)} games on attempt {attempt}")
                        return games
                    logger.warning(f"FanDuel ({state}): 0 games on attempt {attempt}")
                except Exception as e:
                    logger.warning(f"FanDuel ({state}) attempt {attempt} failed: {e}")
                    if attempt < self.MAX_RETRIES:
                        await asyncio.sleep(2 ** attempt)
        logger.error("FanDuel: ALL endpoints failed")
        return []

    async def _fetch(self, base_url: str, state: str) -> list[GameLine]:
        params = {
            "page": "CUSTOM",
            "customPageId": "ncaab",
            "pbHorizontal": "false",
            "_ak": "FhMFpcPWXMeyZxOx",
            "timezone": "America/New_York",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(base_url, headers=HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
        return self._parse(data)

    def _parse(self, data: dict) -> list[GameLine]:
        games = []
        attachments = data.get("attachments", {})
        events = attachments.get("events", {})
        markets = attachments.get("markets", {})
        now = datetime.now(timezone.utc).isoformat()

        # Index markets by event
        event_mkts: dict[str, dict] = {}
        for mid, mkt in markets.items():
            eid = str(mkt.get("eventId", ""))
            if not eid:
                continue
            if eid not in event_mkts:
                event_mkts[eid] = {}
            mtype = (mkt.get("marketType") or "").upper()
            runners = mkt.get("runners", [])

            if "SPREAD" in mtype or "HANDICAP" in mtype:
                for r in runners:
                    handicap = r.get("handicap")
                    if handicap is None:
                        continue
                    rtype = (r.get("result", {}).get("type") or r.get("type", "")).upper()
                    if rtype == "HOME":
                        event_mkts[eid]["spread_home"] = float(handicap)
                    elif rtype == "AWAY":
                        event_mkts[eid]["spread_away"] = float(handicap)

            elif "TOTAL" in mtype or "OVER_UNDER" in mtype:
                for r in runners:
                    handicap = r.get("handicap")
                    rtype = (r.get("result", {}).get("type") or r.get("type", "")).upper()
                    if handicap is not None:
                        event_mkts[eid]["total"] = float(handicap)
                    odds = r.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                    if odds is None:
                        dec = r.get("winRunnerOdds", {}).get("trueOdds", {}).get("decimalOdds", {}).get("decimalOdds")
                        if dec:
                            odds = self._dec_to_am(float(dec))
                    if odds is not None:
                        if rtype == "OVER" or "over" in (r.get("result", {}).get("name") or "").lower():
                            event_mkts[eid]["over_odds"] = int(odds)
                        elif rtype == "UNDER" or "under" in (r.get("result", {}).get("name") or "").lower():
                            event_mkts[eid]["under_odds"] = int(odds)

            elif "MONEYLINE" in mtype or "MATCH_ODDS" in mtype or "MONEY" in mtype:
                for r in runners:
                    odds = r.get("winRunnerOdds", {}).get("americanDisplayOdds", {}).get("americanOdds")
                    if odds is None:
                        dec = r.get("winRunnerOdds", {}).get("trueOdds", {}).get("decimalOdds", {}).get("decimalOdds")
                        if dec:
                            odds = self._dec_to_am(float(dec))
                    if odds is not None:
                        rtype = (r.get("result", {}).get("type") or r.get("type", "")).upper()
                        if rtype == "HOME":
                            event_mkts[eid]["ml_home"] = int(odds)
                        elif rtype == "AWAY":
                            event_mkts[eid]["ml_away"] = int(odds)

        for eid, ev in events.items():
            home = ev.get("homeTeamName") or ""
            away = ev.get("awayTeamName") or ""
            if not home or not away:
                name = ev.get("name", "")
                parsed = self._parse_name(name)
                if parsed:
                    away, home = parsed
                else:
                    continue

            odds = event_mkts.get(eid, {})
            games.append(GameLine(
                home_team=home,
                away_team=away,
                start_time=ev.get("openDate", ""),
                spread_home=odds.get("spread_home"),
                spread_away=odds.get("spread_away"),
                total=odds.get("total"),
                over_odds=odds.get("over_odds"),
                under_odds=odds.get("under_odds"),
                moneyline_home=odds.get("ml_home"),
                moneyline_away=odds.get("ml_away"),
                source="fanduel",
                scraped_at=now,
            ))
        return games

    def _parse_name(self, name: str) -> Optional[tuple[str, str]]:
        for sep in [" @ ", " at ", " vs ", " v "]:
            if sep in name.lower():
                idx = name.lower().index(sep)
                return (name[:idx].strip(), name[idx + len(sep):].strip())
        return None

    @staticmethod
    def _dec_to_am(dec: float) -> int:
        if dec >= 2.0:
            return int(round((dec - 1) * 100))
        return int(round(-100 / (dec - 1)))


# ---------------------------------------------------------------------------
# ESPN
# ---------------------------------------------------------------------------
class ESPNScraper:
    BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"

    async def scrape(self, date: Optional[str] = None) -> list[GameLine]:
        """Scrape ESPN scoreboard. date = YYYYMMDD or None for today."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
        params = {"dates": date, "limit": "400", "groups": "50"}
        now = datetime.now(timezone.utc).isoformat()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(self.BASE, headers=HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"ESPN scrape failed: {e}")
            return []

        games = []
        for ev in data.get("events", []):
            try:
                comp = ev["competitions"][0]
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue

                home = away = None
                home_score = away_score = None
                for c in competitors:
                    team_name = c.get("team", {}).get("displayName") or c.get("team", {}).get("shortDisplayName") or ""
                    score = c.get("score")
                    if c.get("homeAway") == "home":
                        home = team_name
                        home_score = int(score) if score else None
                    else:
                        away = team_name
                        away_score = int(score) if score else None

                if not home or not away:
                    continue

                start = ev.get("date", "")
                status_type = comp.get("status", {}).get("type", {}).get("state", "pre")

                # Extract ESPN BET odds
                spread_home = spread_away = total = ml_home = ml_away = None
                over_odds = under_odds = None
                for odd in comp.get("odds", []):
                    if spread_home is None and odd.get("spread") is not None:
                        try:
                            spread_home = float(odd["spread"])
                            spread_away = -spread_home
                        except (ValueError, TypeError):
                            pass
                    if total is None and odd.get("overUnder") is not None:
                        try:
                            total = float(odd["overUnder"])
                        except (ValueError, TypeError):
                            pass
                    # Moneylines from homeTeamOdds/awayTeamOdds
                    hto = odd.get("homeTeamOdds", {})
                    ato = odd.get("awayTeamOdds", {})
                    if ml_home is None and hto.get("moneyLine") is not None:
                        try:
                            ml_home = int(hto["moneyLine"])
                        except (ValueError, TypeError):
                            pass
                    if ml_away is None and ato.get("moneyLine") is not None:
                        try:
                            ml_away = int(ato["moneyLine"])
                        except (ValueError, TypeError):
                            pass

                games.append(GameLine(
                    home_team=home,
                    away_team=away,
                    start_time=start,
                    spread_home=spread_home,
                    spread_away=spread_away,
                    total=total,
                    over_odds=over_odds,
                    under_odds=under_odds,
                    moneyline_home=ml_home,
                    moneyline_away=ml_away,
                    source="espn",
                    scraped_at=now,
                    home_score=home_score,
                    away_score=away_score,
                    status=status_type,
                ))
            except Exception as e:
                logger.warning(f"ESPN: failed to parse event: {e}")
                continue

        logger.info(f"ESPN: {len(games)} games")
        return games


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
async def scrape_all(date: Optional[str] = None) -> dict[str, list[GameLine]]:
    fd = FanDuelScraper()
    espn = ESPNScraper()
    fd_games, espn_games = await asyncio.gather(
        fd.scrape(),
        espn.scrape(date),
        return_exceptions=False,
    )
    return {"fanduel": fd_games or [], "espn": espn_games or []}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(scrape_all())
    for src, games in results.items():
        print(f"\n{src}: {len(games)} games")
        for g in games[:5]:
            print(f"  {g.away_team} @ {g.home_team} | sprd={g.spread_home} tot={g.total} ML={g.moneyline_home}/{g.moneyline_away}")
