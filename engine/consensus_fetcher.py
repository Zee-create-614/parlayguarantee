"""
Consensus Fetcher — Drop-in replacement for Odds API game fetching.
Uses unified_scraper (FanDuel API + DraftKings Playwright + Odds API) 
to build consensus lines, then returns games in the format engines expect.
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("consensus_fetcher")

ENGINE_DIR = Path(__file__).parent


def _american_to_prob(odds: Optional[int]) -> float:
    if odds is None:
        return 0.5
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)


def fetch_consensus_games(target_date: Optional[date] = None,
                          sport: str = "ncaab",
                          use_playwright: bool = True,
                          use_cache: bool = True) -> List[Dict]:
    """
    Fetch games with consensus lines from multiple sportsbooks.
    Returns games in the same format as ncaab_data_fetcher.fetch_games_from_odds().
    
    Args:
        target_date: Filter to this date (None = today)
        sport: ncaab, nba, nhl
        use_playwright: Whether to use Playwright scrapers (DK)
        use_cache: Use cached consensus if < 30 min old
    """
    target = target_date or date.today()
    target_str = target.isoformat()
    
    # Check cache
    cache_path = ENGINE_DIR / f"consensus_{sport}_{target_str}.json"
    if use_cache and cache_path.exists():
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            # Check age
            gen_time = cached.get("generated_at", "")
            if gen_time:
                gen_dt = datetime.fromisoformat(gen_time.replace("Z", "+00:00"))
                age_min = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 60
                if age_min < 30:
                    logger.info(f"Using cached consensus ({age_min:.0f}m old, {len(cached.get('games', []))} games)")
                    return _consensus_to_game_dicts(cached.get("games", []), target_str, sport)
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

    # Run the unified scraper
    logger.info(f"Scraping all sources for {sport} consensus...")
    
    try:
        from unified_scraper import scrape_all_sources
        from consensus_engine import build_consensus
        
        # Handle both sync and async contexts
        try:
            loop = asyncio.get_running_loop()
            # Already in an event loop — use nest_asyncio or run directly
            import nest_asyncio
            nest_asyncio.apply()
            all_games = asyncio.run(scrape_all_sources(sport=sport, use_playwright=use_playwright))
        except RuntimeError:
            # No running event loop — safe to use asyncio.run()
            all_games = asyncio.run(scrape_all_sources(sport=sport, use_playwright=use_playwright))
        
        # Filter out empty sources
        active = {k: v for k, v in all_games.items() if v}
        if not active:
            logger.error("All sources returned 0 games!")
            return []
        
        logger.info(f"Sources: {', '.join(f'{k}={len(v)}' for k, v in active.items())}")
        
        # Build consensus
        consensus = build_consensus(active, sport=sport)
        
        # Save cache
        cache_data = {
            "sport": sport,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": {k: len(v) for k, v in active.items()},
            "games": [g.to_dict() for g in consensus],
        }
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        logger.info(f"Cached {len(consensus)} consensus games to {cache_path.name}")
        
        return _consensus_to_game_dicts([g.to_dict() for g in consensus], target_str, sport)
        
    except Exception as e:
        logger.error(f"Consensus scrape failed: {e}")
        # Fallback: try just Odds API
        logger.info("Falling back to Odds API only...")
        try:
            from sportsbook_scraper import OddsAPIScraper
            oa = OddsAPIScraper()
            sport_map = {"ncaab": "basketball_ncaab", "nba": "basketball_nba", "nhl": "icehockey_nhl"}
            oa.BASE_URL = f"https://api.the-odds-api.com/v4/sports/{sport_map.get(sport, sport)}/odds"
            games = asyncio.run(oa.scrape())
            if games:
                logger.info(f"Odds API fallback: {len(games)} games")
                return _gamelines_to_game_dicts(games, target_str, sport)
        except Exception as e2:
            logger.error(f"Odds API fallback also failed: {e2}")
        return []


def _consensus_to_game_dicts(consensus_dicts: List[Dict], target_str: str, sport: str) -> List[Dict]:
    """Convert consensus game dicts to the format engines expect."""
    games = []
    
    for g in consensus_dicts:
        start = g.get("start_time", "")
        
        # Filter to target date (allow games from 4am to next day 4am ET)
        if start and target_str:
            try:
                if "T" in start:
                    game_dt = datetime.fromisoformat(start.replace("Z", "+00:00").replace(".0000000Z", "+00:00"))
                    # Convert to ET for date filtering
                    et_offset = timedelta(hours=-5)
                    game_et = game_dt + et_offset
                    game_date_str = game_et.date().isoformat()
                    if game_date_str != target_str:
                        # Check if it's early morning next day (games that start late)
                        prev_day = (game_et.date() - timedelta(days=1)).isoformat()
                        if prev_day != target_str or game_et.hour > 4:
                            continue
            except Exception:
                pass  # Keep game if we can't parse date
        
        home = g.get("home_team", "")
        away = g.get("away_team", "")
        
        home_ml = g.get("moneyline_home")
        away_ml = g.get("moneyline_away")
        spread = g.get("spread_home")
        total = g.get("total")
        
        home_prob = _american_to_prob(home_ml)
        away_prob = _american_to_prob(away_ml)
        
        # Determine available books from sources
        sources = g.get("sources", [])
        book_map = {
            "draftkings": "DraftKings",
            "fanduel": "FanDuel", 
            "odds_api": "Odds API",
            "caesars": "Caesars",
            "betmgm": "BetMGM",
        }
        available_books = [book_map.get(s, s) for s in sources]
        
        games.append({
            "game_id": f"{sport}_{away}_{home}_{target_str}".replace(" ", "_"),
            "game_date": target_str,
            "game_time": start,
            "home_team": home,
            "away_team": away,
            "home_odds": home_ml,
            "away_odds": away_ml,
            "home_implied_prob": home_prob,
            "away_implied_prob": away_prob,
            "spread": spread,
            "total": total,
            "game_status": "Scheduled",
            "available_books": available_books,
            "consensus_confidence": g.get("confidence", 0),
            "consensus_flags": g.get("flags", []),
            "source_lines": g.get("source_lines", {}),
        })
    
    logger.info(f"Returning {len(games)} {sport.upper()} games for {target_str}")
    return games


def _gamelines_to_game_dicts(gamelines, target_str: str, sport: str) -> List[Dict]:
    """Convert raw GameLine objects to engine-expected format."""
    games = []
    for gl in gamelines:
        home_prob = _american_to_prob(gl.moneyline_home)
        away_prob = _american_to_prob(gl.moneyline_away)
        games.append({
            "game_id": f"{sport}_{gl.away_team}_{gl.home_team}_{target_str}".replace(" ", "_"),
            "game_date": target_str,
            "game_time": gl.start_time or "",
            "home_team": gl.home_team,
            "away_team": gl.away_team,
            "home_odds": gl.moneyline_home,
            "away_odds": gl.moneyline_away,
            "home_implied_prob": home_prob,
            "away_implied_prob": away_prob,
            "spread": gl.spread_home,
            "total": gl.total,
            "game_status": "Scheduled",
            "available_books": [gl.source],
        })
    return games


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    
    import sys
    sport = sys.argv[1] if len(sys.argv) > 1 else "ncaab"
    
    games = fetch_consensus_games(sport=sport)
    print(f"\n{len(games)} games:")
    for g in games[:10]:
        books = "/".join(g.get("available_books", []))
        print(f"  {g['away_team']} @ {g['home_team']} | spread={g['spread']} total={g['total']} ML={g['home_odds']}/{g['away_odds']} [{books}]")
