"""
consensus.py — Cross-reference engine for ParlayGuarantee NCAAB.
Matches games across FanDuel + ESPN, scores confidence, flags discrepancies.
NEVER drops a game silently.
"""

import logging
from dataclasses import dataclass, asdict, field
from typing import Optional

from team_name_mapper import normalize_team
from book_scraper import GameLine

logger = logging.getLogger("consensus")


@dataclass
class ConsensusGame:
    home_team: str          # canonical
    away_team: str          # canonical
    start_time: Optional[str]
    spread_home: Optional[float] = None
    spread_away: Optional[float] = None
    total: Optional[float] = None
    over_odds: Optional[int] = None
    under_odds: Optional[int] = None
    moneyline_home: Optional[int] = None
    moneyline_away: Optional[int] = None
    confidence: str = "NO_DATA"  # HIGH, MEDIUM, ESPN_ONLY, NO_DATA
    sources: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    source_lines: dict = field(default_factory=dict)
    # ESPN live data
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    status: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def build_consensus(
    all_games: dict[str, list[GameLine]],
    spread_agree: float = 1.5,
    spread_flag: float = 2.0,
    total_agree: float = 1.5,
    total_flag: float = 2.0,
) -> list[ConsensusGame]:
    """
    Build consensus from FanDuel + ESPN game lists.
    Every game from every source appears in output.
    """
    # Normalize and index all games by (home_canonical, away_canonical)
    # Key: (home, away) → {source: GameLine}
    index: dict[tuple[str, str], dict[str, GameLine]] = {}

    for source, games in all_games.items():
        for g in games:
            h = normalize_team(g.home_team)
            a = normalize_team(g.away_team)
            key = (h, a)
            alt = (a, h)
            # Check if alt key exists (home/away swapped)
            if alt in index and key not in index:
                key = alt
            if key not in index:
                index[key] = {}
            # Don't overwrite if same source already there
            if source not in index[key]:
                index[key][source] = g

    results = []
    for (home, away), src_data in index.items():
        sources = list(src_data.keys())
        flags = []

        # Prefer FanDuel data as primary (sharper book)
        fd = src_data.get("fanduel")
        espn = src_data.get("espn")

        # Determine confidence
        if fd and espn:
            confidence = "HIGH"
        elif fd:
            confidence = "MEDIUM"
        elif espn:
            confidence = "ESPN_ONLY"
        else:
            confidence = "NO_DATA"

        # Spread
        spread_home = None
        if fd and fd.spread_home is not None and espn and espn.spread_home is not None:
            diff = abs(fd.spread_home - espn.spread_home)
            if diff > spread_flag:
                flags.append(f"SPREAD_DIFF={diff:.1f} (FD={fd.spread_home} ESPN={espn.spread_home})")
            # Use FanDuel (sharper)
            spread_home = fd.spread_home
        elif fd and fd.spread_home is not None:
            spread_home = fd.spread_home
        elif espn and espn.spread_home is not None:
            spread_home = espn.spread_home

        spread_away = -spread_home if spread_home is not None else None

        # Total
        total = None
        if fd and fd.total is not None and espn and espn.total is not None:
            diff = abs(fd.total - espn.total)
            if diff > total_flag:
                flags.append(f"TOTAL_DIFF={diff:.1f} (FD={fd.total} ESPN={espn.total})")
            total = fd.total
        elif fd and fd.total is not None:
            total = fd.total
        elif espn and espn.total is not None:
            total = espn.total

        # Moneylines — prefer FanDuel
        ml_home = (fd.moneyline_home if fd and fd.moneyline_home is not None
                   else (espn.moneyline_home if espn else None))
        ml_away = (fd.moneyline_away if fd and fd.moneyline_away is not None
                   else (espn.moneyline_away if espn else None))

        # Over/under odds — FanDuel only typically
        over_odds = fd.over_odds if fd else None
        under_odds = fd.under_odds if fd else None

        # Start time — prefer FanDuel, fall back to ESPN
        start_time = (fd.start_time if fd and fd.start_time else
                      (espn.start_time if espn else None))

        # ESPN live data
        home_score = espn.home_score if espn else None
        away_score = espn.away_score if espn else None
        status = espn.status if espn else None

        source_lines = {s: g.to_dict() for s, g in src_data.items()}

        results.append(ConsensusGame(
            home_team=home,
            away_team=away,
            start_time=start_time,
            spread_home=spread_home,
            spread_away=spread_away,
            total=total,
            over_odds=over_odds,
            under_odds=under_odds,
            moneyline_home=ml_home,
            moneyline_away=ml_away,
            confidence=confidence,
            sources=sources,
            flags=flags,
            source_lines=source_lines,
            home_score=home_score,
            away_score=away_score,
            status=status,
        ))

    # Sort: HIGH first, then MEDIUM, then ESPN_ONLY
    order = {"HIGH": 0, "MEDIUM": 1, "ESPN_ONLY": 2, "NO_DATA": 3}
    results.sort(key=lambda g: (order.get(g.confidence, 9), g.home_team))
    return results
