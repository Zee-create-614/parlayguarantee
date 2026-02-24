#!/usr/bin/env python3
"""
AUTOPILOT.py — ParlayGuarantee Fully Autonomous Pick Engine
============================================================
ONE script. ZERO human intervention. Run from cron and walk away.

Pipeline:
  1. Fetch odds from Odds API (NBA + NCAAB) 
  2. Fetch injury data
  3. Run full analysis (consensus spreads, upset composite, enhanced probs)
  4. Generate structured picks + parlays (all tiers)
  5. Score yesterday's results
  6. Save everything to dated output + website JSON
  7. Deploy to Vercel
  8. Report summary

Usage:
  python autopilot.py                    # Full run
  python autopilot.py --picks-only       # Skip scoring + deploy
  python autopilot.py --score-only       # Score yesterday only
  python autopilot.py --no-deploy        # Skip Vercel deploy
"""

import json, logging, math, os, requests, subprocess, sys, time, traceback
from datetime import datetime, date, timedelta, timezone
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# ─── Setup ────────────────────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ENGINE_DIR = Path(__file__).parent
EST = timezone(timedelta(hours=-5))
NOW_EST = datetime.now(EST)
TODAY = NOW_EST.strftime('%Y-%m-%d')
YESTERDAY = (NOW_EST - timedelta(days=1)).strftime('%Y-%m-%d')

ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Output paths
PICKS_DIR = ENGINE_DIR / f"picks_{TODAY}"
PICKS_DIR.mkdir(exist_ok=True)

LOG_FILE = PICKS_DIR / "autopilot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("autopilot")

# Import calibrated totals engine v3 (blends 55% market + 45% model, min 1.5pt edge)
try:
    from totals_engine_v3 import TotalsEngineV3
    TOTALS_V3_AVAILABLE = True
    _totals_engines = {}  # Cache per sport
    log.info("✅ Totals engine v3 loaded (market-blended)")
except ImportError as e:
    TOTALS_V3_AVAILABLE = False
    log.warning(f"⚠️ Totals engine v3 not available: {e}")

# NBA Upset Composite v2 (smart, NCAAB-style)
try:
    from nba_upset_composite import enhance_games_with_upset_composite as nba_upset_v2
    NBA_UPSET_V2 = True
    log.info("✅ NBA Upset Composite v2 loaded (smart model)")
except ImportError as e:
    NBA_UPSET_V2 = False
    log.warning(f"⚠️ NBA Upset Composite v2 not available: {e}")

# Legacy import kept for reference but NOT used
TOTALS_MODEL_AVAILABLE = False

# ─── Config ───────────────────────────────────────────────────────────
SPORTS = {
    "basketball_nba": "NBA",
    "basketball_ncaab": "NCAAB",
}

TIER_CONFIG = {
    'single': {'legs': 1, 'count': 10},
    '2leg':   {'legs': 2, 'count': 8},
    '3leg':   {'legs': 3, 'count': 5},
    '4leg':   {'legs': 4, 'count': 3},
    '5leg':   {'legs': 5, 'count': 2},
    '6leg':   {'legs': 6, 'count': 2},
    '7leg':   {'legs': 7, 'count': 1},
}

# Star players whose absence significantly impacts games
STAR_PLAYERS = {
    # NBA
    'LeBron James', 'Stephen Curry', 'Kevin Durant', 'Giannis Antetokounmpo',
    'Jayson Tatum', 'Luka Doncic', 'Nikola Jokic', 'Joel Embiid', 'Shai Gilgeous-Alexander',
    'Anthony Davis', 'Donovan Mitchell', 'Ja Morant', 'Anthony Edwards',
    'Damian Lillard', 'Jimmy Butler', 'Trae Young', 'Devin Booker',
    'Tyrese Haliburton', 'De\'Aaron Fox', 'Paolo Banchero', 'Victor Wembanyama',
    'Karl-Anthony Towns', 'Jaylen Brown', 'Domantas Sabonis', 'Bam Adebayo',
    'Jalen Brunson', 'Kawhi Leonard', 'Paul George', 'Kyrie Irving',
    'Zion Williamson', 'Chet Holmgren', 'Lauri Markkanen', 'Franz Wagner',
}


# ═══════════════════════════════════════════════════════════════════════
# STEP 1: FETCH ODDS
# ═══════════════════════════════════════════════════════════════════════
def fetch_odds(sport_key: str, markets: str = "h2h,spreads,totals") -> list:
    """Fetch odds from The Odds API with retry."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'us',
        'markets': markets,
        'oddsFormat': 'american',
        'dateFormat': 'iso',
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            remaining = r.headers.get('x-requests-remaining', '?')
            data = r.json()
            log.info(f"[{sport_key}] {len(data)} events, API calls remaining: {remaining}")
            return data
        except Exception as e:
            log.warning(f"[{sport_key}] Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    log.error(f"[{sport_key}] ALL attempts failed")
    return []


def fetch_scores(sport_key: str, days_from: int = 2) -> list:
    """Fetch completed game scores from Odds API."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/scores/"
    params = {'apiKey': ODDS_API_KEY, 'daysFrom': days_from, 'dateFormat': 'iso'}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Score fetch failed for {sport_key}: {e}")
        return []


def fetch_espn_scores(target_date: str, sport: str = 'nba') -> dict:
    """Fetch scores from ESPN (more reliable for NCAAB)."""
    league = 'nba' if sport == 'nba' else 'mens-college-basketball'
    dt_str = target_date.replace('-', '')
    extra = '&groups=50&limit=500' if sport != 'nba' else ''
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard?dates={dt_str}{extra}"
    scores = {}
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        for event in r.json().get('events', []):
            status = event.get('status', {}).get('type', {}).get('name', '')
            if status != 'STATUS_FINAL':
                continue
            comps = event.get('competitions', [{}])[0]
            home_data = away_data = None
            for c in comps.get('competitors', []):
                entry = {'name': c['team'].get('displayName', ''), 'score': int(c.get('score', 0))}
                if c.get('homeAway') == 'home':
                    home_data = entry
                else:
                    away_data = entry
            if home_data and away_data:
                key = f"{away_data['name']} @ {home_data['name']}"
                result = {
                    'home': home_data['name'], 'away': away_data['name'],
                    'home_score': home_data['score'], 'away_score': away_data['score'],
                    'total': home_data['score'] + away_data['score'],
                    'winner': home_data['name'] if home_data['score'] > away_data['score'] else away_data['name'],
                    'margin': home_data['score'] - away_data['score'],
                }
                scores[home_data['name']] = result
                scores[away_data['name']] = result
    except Exception as e:
        log.warning(f"ESPN scores error ({sport}): {e}")
    return scores


# ═══════════════════════════════════════════════════════════════════════
# STEP 2: INJURIES
# ═══════════════════════════════════════════════════════════════════════
def fetch_injuries() -> dict:
    """Scrape injury data from CBS Sports."""
    injuries = {}
    for sport_url, team_map_fn in [
        ("https://www.cbssports.com/nba/injuries/", None),
        ("https://www.cbssports.com/college-basketball/injuries/", None),
    ]:
        try:
            r = requests.get(sport_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if r.status_code != 200:
                continue
            # Simple parsing — extract player + status from HTML
            import re
            # Find team sections
            team_blocks = re.split(r'<span class="TeamName"[^>]*>([^<]+)</span>', r.text)
            current_team = None
            for i, block in enumerate(team_blocks):
                if i % 2 == 1:  # Team name
                    current_team = block.strip()
                    if current_team not in injuries:
                        injuries[current_team] = []
                elif current_team:
                    # Find players and statuses
                    players = re.findall(
                        r'<span class="CellPlayerName--long"[^>]*><a[^>]*>([^<]+)</a>.*?<td[^>]*>([^<]+)</td>',
                        block, re.DOTALL
                    )
                    for player, status in players:
                        status = status.strip()
                        if status in ('Out', 'Doubtful', 'Questionable', 'Day-To-Day'):
                            injuries[current_team].append({
                                'player': player.strip(),
                                'status': status,
                                'star': player.strip() in STAR_PLAYERS,
                            })
        except Exception as e:
            log.warning(f"Injury scrape error: {e}")
    log.info(f"Injuries loaded for {len(injuries)} teams")
    return injuries


# ═══════════════════════════════════════════════════════════════════════
# STEP 3: ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════
def american_to_prob(odds: int) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def devig(p1: float, p2: float) -> Tuple[float, float]:
    total = p1 + p2
    if total == 0:
        return 0.5, 0.5
    return p1 / total, p2 / total


def prob_to_american(p: float) -> int:
    if p <= 0 or p >= 1:
        return 0
    if p >= 0.5:
        return round(-100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def analyze_game(game: dict, sport_label: str) -> Optional[dict]:
    """Analyze a single game from Odds API data. Returns structured pick dict."""
    home = game['home_team']
    away = game['away_team']
    commence = game['commence_time']

    # Parse time
    dt = datetime.fromisoformat(commence.replace('Z', '+00:00'))
    dt_est = dt.astimezone(EST)
    game_date = dt_est.strftime('%Y-%m-%d')
    game_time = dt_est.strftime('%I:%M %p ET')

    # Aggregate across bookmakers
    home_ml_probs, away_ml_probs = [], []
    home_spread_points, home_spread_probs, away_spread_probs = [], [], []
    totals, over_probs, under_probs = [], [], []

    for bk in game.get('bookmakers', []):
        for mkt in bk.get('markets', []):
            if mkt['key'] == 'h2h':
                for o in mkt['outcomes']:
                    p = american_to_prob(o['price'])
                    if o['name'] == home:
                        home_ml_probs.append(p)
                    elif o['name'] == away:
                        away_ml_probs.append(p)
            elif mkt['key'] == 'spreads':
                for o in mkt['outcomes']:
                    p = american_to_prob(o['price'])
                    if o['name'] == home:
                        home_spread_points.append(o.get('point', 0))
                        home_spread_probs.append(p)
                    elif o['name'] == away:
                        away_spread_probs.append(p)
            elif mkt['key'] == 'totals':
                for o in mkt['outcomes']:
                    p = american_to_prob(o['price'])
                    if o['name'] == 'Over':
                        over_probs.append(p)
                        totals.append(o.get('point', 0))
                    elif o['name'] == 'Under':
                        under_probs.append(p)

    if not home_ml_probs or not away_ml_probs:
        return None

    # Consensus moneyline
    avg_home_ml = sum(home_ml_probs) / len(home_ml_probs)
    avg_away_ml = sum(away_ml_probs) / len(away_ml_probs)
    home_prob, away_prob = devig(avg_home_ml, avg_away_ml)

    # Consensus spread
    spread = round(sum(home_spread_points) / len(home_spread_points), 1) if home_spread_points else 0
    if home_spread_probs and away_spread_probs:
        avg_hsp = sum(home_spread_probs) / len(home_spread_probs)
        avg_asp = sum(away_spread_probs) / len(away_spread_probs)
        home_cover, away_cover = devig(avg_hsp, avg_asp)
    else:
        home_cover = away_cover = 0.5

    # Consensus total
    total_line = round(sum(totals) / len(totals), 1) if totals else None
    if over_probs and under_probs:
        avg_over = sum(over_probs) / len(over_probs)
        avg_under = sum(under_probs) / len(under_probs)
        over_prob, under_prob = devig(avg_over, avg_under)
    else:
        over_prob = under_prob = 0.5

    # Determine picks
    # ML pick
    if home_prob > away_prob:
        ml_pick, ml_prob = home, home_prob
    else:
        ml_pick, ml_prob = away, away_prob

    # Spread pick: who covers?
    if home_cover > away_cover:
        spread_pick = home
        cover_prob = home_cover
        spread_str = f"{spread:+.1f}" if spread != 0 else "PK"
    else:
        spread_pick = away
        cover_prob = away_cover
        spread_str = f"{-spread:+.1f}" if spread != 0 else "PK"

    # O/U pick
    if total_line:
        if over_prob > under_prob:
            ou_pick, ou_prob = 'Over', over_prob
        else:
            ou_pick, ou_prob = 'Under', under_prob
    else:
        ou_pick, ou_prob = None, 0.5

    # Edge: how far from 50/50
    edge = round(cover_prob - 0.5, 4)

    # Book count
    book_count = len(game.get('bookmakers', []))

    # Upset score (basic — enhanced in step 4)
    upset_score = 0
    upset_reasons = []
    if spread != 0:
        abs_spread = abs(spread)
        if abs_spread <= 3:
            upset_score += 0.3
            upset_reasons.append(f"Tight spread ({spread:+.1f})")
        elif abs_spread <= 5:
            upset_score += 0.15
        # Dog getting lots of ML action
        dog_prob = away_prob if spread < 0 else home_prob
        if dog_prob > 0.40:
            boost = (dog_prob - 0.35) * 0.5
            upset_score += boost
            upset_reasons.append(f"Dog ML strong ({dog_prob:.0%})")

    return {
        'sport': sport_label,
        'sport_key': game['id'],
        'home': home,
        'away': away,
        'commence_time': commence,
        'game_date': game_date,
        'game_time': game_time,
        'spread': spread,
        'spread_str': spread_str,
        'pick': spread_pick,  # Primary pick = spread cover
        'cover_prob': round(cover_prob, 4),
        'enhanced_prob': round(cover_prob, 4),  # Will be updated
        'edge': edge,
        'ml_pick': ml_pick,
        'ml_prob': round(ml_prob, 4),
        'ml_home_prob': round(home_prob, 4),
        'ml_away_prob': round(away_prob, 4),
        'total_line': total_line,
        'ou_pick': ou_pick,
        'ou_prob': round(ou_prob, 4) if ou_pick else None,
        'over_prob': round(over_prob, 4),
        'under_prob': round(under_prob, 4),
        'book_count': book_count,
        'upset_score': round(upset_score, 4),
        'upset_reasons': upset_reasons,
        'upset_flip': False,
        'home_injuries': [],
        'away_injuries': [],
    }


# ═══════════════════════════════════════════════════════════════════════
# STEP 4: UPSET COMPOSITE + INJURY ADJUSTMENT
# ═══════════════════════════════════════════════════════════════════════
def enhance_game(game: dict, injuries: dict):
    """Apply upset composite + injury adjustments to a game analysis."""
    home, away = game['home'], game['away']
    spread = game['spread']

    # Determine favorite/dog
    if spread < 0:
        fav, dog, dog_side = home, away, 'away'
    elif spread > 0:
        fav, dog, dog_side = away, home, 'home'
    else:
        return  # Pick'em, no upset logic

    # ─── Injuries ───
    home_inj = injuries.get(home, [])
    away_inj = injuries.get(away, [])
    game['home_injuries'] = [i for i in home_inj if i.get('status') in ('Out', 'Doubtful', 'Questionable')]
    game['away_injuries'] = [i for i in away_inj if i.get('status') in ('Out', 'Doubtful', 'Questionable')]

    fav_inj = injuries.get(fav, [])
    dog_inj = injuries.get(dog, [])
    fav_stars_out = sum(1 for i in fav_inj if i.get('star') and i.get('status') in ('Out', 'Doubtful'))
    dog_stars_out = sum(1 for i in dog_inj if i.get('star') and i.get('status') in ('Out', 'Doubtful'))

    score = game['upset_score']
    reasons = list(game['upset_reasons'])

    if fav_stars_out > 0 and dog_stars_out == 0:
        boost = fav_stars_out * 0.15
        score += boost
        reasons.append(f"🏥 Fav missing {fav_stars_out} star(s): +{boost:.2f}")
    elif dog_stars_out > 0 and fav_stars_out == 0:
        penalty = dog_stars_out * 0.10
        score -= penalty
        reasons.append(f"🏥 Dog missing {dog_stars_out} star(s): -{penalty:.2f}")

    # Home dog bonus
    if dog_side == 'home':
        score += 0.1
        reasons.append("🏠 Home dog +0.10")

    game['upset_score'] = round(max(score, 0), 4)
    game['upset_reasons'] = reasons

    # Enhanced probability adjustment
    if game['pick'] == dog and score > 0.3:
        boost = min(score * 0.05, 0.04)
        game['enhanced_prob'] = round(game['cover_prob'] + boost, 4)
    elif game['pick'] == fav and score > 0.5:
        penalty = min(score * 0.03, 0.03)
        game['enhanced_prob'] = round(game['cover_prob'] - penalty, 4)

    # UPSET FLIP — strong signal overrides the pick
    if score >= 0.8 and abs(spread) <= 10:
        if game['pick'] != dog:
            game['original_pick'] = game['pick']
            game['pick'] = dog
            game['enhanced_prob'] = round(1 - game['cover_prob'] + 0.02, 4)
            game['upset_flip'] = True
            game['pick_label'] = '🔄 UPSET FLIP'
            # Fix spread_str for flipped pick
            if spread < 0:
                game['spread_str'] = f"+{-spread:.1f}"
            else:
                game['spread_str'] = f"+{spread:.1f}"

    # ─── Apply Totals Engine v3 (market-blended) ───
    if TOTALS_V3_AVAILABLE and game.get('total_line') and game['total_line'] > 0:
        sport_key = 'nba' if game.get('sport') == 'NBA' else 'ncaab'
        
        # Store original devigged odds as fallback
        game['ou_devigged_pick'] = game.get('ou_pick')
        game['ou_devigged_prob'] = game.get('ou_prob')
        
        try:
            # Get or create engine for this sport (caches ESPN data)
            if sport_key not in _totals_engines:
                eng = TotalsEngineV3(sport=sport_key)
                eng.fetch_team_stats()
                _totals_engines[sport_key] = eng
            eng = _totals_engines[sport_key]
            
            spread = game.get('spread_home', game.get('spread', 0)) or 0
            result = eng.predict(
                home=game['home'],
                away=game['away'],
                posted_total=game['total_line'],
                spread=spread,
                game_date=game.get('game_date', '')
            )
            
            if result['pick'] != 'PASS':
                game['ou_pick'] = 'Over' if result['pick'] == 'OVER' else 'Under'
                game['ou_prob'] = result['confidence']
                game['ou_model_v3'] = result
                
                # Boost if devigged odds agree
                if game.get('ou_devigged_pick') == game['ou_pick'] and result['confidence'] > 0:
                    game['ou_prob'] = min(game['ou_prob'] + 0.02, 0.75)
                    game['ou_agreement'] = True
                else:
                    game['ou_agreement'] = False
                
                if game['ou_pick'] == 'Over':
                    game['over_prob'] = game['ou_prob']
                    game['under_prob'] = 1 - game['ou_prob']
                else:
                    game['under_prob'] = game['ou_prob']
                    game['over_prob'] = 1 - game['ou_prob']
            else:
                # No edge — keep devigged as-is but mark low confidence
                game['ou_model_v3'] = result
                log.info(f"V3 PASS (no edge): {game['away']} @ {game['home']}, edge={result['edge']}")
        except Exception as e:
            log.warning(f"Totals v3 exception for {game['away']} @ {game['home']}: {e}")


# ═══════════════════════════════════════════════════════════════════════
# STEP 5: PARLAY GENERATOR
# ═══════════════════════════════════════════════════════════════════════
def generate_parlays(games: list, legs: int, count: int) -> list:
    """Generate top parlays from a pool of games."""
    if len(games) < legs:
        return []

    pool = games[:min(len(games), 20)]  # Cap pool to avoid combinatorial explosion
    all_combos = []

    for combo in combinations(range(len(pool)), legs):
        picks = [pool[i] for i in combo]
        combined_prob = 1.0
        for p in picks:
            combined_prob *= p['enhanced_prob']
        if combined_prob > 0:
            # Implied payout
            payout = round((1 / combined_prob - 1) * 100, 2) if combined_prob > 0 else 0
            all_combos.append({
                'legs': [{
                    'game': f"{p['away']} @ {p['home']}",
                    'pick': p['pick'],
                    'type': 'spread',
                    'line': p['spread_str'],
                    'prob': p['enhanced_prob'],
                    'sport': p['sport'],
                    'commence_time': p['commence_time'],
                } for p in picks],
                'combined_prob': round(combined_prob, 6),
                'payout_odds': f"+{payout}" if payout > 0 else str(payout),
                'leg_count': legs,
            })

    # Sort by combined probability (highest = safest)
    all_combos.sort(key=lambda x: x['combined_prob'], reverse=True)
    return all_combos[:count]


def generate_ou_parlays(games: list, legs: int, count: int) -> list:
    """Generate O/U parlays."""
    ou_games = [g for g in games if g.get('ou_pick') and g.get('ou_prob', 0) > 0.52]
    if len(ou_games) < legs:
        return []

    pool = sorted(ou_games, key=lambda x: x['ou_prob'], reverse=True)[:15]
    all_combos = []

    for combo in combinations(range(len(pool)), legs):
        picks = [pool[i] for i in combo]
        combined_prob = 1.0
        for p in picks:
            combined_prob *= p['ou_prob']
        if combined_prob > 0:
            payout = round((1 / combined_prob - 1) * 100, 2)
            all_combos.append({
                'legs': [{
                    'game': f"{p['away']} @ {p['home']}",
                    'pick': p['ou_pick'],
                    'type': 'total',
                    'line': str(p['total_line']),
                    'prob': p['ou_prob'],
                    'sport': p['sport'],
                    'commence_time': p['commence_time'],
                } for p in picks],
                'combined_prob': round(combined_prob, 6),
                'payout_odds': f"+{payout}" if payout > 0 else str(payout),
                'leg_count': legs,
            })

    all_combos.sort(key=lambda x: x['combined_prob'], reverse=True)
    return all_combos[:count]


def generate_ml_parlays(games: list, legs: int, count: int) -> list:
    """Generate moneyline parlays from analyzed games."""
    # Filter to games with solid ML edge (prob > 0.55)
    ml_games = [g for g in games if g.get('ml_prob', 0) > 0.55]
    if len(ml_games) < legs:
        return []

    pool = sorted(ml_games, key=lambda x: x['ml_prob'], reverse=True)[:20]
    all_combos = []

    for combo in combinations(range(len(pool)), legs):
        picks = [pool[i] for i in combo]
        combined_prob = 1.0
        for p in picks:
            combined_prob *= p['ml_prob']
        if combined_prob > 0:
            payout = round((1 / combined_prob - 1) * 100, 2)
            # Calculate implied American odds for each ML leg
            ml_legs = []
            for p in picks:
                ml_american = prob_to_american(p['ml_prob'])
                ml_legs.append({
                    'game': f"{p['away']} @ {p['home']}",
                    'pick': p['ml_pick'],
                    'type': 'moneyline',
                    'line': f"{ml_american:+d}" if ml_american else "EVEN",
                    'prob': p['ml_prob'],
                    'sport': p['sport'],
                    'commence_time': p['commence_time'],
                })
            all_combos.append({
                'legs': ml_legs,
                'combined_prob': round(combined_prob, 6),
                'payout_odds': f"+{payout}" if payout > 0 else str(payout),
                'leg_count': legs,
            })

    all_combos.sort(key=lambda x: x['combined_prob'], reverse=True)
    return all_combos[:count]


# ═══════════════════════════════════════════════════════════════════════
# STEP 6: RESULT SCORER
# ═══════════════════════════════════════════════════════════════════════
def score_yesterday() -> dict:
    """Score yesterday's picks against actual results."""
    log.info(f"\n{'='*60}")
    log.info(f"SCORING YESTERDAY: {YESTERDAY}")

    # Load yesterday's picks
    yesterday_dir = ENGINE_DIR / f"picks_{YESTERDAY}"
    picks_file = yesterday_dir / "all_picks.json"
    if not picks_file.exists():
        # Try alternate location
        picks_file = ENGINE_DIR / f"picks_output_{YESTERDAY}.json"
    if not picks_file.exists():
        picks_file = ENGINE_DIR / "picks_output.json"
    
    if not picks_file.exists():
        log.warning(f"No picks file found for {YESTERDAY}")
        return {'error': 'No picks file found'}

    with open(picks_file) as f:
        picks_data = json.load(f)

    # Fetch actual scores from both sources
    all_scores = {}
    for sport in ['nba', 'ncaab']:
        espn = fetch_espn_scores(YESTERDAY, sport)
        all_scores.update(espn)

    # Also try Odds API scores
    for sport_key in SPORTS:
        for game in fetch_scores(sport_key, days_from=2):
            if not game.get('completed'):
                continue
            home = game['home_team']
            away = game['away_team']
            hs = as_ = None
            for s in game.get('scores', []):
                if s['name'] == home: hs = int(s['score'])
                elif s['name'] == away: as_ = int(s['score'])
            if hs is not None and as_ is not None:
                entry = {
                    'home': home, 'away': away,
                    'home_score': hs, 'away_score': as_,
                    'total': hs + as_,
                    'winner': home if hs > as_ else away,
                    'margin': hs - as_,
                }
                all_scores[home] = entry
                all_scores[away] = entry

    if not all_scores:
        log.warning("Could not fetch any scores")
        return {'error': 'No scores available'}

    log.info(f"Loaded {len(all_scores)} team scores")

    # Score picks
    results = {'date': YESTERDAY, 'scores_loaded': len(all_scores),
               'straight': {'correct': 0, 'incorrect': 0, 'no_score': 0, 'details': []},
               'spread': {'correct': 0, 'incorrect': 0, 'push': 0, 'no_score': 0, 'details': []},
               'ou': {'correct': 0, 'incorrect': 0, 'push': 0, 'no_score': 0, 'details': []},
               'ml_results': {'correct': 0, 'incorrect': 0, 'no_score': 0, 'details': []}}

    games = picks_data.get('all_games', picks_data.get('games', []))
    for g in games:
        home, away = g.get('home', ''), g.get('away', '')
        score_data = all_scores.get(home) or all_scores.get(away)
        if not score_data:
            results['straight']['no_score'] += 1
            results['spread']['no_score'] += 1
            continue

        actual_winner = score_data['winner']
        margin = score_data['margin']  # home - away
        total = score_data['total']

        # ML scoring
        ml_pick = g.get('ml_pick', '')
        if ml_pick == actual_winner:
            results['straight']['correct'] += 1
            results['straight']['details'].append(f"✅ {ml_pick} won ({score_data['away']} {score_data['away_score']} - {score_data['home']} {score_data['home_score']})")
        else:
            results['straight']['incorrect'] += 1
            results['straight']['details'].append(f"❌ {ml_pick} lost ({score_data['away']} {score_data['away_score']} - {score_data['home']} {score_data['home_score']})")

        # Spread scoring
        spread_pick = g.get('pick', '')
        spread_val = g.get('spread', 0)
        if spread_pick == home:
            adjusted = margin + spread_val
        else:
            adjusted = -margin - spread_val
        if adjusted > 0:
            results['spread']['correct'] += 1
        elif adjusted == 0:
            results['spread']['push'] += 1
        else:
            results['spread']['incorrect'] += 1

        # O/U scoring
        if g.get('total_line') and g.get('ou_pick'):
            ou_pick = g['ou_pick']
            if ou_pick == 'Over' and total > g['total_line']:
                results['ou']['correct'] += 1
            elif ou_pick == 'Under' and total < g['total_line']:
                results['ou']['correct'] += 1
            elif total == g['total_line']:
                results['ou']['push'] += 1
            else:
                results['ou']['incorrect'] += 1

        # ML scoring (separate from straight — uses ml_pick field explicitly)
        ml_pick = g.get('ml_pick', '')
        if ml_pick:
            if ml_pick == actual_winner:
                results['ml_results']['correct'] += 1
                results['ml_results']['details'].append(
                    f"✅ ML {ml_pick} won ({score_data['away']} {score_data['away_score']} - {score_data['home']} {score_data['home_score']})")
            else:
                results['ml_results']['incorrect'] += 1
                results['ml_results']['details'].append(
                    f"❌ ML {ml_pick} lost ({score_data['away']} {score_data['away_score']} - {score_data['home']} {score_data['home_score']})")
        else:
            results['ml_results']['no_score'] += 1

    # Score ML tier parlays
    ml_tiers = picks_data.get('ml_tiers', {})
    ml_tier_results = {}
    for tier_id, tier_data in ml_tiers.items():
        tier_picks = tier_data.get('picks', [])
        tier_w = tier_l = 0
        for parlay in tier_picks:
            all_hit = True
            for leg in parlay.get('legs', []):
                pick_team = leg.get('pick', '')
                score_data = all_scores.get(pick_team)
                if not score_data:
                    all_hit = False
                    break
                if score_data['winner'] != pick_team:
                    all_hit = False
                    break
            if all_hit:
                tier_w += 1
            else:
                tier_l += 1
        total = tier_w + tier_l
        ml_tier_results[tier_id] = {
            'wins': tier_w, 'losses': tier_l, 'total': total,
            'rate': round(tier_w / total, 4) if total > 0 else 0
        }
    results['ml_tier_results'] = ml_tier_results

    # Calculate rates
    for cat in ['straight', 'spread', 'ou', 'ml_results']:
        total = results[cat]['correct'] + results[cat]['incorrect']
        results[cat]['total'] = total
        results[cat]['rate'] = round(results[cat]['correct'] / total, 4) if total > 0 else 0

    # Save
    score_file = ENGINE_DIR / f"results_{YESTERDAY}_scorecard.json"
    with open(score_file, 'w') as f:
        json.dump(results, f, indent=2)
    log.info(f"Results saved to {score_file}")

    return results


# ═══════════════════════════════════════════════════════════════════════
# STEP 7: DEPLOY
# ═══════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════
# STEP 6B: PUSH TO TURSO CLOUD DB
# ═══════════════════════════════════════════════════════════════════════
TURSO_URL = "https://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2IiwicmlkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0.tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA"


def _turso_arg(value, typ="text"):
    """Format a value as a Turso HTTP API arg."""
    if value is None:
        return {"type": "null"}
    if typ == "integer":
        return {"type": "integer", "value": str(int(value))}
    if typ == "float":
        return {"type": "float", "value": float(value)}
    return {"type": "text", "value": str(value)}


def push_to_turso(games: list, pick_date: str):
    """Push analyzed games to Turso cloud DB via HTTP pipeline API."""
    log.info(f"\n☁️ Pushing {len(games)} games to Turso for {pick_date}...")

    requests_list = [
        # Delete existing picks for today (idempotent)
        {
            "type": "execute",
            "stmt": {
                "sql": "DELETE FROM daily_picks WHERE pick_date = ?",
                "args": [_turso_arg(pick_date)]
            }
        }
    ]

    for g in games:
        raw_json = json.dumps(g, default=str)
        requests_list.append({
            "type": "execute",
            "stmt": {
                "sql": """INSERT INTO daily_picks
                    (pick_date, sport, home, away, spread, spread_str, pick,
                     cover_prob, enhanced_prob, ml_pick, ml_prob, total_line,
                     ou_pick, ou_prob, upset_score, upset_flip, game_time,
                     commence_time, book_count, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                "args": [
                    _turso_arg(pick_date),
                    _turso_arg(g.get('sport', '')),
                    _turso_arg(g.get('home', '')),
                    _turso_arg(g.get('away', '')),
                    _turso_arg(g.get('spread'), "float"),
                    _turso_arg(g.get('spread_str', '')),
                    _turso_arg(g.get('pick', '')),
                    _turso_arg(g.get('cover_prob'), "float"),
                    _turso_arg(g.get('enhanced_prob'), "float"),
                    _turso_arg(g.get('ml_pick', '')),
                    _turso_arg(g.get('ml_prob'), "float"),
                    _turso_arg(g.get('total_line'), "float"),
                    _turso_arg(g.get('ou_pick')),
                    _turso_arg(g.get('ou_prob'), "float"),
                    _turso_arg(g.get('upset_score'), "float"),
                    _turso_arg(1 if g.get('upset_flip') else 0, "integer"),
                    _turso_arg(g.get('game_time', '')),
                    _turso_arg(g.get('commence_time', '')),
                    _turso_arg(g.get('book_count'), "integer"),
                    _turso_arg(raw_json),
                ]
            }
        })

    # Send pipeline request
    try:
        resp = requests.post(
            f"{TURSO_URL}/v2/pipeline",
            headers={
                "Authorization": f"Bearer {TURSO_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"requests": requests_list},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        errors = [r for r in result.get("results", []) if r.get("type") == "error"]
        if errors:
            log.error(f"Turso pipeline errors: {errors[:3]}")
        else:
            log.info(f"  ✅ Pushed {len(games)} games to Turso")
    except Exception as e:
        log.error(f"  ❌ Turso push failed: {e}")


def deploy_to_vercel():
    """Copy picks to website public dir and deploy."""
    website_dir = ENGINE_DIR.parent  # parlayguarantee root
    public_dir = website_dir / "public"
    
    if not public_dir.exists():
        log.warning(f"No public dir at {public_dir}, skipping deploy")
        return False

    # Copy latest picks
    for fname in ['picks_output.json', 'analyzed_games.json']:
        src = ENGINE_DIR / fname
        dst = public_dir / fname
        if src.exists():
            import shutil
            shutil.copy2(src, dst)
            log.info(f"Copied {fname} → public/")

    # Deploy
    try:
        result = subprocess.run(
            ['C:\\Users\\joshs\\AppData\\Roaming\\npm\\vercel.cmd', '--prod', '--yes'],
            cwd=str(website_dir), capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info("✅ Vercel deploy successful")
            return True
        else:
            log.error(f"Vercel deploy failed: {result.stderr[:500]}")
            return False
    except Exception as e:
        log.error(f"Deploy error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════
def run_picks_pipeline() -> dict:
    """Full autonomous picks pipeline. Returns summary dict."""
    log.info(f"{'='*60}")
    log.info(f"🏀 AUTOPILOT — {TODAY} {NOW_EST.strftime('%I:%M %p ET')}")
    log.info(f"{'='*60}")

    summary = {
        'date': TODAY,
        'timestamp': NOW_EST.isoformat(),
        'sports': {},
        'total_games': 0,
        'errors': [],
    }

    # ─── Fetch odds for all sports ───
    all_games = []
    for sport_key, sport_label in SPORTS.items():
        log.info(f"\n📡 Fetching {sport_label} odds...")
        try:
            raw = fetch_odds(sport_key, "h2h,spreads,totals")
            if not raw:
                summary['errors'].append(f"{sport_label}: no data from API")
                continue

            count = 0
            for g in raw:
                result = analyze_game(g, sport_label)
                if result:
                    all_games.append(result)
                    count += 1
            
            summary['sports'][sport_label] = {'raw': len(raw), 'analyzed': count}
            log.info(f"  ✅ {sport_label}: {len(raw)} events → {count} analyzed")
        except Exception as e:
            log.error(f"  ❌ {sport_label} error: {e}")
            summary['errors'].append(f"{sport_label}: {str(e)}")

    if not all_games:
        log.error("NO GAMES FOUND — aborting")
        summary['errors'].append("No games available from any sport")
        return summary

    # Filter to today + tomorrow
    tomorrow = (NOW_EST + timedelta(days=1)).strftime('%Y-%m-%d')
    target_games = [g for g in all_games if g['game_date'] in (TODAY, tomorrow)]
    log.info(f"\n📊 {len(target_games)} target games (today + tomorrow)")

    if not target_games:
        # Maybe all games are today under a different timezone interpretation
        target_games = all_games
        log.info(f"  Using all {len(target_games)} games (no date filter match)")

    # Filter out games that have already started (only keep future games)
    now_utc = datetime.now(timezone.utc)
    pre_filter_count = len(target_games)
    future_games = []
    for g in target_games:
        ct = g.get('commence_time', '')
        if ct:
            try:
                dt = datetime.fromisoformat(ct.replace('Z', '+00:00'))
                if dt <= now_utc:
                    continue  # game already started, skip
            except (ValueError, TypeError):
                pass  # can't parse, keep it
        future_games.append(g)
    if future_games:
        target_games = future_games
        started_count = pre_filter_count - len(target_games)
        if started_count > 0:
            log.info(f"  ⏰ Filtered out {started_count} already-started games, {len(target_games)} remaining")
    else:
        log.info(f"  ⚠️ All {pre_filter_count} games already started — keeping all for reference")

    # ─── Fetch injuries ───
    log.info("\n🏥 Fetching injuries...")
    injuries = fetch_injuries()

    # ─── Enhance with upset composite + injuries ───
    log.info("\n🔄 Computing upset composites + injury adjustments...")
    for g in target_games:
        enhance_game(g, injuries)

    # ─── NBA Upset Composite v2 (overrides old dumb composite for NBA) ───
    if NBA_UPSET_V2:
        log.info("\n🧠 Running NBA Upset Composite v2 (smart model)...")
        nba_upset_v2(target_games, injuries)
    else:
        log.info("⚠️ NBA Upset Composite v2 not available — using legacy composite")

    # Sort by enhanced probability
    target_games.sort(key=lambda x: x.get('enhanced_prob', 0), reverse=True)

    upset_flips = [g for g in target_games if g.get('upset_flip')]
    if upset_flips:
        log.info(f"  🔄 {len(upset_flips)} upset flips:")
        for g in upset_flips:
            log.info(f"    {g['away']} @ {g['home']} → {g['pick']} (was {g.get('original_pick')})")

    summary['total_games'] = len(target_games)

    # ─── Save analyzed_games.json ───
    with open(ENGINE_DIR / 'analyzed_games.json', 'w', encoding='utf-8') as f:
        json.dump(target_games, f, indent=2, default=str)
    log.info(f"\n💾 Saved analyzed_games.json ({len(target_games)} games)")

    # ─── Generate tiered parlays ───
    log.info("\n🎰 Generating parlays...")
    nba_games = sorted([g for g in target_games if g['sport'] == 'NBA'],
                       key=lambda x: x['enhanced_prob'], reverse=True)
    ncaab_games = sorted([g for g in target_games if g['sport'] == 'NCAAB'],
                         key=lambda x: x['enhanced_prob'], reverse=True)
    all_sorted = sorted(target_games, key=lambda x: x['enhanced_prob'], reverse=True)

    output = {
        'date': TODAY,
        'generated_at': NOW_EST.isoformat(),
        'total_games': len(target_games),
        'nba_games': len(nba_games),
        'ncaab_games': len(ncaab_games),
        'all_games': target_games,
        'tiers': {},
        'ou_tiers': {},
        'ml_tiers': {},
    }

    # Spread parlays
    for tier_id, cfg in TIER_CONFIG.items():
        legs, count = cfg['legs'], cfg['count']
        pool = all_sorted[:25]
        picks = generate_parlays(pool, legs, count)
        output['tiers'][tier_id] = {
            'tier_id': tier_id, 'legs': legs,
            'picks': picks, 'pool_size': len(pool),
        }
        if picks:
            log.info(f"  {tier_id}: {len(picks)} parlays (top prob: {picks[0]['combined_prob']:.1%})")

    # O/U parlays
    for tier_id in ['single', '2leg', '3leg']:
        cfg = TIER_CONFIG[tier_id]
        legs, count = cfg['legs'], cfg['count']
        picks = generate_ou_parlays(all_sorted, legs, count)
        output['ou_tiers'][tier_id] = {
            'tier_id': f"ou_{tier_id}", 'legs': legs,
            'picks': picks, 'pool_size': len(all_sorted),
        }

    # ML parlays
    ML_TIER_CONFIG = {
        'single': {'legs': 1, 'count': 10},
        '2leg':   {'legs': 2, 'count': 8},
        '3leg':   {'legs': 3, 'count': 5},
        '4leg':   {'legs': 4, 'count': 3},
        '5leg':   {'legs': 5, 'count': 2},
    }
    for tier_id, cfg in ML_TIER_CONFIG.items():
        legs, count = cfg['legs'], cfg['count']
        picks = generate_ml_parlays(all_sorted, legs, count)
        output['ml_tiers'][tier_id] = {
            'tier_id': f"ml_{tier_id}", 'legs': legs,
            'picks': picks, 'pool_size': len(all_sorted),
        }
        if picks:
            log.info(f"  ml_{tier_id}: {len(picks)} ML parlays (top prob: {picks[0]['combined_prob']:.1%})")

    # ─── Save picks_output.json ───
    with open(ENGINE_DIR / 'picks_output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=str)
    log.info(f"💾 Saved picks_output.json")

    # ─── Save dated copy ───
    all_picks_file = PICKS_DIR / 'all_picks.json'
    with open(all_picks_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=str)
    log.info(f"💾 Saved {all_picks_file}")

    # ─── Save individual sport picks for backward compat ───
    for sport, games in [('nba', nba_games), ('ncaab', ncaab_games)]:
        if games:
            sport_file = PICKS_DIR / f"{sport}_picks.json"
            with open(sport_file, 'w', encoding='utf-8') as f:
                json.dump({'sport': sport.upper(), 'date': TODAY, 'picks': games}, f, indent=2, default=str)

    # ─── Push to Turso cloud DB ───
    try:
        push_to_turso(target_games, TODAY)
    except Exception as e:
        log.error(f"Turso push failed (non-fatal): {e}")
        summary['errors'].append(f"Turso push: {str(e)}")

    return summary


def format_summary(summary: dict, results: dict = None) -> str:
    """Format a clean summary for Telegram."""
    lines = [f"🏀 AUTOPILOT — {TODAY} {NOW_EST.strftime('%I:%M %p ET')}"]
    lines.append("=" * 40)

    total = summary.get('total_games', 0)
    for sport, info in summary.get('sports', {}).items():
        lines.append(f"  {sport}: {info['analyzed']} games")
    lines.append(f"  Total: {total} games analyzed")

    if summary.get('errors'):
        lines.append(f"\n⚠️ Errors: {', '.join(summary['errors'])}")

    # Load analyzed games for quick stats
    try:
        with open(ENGINE_DIR / 'analyzed_games.json') as f:
            games = json.load(f)
        
        high_conf = [g for g in games if g.get('enhanced_prob', 0) >= 0.60]
        flips = [g for g in games if g.get('upset_flip')]
        
        if high_conf:
            lines.append(f"\n🔥 HIGH CONFIDENCE (≥60%): {len(high_conf)} picks")
            for g in high_conf[:10]:
                flip = " 🔄" if g.get('upset_flip') else ""
                lines.append(f"  • {g['pick']} {g['spread_str']} ({g['enhanced_prob']:.0%}) — {g['away']} @ {g['home']}{flip}")
        
        if flips:
            lines.append(f"\n🔄 UPSET FLIPS: {len(flips)}")
            for g in flips:
                lines.append(f"  • {g['pick']} (was {g.get('original_pick')}) — {g['away']} @ {g['home']}")
    except:
        pass

    if results and not results.get('error'):
        lines.append(f"\n📊 YESTERDAY ({YESTERDAY}):")
        for cat, label in [('straight', 'ML(legacy)'), ('spread', 'Spread'), ('ou', 'O/U'), ('ml_results', 'ML')]:
            r = results.get(cat, {})
            total = r.get('total', 0)
            if total > 0:
                lines.append(f"  {label}: {r['correct']}/{total} ({r['rate']:.0%})")

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='ParlayGuarantee Autopilot')
    parser.add_argument('--picks-only', action='store_true', help='Skip scoring + deploy')
    parser.add_argument('--score-only', action='store_true', help='Score yesterday only')
    parser.add_argument('--no-deploy', action='store_true', help='Skip Vercel deploy')
    parser.add_argument('--force-picks', action='store_true', help='Force regenerate picks even if already locked today')
    args = parser.parse_args()

    start = time.time()
    results = None
    summary = None

    try:
        if not args.picks_only:
            results = score_yesterday()
            if results and not results.get('error'):
                sr = results.get('spread', {})
                log.info(f"\n📊 Yesterday's spread: {sr.get('correct', 0)}/{sr.get('total', 0)} ({sr.get('rate', 0):.0%})")
                # Sync results to Turso so Vercel can read them
                try:
                    import subprocess
                    subprocess.run([sys.executable, str(ENGINE_DIR / 'sync_results_to_turso.py')],
                                   timeout=30, capture_output=True)
                    log.info("  ✅ Results synced to Turso")
                except Exception as e:
                    log.warning(f"  ⚠️ Turso results sync failed: {e}")

            # Auto-capture/cancel Stripe holds based on results
            try:
                log.info("\n💳 Running auto-capture on Stripe holds...")
                from auto_capture import process_holds
                cap_stats = process_holds()
                if cap_stats:
                    log.info(f"  💰 Captured: {cap_stats['captured']} | ❌ Cancelled: {cap_stats['cancelled']} | ⏳ Pending: {cap_stats['pending']}")
            except Exception as e:
                log.warning(f"  ⚠️ Auto-capture failed: {e}")

        if not args.score_only:
            # LOCK: Only generate picks once per day. Subsequent runs skip pick generation.
            lock_file = PICKS_DIR / '.picks_locked'
            if lock_file.exists() and not args.force_picks:
                log.info(f"\n🔒 Picks already locked for {TODAY} (generated earlier). Skipping pick generation.")
                log.info("   Use --force-picks to override. Only scoring + deploy will run.")
                summary = {'total_games': 0, 'sports': {}, 'errors': [], 'skipped': True}
            else:
                summary = run_picks_pipeline()
                # Create lock file after successful pick generation
                if summary and not summary.get('errors'):
                    lock_file.write_text(f"Locked at {NOW_EST.isoformat()}\n", encoding='utf-8')
                    log.info(f"🔒 Picks locked for {TODAY}")

            if not args.no_deploy and not args.picks_only:
                log.info("\n🚀 Deploying to Vercel...")
                deploy_to_vercel()

    except Exception as e:
        log.error(f"FATAL: {traceback.format_exc()}")
        summary = summary or {'errors': [str(e)]}

    elapsed = time.time() - start
    log.info(f"\n⏱️ Total: {elapsed:.1f}s")

    # Print final summary
    if summary:
        report = format_summary(summary, results)
        print(f"\n{report}")

        # Save summary
        with open(PICKS_DIR / 'summary.txt', 'w', encoding='utf-8') as f:
            f.write(report)
