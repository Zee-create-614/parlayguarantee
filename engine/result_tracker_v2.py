"""
ParlayGuarantee Result Tracker v2 — All Sports, All Bet Types
Scores NBA + NCAAB moneyline, spread, and over/under picks against ESPN actuals.

Usage:
    python result_tracker_v2.py --date 2026-02-20
    python result_tracker_v2.py --date 2026-02-20 --sport nba
    python result_tracker_v2.py                     # scores yesterday
"""

import sys, json, sqlite3, argparse, logging, requests
from datetime import date, timedelta
from pathlib import Path
from difflib import get_close_matches
from typing import Dict, List, Optional, Tuple

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent
HISTORY_DIR = ENGINE_DIR / "history"
DB_PATH = ENGINE_DIR / "results.db"

ESPN_URLS = {
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "ncaab": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
}

# ── NBA team aliases ──
NBA_ALIASES = {
    'la clippers': 'LA Clippers', 'los angeles clippers': 'LA Clippers',
    'los angeles lakers': 'Los Angeles Lakers', 'la lakers': 'Los Angeles Lakers',
    'okc thunder': 'Oklahoma City Thunder', 'okc': 'Oklahoma City Thunder',
}

def normalize_nba(name: str) -> str:
    if not name: return name
    return NBA_ALIASES.get(name.lower().strip(), name.strip())

# ── Fuzzy team matching for NCAAB ──
def fuzzy_match_team(name: str, candidates: List[str]) -> Optional[str]:
    """Match a team name against a list of candidates using multiple strategies."""
    if not name or not candidates:
        return None
    name_l = name.lower().strip()
    # Exact
    for c in candidates:
        if c.lower().strip() == name_l:
            return c
    # Substring containment
    for c in candidates:
        cl = c.lower()
        if name_l in cl or cl in name_l:
            return c
    # Mascot match (last word)
    mascot = name_l.split()[-1] if name_l.split() else ""
    for c in candidates:
        if c.lower().split()[-1] == mascot:
            return c
    # School/city match (first word)
    school = name_l.split()[0] if name_l.split() else ""
    for c in candidates:
        if c.lower().split()[0] == school:
            return c
    # difflib fallback
    matches = get_close_matches(name_l, [c.lower() for c in candidates], n=1, cutoff=0.6)
    if matches:
        for c in candidates:
            if c.lower() == matches[0]:
                return c
    return None

# ── ESPN Score Fetching ──
def fetch_scores(sport: str, game_date: str) -> Dict[str, Dict]:
    """Fetch scores from ESPN. Returns dict keyed by normalized team name -> game result."""
    url = ESPN_URLS.get(sport)
    if not url:
        return {}
    
    date_str = game_date.replace("-", "")
    params = {"dates": date_str}
    if sport == "ncaab":
        params["limit"] = 500
        params["groups"] = 50  # All D1 games, not just top conferences
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"ESPN fetch failed for {sport}/{game_date}: {e}")
        return {}
    
    results = {}
    for event in data.get("events", []):
        comps = event.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status != "STATUS_FINAL":
            continue
        
        teams = comp.get("competitors", [])
        if len(teams) < 2:
            continue
        
        home_name = away_name = ""
        home_score = away_score = 0
        for t in teams:
            tn = t.get("team", {}).get("displayName", "")
            sc = int(t.get("score", 0))
            if t.get("homeAway") == "home":
                home_name, home_score = tn, sc
            else:
                away_name, away_score = tn, sc
        
        if sport == "nba":
            home_name = normalize_nba(home_name)
            away_name = normalize_nba(away_name)
        
        winner = home_name if home_score > away_score else away_name
        game = {
            "home": home_name, "away": away_name,
            "home_score": home_score, "away_score": away_score,
            "total": home_score + away_score, "winner": winner,
        }
        results[home_name] = game
        results[away_name] = game
    
    logger.info(f"ESPN {sport.upper()}: {len(set(id(v) for v in results.values()))} final games for {game_date}")
    return results

def find_game(team1: str, team2: str, scores: Dict, sport: str) -> Optional[Dict]:
    """Find a game result by team names, with fuzzy matching for NCAAB."""
    # Direct lookup
    for key in [team1, team2]:
        if key in scores:
            return scores[key]
    
    if sport == "nba":
        for key in [normalize_nba(team1), normalize_nba(team2)]:
            if key in scores:
                return scores[key]
        return None
    
    # Fuzzy for NCAAB
    all_teams = list(scores.keys())
    for name in [team1, team2]:
        match = fuzzy_match_team(name, all_teams)
        if match and match in scores:
            return scores[match]
    return None

# ── Pick Loading ──
def load_nba_ml_spread(game_date: str) -> List[Dict]:
    """Load NBA moneyline/spread picks."""
    picks = []
    # Try history first, then current
    for path in [
        HISTORY_DIR / f"analyzed_games_{game_date}.json",
        ENGINE_DIR / "analyzed_games.json",
    ]:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            matching = [g for g in data if g.get("game_date", "") == game_date]
            if matching:
                for g in matching:
                    picks.append({
                        "sport": "nba", "bet_type": "moneyline",
                        "home": normalize_nba(g.get("home", "")),
                        "away": normalize_nba(g.get("away", "")),
                        "pick": normalize_nba(g.get("pick", "")),
                        "confidence": g.get("win_prob", 0),
                        "spread": g.get("spread"),
                        "pick_label": g.get("pick_label", ""),
                    })
                break
    return picks

def load_nba_ou(game_date: str) -> List[Dict]:
    path = ENGINE_DIR / f"tonight_nba_ou_{game_date}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    games = data.get("games", []) if isinstance(data, dict) else data
    picks = []
    for g in games:
        picks.append({
            "sport": "nba", "bet_type": "over_under",
            "home": normalize_nba(g.get("home", "")),
            "away": normalize_nba(g.get("away", "")),
            "ou_pick": g.get("pick", "").upper(),
            "total_line": g.get("total_line", 0),
            "confidence": g.get("win_prob", 0),
        })
    return picks

def load_ncaab_ml_spread(game_date: str) -> List[Dict]:
    """Load NCAAB moneyline/spread picks from ncaab_picks or history/ncaab_analyzed_games."""
    picks = []
    for path in [
        ENGINE_DIR / f"ncaab_picks_{game_date}.json",
        HISTORY_DIR / f"ncaab_analyzed_games_{game_date}.json",
    ]:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Match target date OR next day (UTC game_time pushes date forward for evening games)
            next_day = (date.fromisoformat(game_date) + timedelta(days=1)).isoformat()
            matching = [g for g in data if g.get("game_date", "") in (game_date, next_day)]
            if not matching:
                matching = data  # Trust filename if date filter fails
            if matching:
                for g in matching:
                    home = g.get("home_team", g.get("home", ""))
                    away = g.get("away_team", g.get("away", ""))
                    pick_winner = g.get("predicted_winner", g.get("pick", ""))
                    
                    # Parse spread from spread_pick field like "Ball State Cardinals +14.5"
                    spread_val = g.get("spread")
                    spread_pick_str = g.get("spread_pick", "")
                    spread_team = None
                    if spread_pick_str and not spread_val:
                        # Try to extract spread value
                        parts = spread_pick_str.rsplit(" ", 1)
                        if len(parts) == 2:
                            try:
                                spread_val = float(parts[1])
                                spread_team = parts[0]
                            except ValueError:
                                pass
                    
                    # Moneyline pick
                    picks.append({
                        "sport": "ncaab", "bet_type": "moneyline",
                        "home": home, "away": away,
                        "pick": pick_winner,
                        "confidence": g.get("confidence", g.get("win_prob", 0)),
                        "spread": spread_val,
                        "spread_team": spread_team or pick_winner,
                    })
                    
                    # O/U from this file if present
                    ou_pick_str = g.get("ou_pick", "")
                    total = g.get("total")
                    if ou_pick_str and total:
                        # Parse "Over 146.5" -> OVER, 146.5
                        ou_parts = ou_pick_str.split()
                        ou_dir = ou_parts[0].upper() if ou_parts else ""
                        ou_line = float(ou_parts[1]) if len(ou_parts) > 1 else total
                        picks.append({
                            "sport": "ncaab", "bet_type": "over_under",
                            "home": home, "away": away,
                            "ou_pick": ou_dir,
                            "total_line": ou_line,
                            "confidence": g.get("spread_confidence", 0.5),
                        })
                break
    return picks

def load_ncaab_ou(game_date: str) -> List[Dict]:
    path = ENGINE_DIR / f"tonight_ncaab_ou_{game_date}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    games = data.get("games", []) if isinstance(data, dict) else data
    picks = []
    for g in games:
        picks.append({
            "sport": "ncaab", "bet_type": "over_under",
            "home": g.get("home", ""),
            "away": g.get("away", ""),
            "ou_pick": g.get("pick", "").upper(),
            "total_line": g.get("total_line", 0),
            "confidence": g.get("win_prob", 0),
        })
    return picks

# ── DB Setup ──
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    
    # Create tables if not exist
    c.execute("""CREATE TABLE IF NOT EXISTS pick_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, product TEXT NOT NULL, pick_number INTEGER NOT NULL,
        type TEXT NOT NULL, predicted_winner TEXT NOT NULL,
        actual_winner TEXT, correct INTEGER, confidence REAL, odds TEXT,
        game_home TEXT, game_away TEXT, home_score INTEGER, away_score INTEGER,
        spread REAL, spread_pick TEXT, spread_correct INTEGER,
        pick_label TEXT, upset_score REAL, value_score REAL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(date, product, pick_number, predicted_winner)
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS daily_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL, product TEXT NOT NULL,
        total_picks INTEGER, correct_picks INTEGER, accuracy REAL,
        spread_correct INTEGER DEFAULT 0, spread_total INTEGER DEFAULT 0,
        spread_accuracy REAL DEFAULT 0,
        parlays_hit INTEGER DEFAULT 0, total_parlays INTEGER DEFAULT 0,
        deposit_kept INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(date, product)
    )""")
    
    # Add new columns idempotently
    new_cols_picks = [
        ("sport", "TEXT"), ("bet_type", "TEXT"),
        ("ou_pick", "TEXT"), ("total_line", "REAL"),
        ("total_actual", "REAL"), ("ou_correct", "INTEGER"),
    ]
    new_cols_summary = [
        ("sport", "TEXT"), ("ou_correct", "INTEGER DEFAULT 0"),
        ("ou_total", "INTEGER DEFAULT 0"), ("ou_accuracy", "REAL DEFAULT 0"),
    ]
    for col, typ in new_cols_picks:
        try: c.execute(f"ALTER TABLE pick_results ADD COLUMN {col} {typ}")
        except: pass
    for col, typ in new_cols_summary:
        try: c.execute(f"ALTER TABLE daily_summaries ADD COLUMN {col} {typ}")
        except: pass
    
    conn.commit()
    return conn

# ── Scoring Logic ──
def check_spread(pick_team: str, spread: float, home: str, away: str,
                 home_score: int, away_score: int, sport: str) -> Optional[bool]:
    if spread is None:
        return None
    
    pick_norm = normalize_nba(pick_team) if sport == "nba" else pick_team.lower()
    home_norm = normalize_nba(home) if sport == "nba" else home.lower()
    
    if pick_norm == home_norm or (sport == "ncaab" and fuzzy_match_team(pick_team, [home])):
        pick_margin = home_score - away_score
    else:
        pick_margin = away_score - home_score
    
    return (pick_margin + spread) > 0

def check_ou(ou_pick: str, total_line: float, actual_total: int) -> Optional[bool]:
    if not ou_pick or not total_line:
        return None
    if ou_pick == "OVER":
        return actual_total > total_line
    elif ou_pick == "UNDER":
        return actual_total < total_line
    return None

def score_picks(game_date: str, sport: str, picks: List[Dict], scores: Dict, conn: sqlite3.Connection) -> Dict:
    """Score a list of picks against scores. Returns summary stats."""
    c = conn.cursor()
    
    # Product mapping
    product_map = {
        ("nba", "moneyline"): "nba_engine",
        ("nba", "over_under"): "nba_ou",
        ("ncaab", "moneyline"): "ncaab_engine",
        ("ncaab", "over_under"): "ncaab_ou",
        ("nhl", "moneyline"): "nhl_engine",
        ("nhl", "over_under"): "nhl_ou",
    }
    
    stats = {"ml": [0, 0], "spread": [0, 0], "ou": [0, 0], "details": []}
    pick_counters = {}  # per-product pick numbering
    
    for pick in picks:
        bt = pick.get("bet_type", "moneyline")
        home = pick.get("home", "")
        away = pick.get("away", "")
        product = product_map.get((sport, bt), f"{sport}_{bt}")
        
        game = find_game(home, away, scores, sport)
        if not game:
            stats["details"].append(f"⚪ {away} @ {home} — no result found")
            continue
        
        hs, as_ = game["home_score"], game["away_score"]
        actual_total = game["total"]
        winner = game["winner"]
        
        # Counter for this product
        pick_counters[product] = pick_counters.get(product, 0) + 1
        pnum = pick_counters[product]
        
        if bt == "over_under":
            ou_pick = pick.get("ou_pick", "")
            total_line = pick.get("total_line", 0)
            hit = check_ou(ou_pick, total_line, actual_total)
            if hit is not None:
                stats["ou"][1] += 1
                if hit: stats["ou"][0] += 1
            
            emoji = "✅" if hit else "❌" if hit is not None else "⚪"
            detail = f"{emoji} {away} @ {home}: {ou_pick} {total_line} | Actual: {actual_total}"
            stats["details"].append(detail)
            
            # Match home/away to ESPN names for DB
            espn_home = game["home"]
            espn_away = game["away"]
            
            try:
                c.execute("""INSERT OR REPLACE INTO pick_results
                    (date, product, pick_number, type, predicted_winner, actual_winner,
                     correct, confidence, odds, game_home, game_away,
                     home_score, away_score, sport, bet_type,
                     ou_pick, total_line, total_actual, ou_correct)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (game_date, product, pnum, "straight",
                     ou_pick, f"{'OVER' if actual_total > total_line else 'UNDER'}",
                     1 if hit else 0, pick.get("confidence", 0), "",
                     espn_home, espn_away, hs, as_,
                     sport, bt, ou_pick, total_line, actual_total,
                     1 if hit else (0 if hit is not None else None)))
            except Exception as e:
                logger.error(f"DB insert error: {e}")
        
        else:  # moneyline / spread
            predicted = pick.get("pick", "")
            spread = pick.get("spread")
            
            # ML check - need fuzzy for ncaab
            if sport == "nba":
                ml_hit = normalize_nba(predicted) == normalize_nba(winner)
            else:
                # Fuzzy check
                ml_hit = (predicted.lower() == winner.lower() or
                          fuzzy_match_team(predicted, [winner]) is not None)
            
            stats["ml"][1] += 1
            if ml_hit: stats["ml"][0] += 1
            
            # Spread check
            spread_team = pick.get("spread_team", predicted)
            sp_hit = check_spread(spread_team, spread, home, away, hs, as_, sport)
            if sp_hit is not None:
                stats["spread"][1] += 1
                if sp_hit: stats["spread"][0] += 1
            
            emoji = "✅" if ml_hit else "❌"
            sp_str = ""
            if sp_hit is not None:
                sp_str = f" | Spread {'✅' if sp_hit else '❌'} ({spread:+.1f})"
            
            espn_home = game["home"]
            espn_away = game["away"]
            detail = f"{emoji} {away} @ {home}: picked {predicted} | Winner: {winner} ({as_}-{hs}){sp_str}"
            stats["details"].append(detail)
            
            try:
                c.execute("""INSERT OR REPLACE INTO pick_results
                    (date, product, pick_number, type, predicted_winner, actual_winner,
                     correct, confidence, odds, game_home, game_away,
                     home_score, away_score, spread, spread_pick, spread_correct,
                     pick_label, sport, bet_type)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (game_date, product, pnum, "straight",
                     predicted, winner,
                     1 if ml_hit else 0, pick.get("confidence", 0), "",
                     espn_home, espn_away, hs, as_,
                     spread,
                     f"{spread_team} {spread:+.1f}" if spread else None,
                     1 if sp_hit else (0 if sp_hit is not None else None),
                     pick.get("pick_label", ""),
                     sport, bt))
            except Exception as e:
                logger.error(f"DB insert error: {e}")
    
    conn.commit()
    return stats

def save_daily_summary(game_date: str, sport: str, product: str, stats: Dict, conn: sqlite3.Connection):
    c = conn.cursor()
    ml_c, ml_t = stats["ml"]
    sp_c, sp_t = stats["spread"]
    ou_c, ou_t = stats["ou"]
    ml_acc = (ml_c / ml_t * 100) if ml_t else 0
    sp_acc = (sp_c / sp_t * 100) if sp_t else 0
    ou_acc = (ou_c / ou_t * 100) if ou_t else 0
    try:
        c.execute("""INSERT OR REPLACE INTO daily_summaries
            (date, product, total_picks, correct_picks, accuracy,
             spread_correct, spread_total, spread_accuracy,
             sport, ou_correct, ou_total, ou_accuracy, deposit_kept)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (game_date, product, ml_t, ml_c, round(ml_acc, 1),
             sp_c, sp_t, round(sp_acc, 1),
             sport, ou_c, ou_t, round(ou_acc, 1),
             1 if ml_acc >= 60 else 0))
        conn.commit()
    except Exception as e:
        logger.error(f"Summary insert error: {e}")

# ── Main ──
def run(game_date: str, sports: List[str]) -> str:
    conn = init_db()
    output_lines = []
    
    def log(msg):
        print(msg)
        output_lines.append(msg)
    
    log(f"🏆 ParlayGuarantee Result Tracker v2")
    log(f"📅 Scoring picks for: {game_date}")
    log("=" * 55)
    
    all_stats = {}
    
    for sport in sports:
        scores = fetch_scores(sport, game_date)
        if not scores:
            log(f"\n⚠️ No {sport.upper()} scores found for {game_date}")
            continue
        
        game_count = len(set(id(v) for v in scores.values()))
        log(f"\n{'🏀' if sport != 'nhl' else '🏒'} {sport.upper()} — {game_count} games found")
        log("-" * 45)
        
        # Load picks by type
        if sport == "nba":
            ml_picks = load_nba_ml_spread(game_date)
            ou_picks = load_nba_ou(game_date)
        elif sport == "ncaab":
            ml_picks = load_ncaab_ml_spread(game_date)
            # Separate ML and OU picks that came from ncaab_picks file
            embedded_ou = [p for p in ml_picks if p["bet_type"] == "over_under"]
            ml_picks = [p for p in ml_picks if p["bet_type"] == "moneyline"]
            ou_picks_file = load_ncaab_ou(game_date)
            # Deduplicate: use tonight_ncaab_ou if available, else embedded
            ou_picks = ou_picks_file if ou_picks_file else embedded_ou
        else:
            ml_picks = []
            ou_picks = []
        
        all_picks = ml_picks + ou_picks
        
        if not all_picks:
            log(f"  No picks found for {sport.upper()}")
            continue
        
        log(f"  📊 {len(ml_picks)} ML/spread picks, {len(ou_picks)} O/U picks")
        
        stats = score_picks(game_date, sport, all_picks, scores, conn)
        all_stats[sport] = stats
        
        # Print details
        log("")
        if ml_picks:
            log(f"  📈 Moneyline + Spread:")
            for d in stats["details"]:
                if "OVER" not in d and "UNDER" not in d:
                    log(f"    {d}")
        
        if ou_picks:
            log(f"\n  📊 Over/Under:")
            for d in stats["details"]:
                if "OVER" in d or "UNDER" in d:
                    log(f"    {d}")
        
        # Sport summary
        ml_c, ml_t = stats["ml"]
        sp_c, sp_t = stats["spread"]
        ou_c, ou_t = stats["ou"]
        log(f"\n  ── {sport.upper()} Summary ──")
        if ml_t: log(f"  🎯 Moneyline: {ml_c}/{ml_t} ({ml_c/ml_t*100:.1f}%)")
        if sp_t: log(f"  📐 Spread:    {sp_c}/{sp_t} ({sp_c/sp_t*100:.1f}%)")
        if ou_t: log(f"  📊 O/U:       {ou_c}/{ou_t} ({ou_c/ou_t*100:.1f}%)")
        
        # Save summaries per product
        if ml_t:
            save_daily_summary(game_date, sport, f"{sport}_engine", 
                             {"ml": stats["ml"], "spread": stats["spread"], "ou": [0,0]}, conn)
        if ou_t:
            save_daily_summary(game_date, sport, f"{sport}_ou",
                             {"ml": [0,0], "spread": [0,0], "ou": stats["ou"]}, conn)
    
    # Grand total
    log("\n" + "=" * 55)
    log("📋 GRAND TOTAL")
    log("=" * 55)
    
    g_ml = [sum(s["ml"][i] for s in all_stats.values()) for i in range(2)]
    g_sp = [sum(s["spread"][i] for s in all_stats.values()) for i in range(2)]
    g_ou = [sum(s["ou"][i] for s in all_stats.values()) for i in range(2)]
    
    if g_ml[1]: log(f"🎯 Moneyline: {g_ml[0]}/{g_ml[1]} ({g_ml[0]/g_ml[1]*100:.1f}%)")
    if g_sp[1]: log(f"📐 Spread:    {g_sp[0]}/{g_sp[1]} ({g_sp[0]/g_sp[1]*100:.1f}%)")
    if g_ou[1]: log(f"📊 O/U:       {g_ou[0]}/{g_ou[1]} ({g_ou[0]/g_ou[1]*100:.1f}%)")
    
    total_c = g_ml[0] + g_sp[0] + g_ou[0]
    total_t = g_ml[1] + g_sp[1] + g_ou[1]
    if total_t:
        log(f"\n🏆 Overall:   {total_c}/{total_t} ({total_c/total_t*100:.1f}%)")
    
    conn.close()
    return "\n".join(output_lines)


def main():
    parser = argparse.ArgumentParser(description='ParlayGuarantee Result Tracker v2')
    parser.add_argument('--date', type=str, default=None, help='YYYY-MM-DD (default: yesterday)')
    parser.add_argument('--sport', type=str, default='all', help='all, nba, ncaab, nhl')
    args = parser.parse_args()
    
    game_date = args.date or (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    if args.sport == 'all':
        sports = ["nba", "ncaab"]  # NHL/MMA added when ready
    else:
        sports = [args.sport.lower()]
    
    run(game_date, sports)


if __name__ == '__main__':
    main()
