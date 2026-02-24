"""
Consensus Engine — Cross-references multiple sportsbook sources for NCAAB lines.
Fuzzy team matching, confidence scoring, discrepancy flagging.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Optional

from team_name_mapper import normalize_team, are_same_team
from sportsbook_scraper import GameLine

logger = logging.getLogger("consensus_engine")


@dataclass
class ConsensusGame:
    home_team: str  # canonical name
    away_team: str  # canonical name
    start_time: Optional[str]
    spread_home: Optional[float]
    spread_away: Optional[float]
    total: Optional[float]
    moneyline_home: Optional[int]
    moneyline_away: Optional[int]
    confidence: float  # 0.0 to 1.0
    sources: list[str]
    flags: list[str]  # discrepancy flags
    source_lines: dict  # raw lines from each source

    def to_dict(self) -> dict:
        return asdict(self)


def _match_games(games_a: list[GameLine], games_b: list[GameLine]) -> list[tuple[GameLine, GameLine]]:
    """Match games between two sources by normalized team names."""
    matched = []
    used_b = set()

    for ga in games_a:
        ha = normalize_team(ga.home_team)
        aa = normalize_team(ga.away_team)
        for i, gb in enumerate(games_b):
            if i in used_b:
                continue
            hb = normalize_team(gb.home_team)
            ab = normalize_team(gb.away_team)
            if ha == hb and aa == ab:
                matched.append((ga, gb))
                used_b.add(i)
                break
            # Try swapped (some sources flip home/away)
            if ha == ab and aa == hb:
                matched.append((ga, gb))
                used_b.add(i)
                break

    return matched


def build_consensus(all_games: dict[str, list[GameLine]],
                    spread_tolerance: float = 1.0,
                    flag_threshold: float = 2.0,
                    sport: str = "ncaab") -> list[ConsensusGame]:
    """
    Build consensus from multiple sources.

    Args:
        all_games: {source_name: [GameLine, ...]}
        spread_tolerance: max diff for 2 sources to agree
        flag_threshold: diff above this triggers a flag

    Returns:
        List of ConsensusGame with confidence scores and flags.
    """
    # Collect all unique games across sources
    game_index: dict[tuple[str, str], dict] = {}  # (home_canonical, away_canonical) → {source: GameLine}

    # For NBA/NHL, team names are already standard — use light normalization only
    def _norm(name):
        if sport in ("nba", "nhl"):
            return name.strip()
        return normalize_team(name)

    for source, games in all_games.items():
        for g in games:
            home = _norm(g.home_team)
            away = _norm(g.away_team)
            key = (home, away)
            alt_key = (away, home)

            if alt_key in game_index and key not in game_index:
                key = alt_key  # use existing key even if home/away flipped

            if key not in game_index:
                game_index[key] = {}
            game_index[key][source] = g

    # Build consensus for each game
    consensus = []
    for (home, away), source_data in game_index.items():
        sources = list(source_data.keys())
        flags = []
        source_lines_raw = {}

        # Collect all values
        spreads = {}
        totals = {}
        mls_home = {}
        mls_away = {}
        start_time = None

        for src, gl in source_data.items():
            source_lines_raw[src] = gl.to_dict()
            if gl.start_time and not start_time:
                start_time = gl.start_time
            if gl.spread_home is not None:
                spreads[src] = gl.spread_home
            if gl.total is not None:
                totals[src] = gl.total
            if gl.moneyline_home is not None:
                mls_home[src] = gl.moneyline_home
            if gl.moneyline_away is not None:
                mls_away[src] = gl.moneyline_away

        # Consensus spread
        spread_val = _consensus_value(spreads, spread_tolerance, flag_threshold, "spread", flags)
        spread_away_val = -spread_val if spread_val is not None else None

        # Consensus total
        total_val = _consensus_value(totals, spread_tolerance, flag_threshold, "total", flags)

        # Consensus moneylines (use wider tolerance)
        ml_home_val = _consensus_value(mls_home, 20, 50, "ml_home", flags)
        ml_away_val = _consensus_value(mls_away, 20, 50, "ml_away", flags)

        # Confidence score
        confidence = _calc_confidence(len(sources), len(flags), spreads, totals)

        consensus.append(ConsensusGame(
            home_team=home,
            away_team=away,
            start_time=start_time,
            spread_home=spread_val,
            spread_away=spread_away_val,
            total=total_val,
            moneyline_home=int(ml_home_val) if ml_home_val is not None else None,
            moneyline_away=int(ml_away_val) if ml_away_val is not None else None,
            confidence=confidence,
            sources=sources,
            flags=flags,
            source_lines=source_lines_raw,
        ))

    # Filter to games with 2+ sources (true consensus only)
    multi_source = [g for g in consensus if len(g.sources) >= 2]
    single_source = len(consensus) - len(multi_source)
    if single_source:
        logger.info(f"Dropped {single_source} single-source games (no consensus)")

    # Sort by confidence descending
    multi_source.sort(key=lambda g: g.confidence, reverse=True)
    return multi_source


def _consensus_value(values: dict[str, float], tolerance: float, flag_thresh: float,
                     label: str, flags: list[str]) -> Optional[float]:
    """Pick consensus value from multiple sources."""
    if not values:
        return None
    if len(values) == 1:
        return list(values.values())[0]

    vals = list(values.values())
    srcs = list(values.keys())

    # Check pairwise agreement
    min_val, max_val = min(vals), max(vals)
    spread_diff = abs(max_val - min_val)

    if spread_diff > flag_thresh:
        flags.append(f"{label}_DISAGREE: {dict(zip(srcs, vals))} diff={spread_diff:.1f}")

    if spread_diff <= tolerance:
        # All agree — use mean
        return round(sum(vals) / len(vals), 1)

    # Find 2 that agree
    if len(vals) >= 3:
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                if abs(vals[i] - vals[j]) <= tolerance:
                    return round((vals[i] + vals[j]) / 2, 1)

    # No agreement — use median
    vals.sort()
    return vals[len(vals) // 2]


def _calc_confidence(num_sources: int, num_flags: int,
                     spreads: dict, totals: dict) -> float:
    """Calculate confidence score 0-1."""
    score = 0.0

    # More sources = higher confidence
    if num_sources >= 3:
        score += 0.5
    elif num_sources == 2:
        score += 0.35
    else:
        score += 0.15

    # Has spread data
    if spreads:
        score += 0.2

    # Has total data
    if totals:
        score += 0.1

    # Penalty for flags
    score -= num_flags * 0.15

    return max(0.0, min(1.0, round(score, 2)))


if __name__ == "__main__":
    # Quick test with mock data
    games = {
        "draftkings": [
            GameLine("Duke", "UNC", "2025-02-21T19:00:00Z", -3.5, 3.5, 145.5, -160, 140, "draftkings"),
        ],
        "fanduel": [
            GameLine("Duke Blue Devils", "North Carolina", "2025-02-21T19:00:00Z", -3.0, 3.0, 146.0, -155, 135, "fanduel"),
        ],
        "odds_api": [
            GameLine("Duke Blue Devils", "North Carolina Tar Heels", "2025-02-21T19:00:00Z", -3.5, 3.5, 145.5, -158, 138, "odds_api"),
        ],
    }
    result = build_consensus(games)
    for g in result:
        print(f"{g.away_team} @ {g.home_team} | spread={g.spread_home} total={g.total} conf={g.confidence} flags={g.flags}")
