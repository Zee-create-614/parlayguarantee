#!/usr/bin/env python3
"""
ParlayGuarantee Pool Generator
Generates all unique parlay combinations and stores them in Turso.
Usage: python parlay_pool_generator.py [--date YYYY-MM-DD] [--run 1|2|3]
"""

import argparse
import itertools
import json
import os
import random
import sys
from datetime import datetime, timezone
from math import comb as nCr
from pathlib import Path

import requests

# ─── Config ───

ODDS_API_BASE = "https://api.the-odds-api.com/v4/sports"
SPORTS = {
    "nba": "basketball_nba",
    "ncaab": "basketball_ncaab",
}
MAX_PER_TIER = 10_000
MAX_MIXED_PER_TIER = 50_000
SAMPLE_THRESHOLD_LEGS = 8

TURSO_URL = "libsql://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io"
TURSO_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9."
    "eyJhIjoicnciLCJpYXQiOjE3NzE3NjQxNzcsImlkIjoiNWZlOTIyMzgtM2RlNC00YzEyLTg1NmMtYWNiNjk0ZjkxNTY2Iiwicm"
    "lkIjoiZDBhNzE4NzYtNjg5MS00YWE3LThkZGQtZGU0MWM4N2ZjNGZlIn0."
    "tQhQ9DdNqnkIP0rEz0jbOPNhNWTjz4SOcElzp5PGngDPneus0dfp9qvm6GMu7TqMGO8zPH_k_kJFvNP1h3TRBA"
)


def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        raw = env_path.read_bytes()
        try:
            text = raw.decode("utf-16")
        except (UnicodeDecodeError, UnicodeError):
            text = raw.decode("utf-8-sig", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_odds_api_key():
    load_env()
    key = os.environ.get("THE_ODDS_API_KEY", "")
    if not key:
        print("ERROR: THE_ODDS_API_KEY not set")
        sys.exit(1)
    return key


# ─── Odds API ───

def american_to_prob(odds: int) -> float:
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)


def fetch_games(sport_key: str, api_key: str) -> list[dict]:
    """Fetch games and extract picks from Odds API."""
    url = f"{ODDS_API_BASE}/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "markets": "h2h,spreads",
        "regions": "us",
        "oddsFormat": "american",
        "bookmakers": "fanduel",
    }
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        # Retry without bookmaker filter
        del params["bookmakers"]
        resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"  Odds API error {resp.status_code} for {sport_key}: {resp.text[:200]}")
        return []

    games = []
    for event in resp.json():
        if not event.get("bookmakers"):
            continue
        book = event["bookmakers"][0]  # fanduel or first available
        markets = {m["key"]: m for m in book.get("markets", [])}

        game_info = {
            "game_id": event["id"],
            "home_team": event["home_team"],
            "away_team": event["away_team"],
            "commence_time": event["commence_time"],
            "sport": sport_key,
        }

        ml_pick = None
        spread_pick = None

        # Moneyline - pick the favorite (more negative odds)
        h2h = markets.get("h2h")
        if h2h:
            outcomes = {o["name"]: o["price"] for o in h2h["outcomes"]}
            if len(outcomes) >= 2:
                fav = min(outcomes, key=lambda t: outcomes[t])
                opp = [t for t in outcomes if t != fav][0]
                odds_val = outcomes[fav]
                ml_pick = {
                    **game_info,
                    "bet_type": "moneyline",
                    "team": fav,
                    "opponent": opp,
                    "line": None,
                    "odds": odds_val,
                    "prob": american_to_prob(odds_val),
                }

        # Spread - pick the favorite (negative spread)
        spreads = markets.get("spreads")
        if spreads:
            outcomes = {o["name"]: (o["point"], o["price"]) for o in spreads["outcomes"]}
            if len(outcomes) >= 2:
                fav = min(outcomes, key=lambda t: outcomes[t][0])
                opp = [t for t in outcomes if t != fav][0]
                point, odds_val = outcomes[fav]
                spread_pick = {
                    **game_info,
                    "bet_type": "spread",
                    "team": fav,
                    "opponent": opp,
                    "line": point,
                    "odds": odds_val,
                    "prob": american_to_prob(odds_val),
                }

        if ml_pick or spread_pick:
            games.append({"ml": ml_pick, "spread": spread_pick, "info": game_info})

    return games


# ─── Parlay Generation ───

def make_parlay_record(legs: list[dict], date_str: str, sport_cat: str, bet_type: str, run: int) -> dict:
    combined_prob = 1.0
    for leg in legs:
        combined_prob *= leg["prob"]
    payout = (100 / combined_prob) if combined_prob > 0 else 0

    picks = []
    for leg in legs:
        picks.append({
            "team": leg["team"],
            "opponent": leg["opponent"],
            "line": leg.get("line"),
            "odds": leg["odds"],
            "sport": leg["sport"],
            "bet_type": leg["bet_type"],
            "game_id": leg["game_id"],
        })

    return {
        "date": date_str,
        "sport_category": sport_cat,
        "bet_type": bet_type,
        "leg_count": len(legs),
        "combined_prob": combined_prob,
        "implied_payout_per_100": round(payout, 2),
        "picks_json": json.dumps(picks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_run": run,
    }


def generate_single_type_parlays(picks: list[dict], date_str: str, sport_cat: str, bet_type: str, run: int) -> list[dict]:
    """Generate parlays for a single bet type (moneyline or spread)."""
    if len(picks) < 2:
        return []
    
    records = []
    for leg_count in range(2, len(picks) + 1):
        total_combos = nCr(len(picks), leg_count)
        if leg_count >= SAMPLE_THRESHOLD_LEGS or total_combos > MAX_PER_TIER:
            # Sample randomly
            sample_size = min(MAX_PER_TIER, total_combos)
            if total_combos <= MAX_PER_TIER * 2:
                # Generate all then sample
                all_combos = list(itertools.combinations(picks, leg_count))
                chosen = random.sample(all_combos, sample_size)
            else:
                # Random index sampling
                chosen = set()
                indices = list(range(len(picks)))
                while len(chosen) < sample_size:
                    combo = tuple(sorted(random.sample(indices, leg_count)))
                    if combo not in chosen:
                        chosen.add(combo)
                chosen = [tuple(picks[i] for i in c) for c in chosen]
            for combo in chosen:
                records.append(make_parlay_record(list(combo), date_str, sport_cat, bet_type, run))
        else:
            for combo in itertools.combinations(picks, leg_count):
                records.append(make_parlay_record(list(combo), date_str, sport_cat, bet_type, run))
    return records


def generate_mixed_parlays(games: list[dict], date_str: str, sport_cat: str, run: int) -> list[dict]:
    """Generate mixed parlays where each leg can be ML or spread, with at least 1 of each."""
    # Only use games that have both ML and spread picks
    eligible = [g for g in games if g["ml"] and g["spread"]]
    if len(eligible) < 2:
        return []

    records = []
    for leg_count in range(2, len(eligible) + 1):
        # For each combination of games, enumerate ML/spread assignments
        game_combos = list(itertools.combinations(range(len(eligible)), leg_count))
        
        # Check if we need to sample at game combo level
        # Each game combo produces 2^N - 2 mixed variations
        variations_per = (2 ** leg_count) - 2
        total_estimate = len(game_combos) * variations_per
        
        if leg_count >= SAMPLE_THRESHOLD_LEGS or total_estimate > MAX_MIXED_PER_TIER:
            # Sample approach
            target = min(MAX_PER_TIER, total_estimate)
            sampled = []
            attempts = 0
            seen = set()
            while len(sampled) < target and attempts < target * 5:
                attempts += 1
                gc = random.choice(game_combos)
                # Random bitmask (0=ML, 1=spread), exclude all-0 and all-1
                mask = random.randint(1, (2 ** leg_count) - 2)
                key = (gc, mask)
                if key in seen:
                    continue
                seen.add(key)
                legs = []
                for i, gi in enumerate(gc):
                    g = eligible[gi]
                    legs.append(g["spread"] if (mask >> i) & 1 else g["ml"])
                sampled.append(make_parlay_record(legs, date_str, sport_cat, "mixed", run))
            records.extend(sampled)
        else:
            for gc in game_combos:
                # Generate all bitmasks except all-0 (all ML) and all-1 (all spread)
                for mask in range(1, (2 ** leg_count) - 1):
                    legs = []
                    for i, gi in enumerate(gc):
                        g = eligible[gi]
                        legs.append(g["spread"] if (mask >> i) & 1 else g["ml"])
                    records.append(make_parlay_record(legs, date_str, sport_cat, "mixed", run))
    return records


def generate_cross_sport_parlays(nba_games: list[dict], ncaab_games: list[dict], date_str: str, run: int) -> list[dict]:
    """Generate cross-sport parlays with at least 1 game from each sport."""
    all_games = nba_games + ncaab_games
    nba_set = set(range(len(nba_games)))
    ncaab_set = set(range(len(nba_games), len(all_games)))
    
    if not nba_games or not ncaab_games:
        return []

    records = []
    
    for bet_type in ["moneyline", "spread"]:
        pick_key = "ml" if bet_type == "moneyline" else "spread"
        picks_with_idx = [(i, g[pick_key]) for i, g in enumerate(all_games) if g[pick_key]]
        if len(picks_with_idx) < 2:
            continue

        for leg_count in range(2, min(len(picks_with_idx) + 1, 13)):  # cap cross-sport
            total_combos = nCr(len(picks_with_idx), leg_count)
            
            if leg_count >= SAMPLE_THRESHOLD_LEGS or total_combos > MAX_PER_TIER * 2:
                target = min(MAX_PER_TIER, total_combos)
                sampled = []
                attempts = 0
                indices = list(range(len(picks_with_idx)))
                seen = set()
                while len(sampled) < target and attempts < target * 5:
                    attempts += 1
                    combo_idx = tuple(sorted(random.sample(indices, leg_count)))
                    if combo_idx in seen:
                        continue
                    seen.add(combo_idx)
                    combo = [picks_with_idx[i] for i in combo_idx]
                    game_indices = {c[0] for c in combo}
                    if not (game_indices & nba_set) or not (game_indices & ncaab_set):
                        continue
                    legs = [c[1] for c in combo]
                    sampled.append(make_parlay_record(legs, date_str, "nba_ncaab", bet_type, run))
                records.extend(sampled)
            else:
                for combo in itertools.combinations(picks_with_idx, leg_count):
                    game_indices = {c[0] for c in combo}
                    if not (game_indices & nba_set) or not (game_indices & ncaab_set):
                        continue
                    legs = [c[1] for c in combo]
                    records.append(make_parlay_record(legs, date_str, "nba_ncaab", bet_type, run))
    
    # Mixed cross-sport
    eligible = [(i, g) for i, g in enumerate(all_games) if g["ml"] and g["spread"]]
    if len(eligible) >= 2:
        for leg_count in range(2, min(len(eligible) + 1, 10)):
            game_combos = list(itertools.combinations(range(len(eligible)), leg_count))
            variations_per = (2 ** leg_count) - 2
            total_estimate = len(game_combos) * variations_per
            target = min(MAX_PER_TIER, total_estimate)
            
            if leg_count >= SAMPLE_THRESHOLD_LEGS or total_estimate > MAX_PER_TIER:
                sampled = []
                attempts = 0
                seen = set()
                while len(sampled) < target and attempts < target * 5:
                    attempts += 1
                    gc = random.choice(game_combos)
                    mask = random.randint(1, (2 ** leg_count) - 2)
                    key = (gc, mask)
                    if key in seen:
                        continue
                    seen.add(key)
                    real_indices = {eligible[gi][0] for gi in gc}
                    if not (real_indices & nba_set) or not (real_indices & ncaab_set):
                        continue
                    legs = []
                    for i, gi in enumerate(gc):
                        g = eligible[gi][1]
                        legs.append(g["spread"] if (mask >> i) & 1 else g["ml"])
                    sampled.append(make_parlay_record(legs, date_str, "nba_ncaab", "mixed", run))
                records.extend(sampled)
            else:
                for gc in game_combos:
                    real_indices = {eligible[gi][0] for gi in gc}
                    if not (real_indices & nba_set) or not (real_indices & ncaab_set):
                        continue
                    for mask in range(1, (2 ** leg_count) - 1):
                        legs = []
                        for i, gi in enumerate(gc):
                            g = eligible[gi][1]
                            legs.append(g["spread"] if (mask >> i) & 1 else g["ml"])
                        records.append(make_parlay_record(legs, date_str, "nba_ncaab", "mixed", run))

    return records


# ─── Database (Turso HTTP API) ───

class TursoClient:
    """Simple sync client for Turso using the HTTP pipeline API."""

    def __init__(self, url: str, token: str):
        # Convert libsql:// to https://
        self.base_url = url.replace("libsql://", "https://")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def execute(self, sql: str, args: list | None = None):
        """Execute a single statement."""
        stmt: dict = {"type": "execute", "stmt": {"sql": sql}}
        if args:
            stmt["stmt"]["args"] = [self._encode_arg(a) for a in args]
        body = {"requests": [stmt, {"type": "close"}]}
        resp = requests.post(f"{self.base_url}/v2/pipeline", json=body, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def execute_batch(self, statements: list[tuple[str, list]]):
        """Execute multiple statements in a pipeline."""
        reqs = []
        for sql, args in statements:
            stmt: dict = {"type": "execute", "stmt": {"sql": sql}}
            if args:
                stmt["stmt"]["args"] = [self._encode_arg(a) for a in args]
            reqs.append(stmt)
        reqs.append({"type": "close"})
        resp = requests.post(f"{self.base_url}/v2/pipeline", json={"requests": reqs}, headers=self.headers, timeout=60)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _encode_arg(val):
        if val is None:
            return {"type": "null", "value": None}
        elif isinstance(val, int):
            return {"type": "integer", "value": str(val)}
        elif isinstance(val, float):
            return {"type": "float", "value": val}
        elif isinstance(val, str):
            return {"type": "text", "value": val}
        else:
            return {"type": "text", "value": str(val)}


def init_db(db: TursoClient):
    db.execute_batch([
        ("""CREATE TABLE IF NOT EXISTS parlay_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            sport_category TEXT NOT NULL,
            bet_type TEXT NOT NULL,
            leg_count INTEGER NOT NULL,
            combined_prob REAL,
            implied_payout_per_100 REAL,
            picks_json TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            generation_run INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1
        )""", []),
        ("CREATE INDEX IF NOT EXISTS idx_pool_lookup ON parlay_pool(date, sport_category, bet_type, leg_count, is_active)", []),
        ("""CREATE TABLE IF NOT EXISTS dealt_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            pool_id INTEGER NOT NULL,
            dealt_at TEXT NOT NULL,
            payment_intent TEXT,
            FOREIGN KEY (pool_id) REFERENCES parlay_pool(id)
        )""", []),
        ("CREATE INDEX IF NOT EXISTS idx_dealt_user ON dealt_tickets(user_id, pool_id)", []),
    ])


def insert_parlays(db: TursoClient, records: list[dict], date_str: str, run: int):
    # Deactivate previous runs
    db.execute_batch([
        ("UPDATE parlay_pool SET is_active = 0 WHERE date = ? AND generation_run < ?", [date_str, run]),
        ("UPDATE parlay_pool SET is_active = 0 WHERE date < ?", [date_str]),
    ])

    # Batch insert (pipeline max ~100 statements at a time for safety)
    batch_size = 90
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        stmts = []
        for r in batch:
            stmts.append((
                """INSERT INTO parlay_pool 
                   (date, sport_category, bet_type, leg_count, combined_prob, 
                    implied_payout_per_100, picks_json, generated_at, generation_run, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                [
                    r["date"], r["sport_category"], r["bet_type"], r["leg_count"],
                    r["combined_prob"], r["implied_payout_per_100"], r["picks_json"],
                    r["generated_at"], r["generation_run"],
                ],
            ))
        db.execute_batch(stmts)
        print(f"  Inserted batch {i // batch_size + 1} ({len(batch)} records)")


# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description="Generate parlay pool")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Date YYYY-MM-DD")
    parser.add_argument("--run", type=int, default=1, choices=[1, 2, 3], help="Generation run (1=10am, 2=2pm, 3=4pm)")
    args = parser.parse_args()

    date_str = args.date
    run = args.run
    api_key = get_odds_api_key()

    print(f"=== ParlayGuarantee Pool Generator ===")
    print(f"Date: {date_str} | Run: {run}")
    print()

    # Fetch games
    print("Fetching NBA games...")
    nba_games = fetch_games("basketball_nba", api_key)
    print(f"  Found {len(nba_games)} NBA games with odds")

    print("Fetching NCAAB games...")
    ncaab_games = fetch_games("basketball_ncaab", api_key)
    print(f"  Found {len(ncaab_games)} NCAAB games with odds")
    print()

    all_records = []
    summary = {}

    # NBA parlays
    if len(nba_games) >= 2:
        nba_ml = [g["ml"] for g in nba_games if g["ml"]]
        nba_sp = [g["spread"] for g in nba_games if g["spread"]]

        ml_recs = generate_single_type_parlays(nba_ml, date_str, "nba", "moneyline", run)
        summary["nba_moneyline"] = len(ml_recs)
        all_records.extend(ml_recs)

        sp_recs = generate_single_type_parlays(nba_sp, date_str, "nba", "spread", run)
        summary["nba_spread"] = len(sp_recs)
        all_records.extend(sp_recs)

        mx_recs = generate_mixed_parlays(nba_games, date_str, "nba", run)
        summary["nba_mixed"] = len(mx_recs)
        all_records.extend(mx_recs)

    # NCAAB parlays
    if len(ncaab_games) >= 2:
        ncaab_ml = [g["ml"] for g in ncaab_games if g["ml"]]
        ncaab_sp = [g["spread"] for g in ncaab_games if g["spread"]]

        ml_recs = generate_single_type_parlays(ncaab_ml, date_str, "ncaab", "moneyline", run)
        summary["ncaab_moneyline"] = len(ml_recs)
        all_records.extend(ml_recs)

        sp_recs = generate_single_type_parlays(ncaab_sp, date_str, "ncaab", "spread", run)
        summary["ncaab_spread"] = len(sp_recs)
        all_records.extend(sp_recs)

        mx_recs = generate_mixed_parlays(ncaab_games, date_str, "ncaab", run)
        summary["ncaab_mixed"] = len(mx_recs)
        all_records.extend(mx_recs)

    # Cross-sport
    if nba_games and ncaab_games:
        cross_recs = generate_cross_sport_parlays(nba_games, ncaab_games, date_str, run)
        summary["nba_ncaab_total"] = len(cross_recs)
        all_records.extend(cross_recs)

    print("=== Generation Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v:,} parlays")
    print(f"  TOTAL: {len(all_records):,} parlays")
    print()

    if not all_records:
        print("No parlays generated. Check if games are available.")
        return

    # Connect to Turso and insert
    print("Connecting to Turso...")
    db = TursoClient(TURSO_URL, TURSO_TOKEN)

    print("Initializing schema...")
    init_db(db)

    print(f"Inserting {len(all_records):,} parlays...")
    insert_parlays(db, all_records, date_str, run)

    print()
    print("✅ Done! Pool generation complete.")


if __name__ == "__main__":
    main()
