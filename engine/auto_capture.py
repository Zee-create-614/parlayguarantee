#!/usr/bin/env python3
"""
AUTO_CAPTURE.py — Automatically capture or cancel Stripe payment holds after results
====================================================================================
Runs after games finish. For each requires_capture payment intent:
  - Parse parlay legs from Stripe metadata
  - Fetch actual scores from Odds API
  - Score each leg
  - ALL legs hit → capture payment (we earned it)
  - ANY leg lost → cancel hold (refund per guarantee)
  - Games still pending → skip (check next run)

Usage:
  python auto_capture.py              # Process all pending holds
  python auto_capture.py --dry-run    # Show what would happen without acting
  python auto_capture.py --verbose    # Extra logging

Designed to run as a cron job ~1hr after last game tips off.
"""

import json, os, sys, time, requests, logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── Config ───────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
ODDS_API_KEY = "f3c9f91dc369f56dea1b523d3071e1f1"
TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "libsql://parlayguarantee-parlayguarantee.aws-us-east-2.turso.io").strip()
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()

ENGINE_DIR = Path(__file__).parent
EST = timezone(timedelta(hours=-5))
DRY_RUN = "--dry-run" in sys.argv
VERBOSE = "--verbose" in sys.argv

logging.basicConfig(
    level=logging.DEBUG if VERBOSE else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(ENGINE_DIR / "auto_capture.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("auto_capture")

# ─── Load Stripe key from .env if not in environment ─────────────────
def load_env():
    global STRIPE_SECRET_KEY, TURSO_TOKEN
    env_files = [
        ENGINE_DIR.parent / ".env.local",
        ENGINE_DIR.parent / ".env",
        ENGINE_DIR / ".env",
    ]
    for ef in env_files:
        if ef.exists():
            for line in ef.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "STRIPE_SECRET_KEY" and not STRIPE_SECRET_KEY:
                        STRIPE_SECRET_KEY = v
                    elif k == "TURSO_AUTH_TOKEN" and not TURSO_TOKEN:
                        TURSO_TOKEN = v

load_env()

if not STRIPE_SECRET_KEY:
    log.warning("⚠️ STRIPE_SECRET_KEY not found — auto-capture disabled.")
    def process_holds():
        return None

# ─── Stripe helpers ───────────────────────────────────────────────────
STRIPE_BASE = "https://api.stripe.com/v1"
STRIPE_HEADERS = {"Authorization": f"Bearer {STRIPE_SECRET_KEY}"}

def stripe_get(endpoint, params=None):
    r = requests.get(f"{STRIPE_BASE}/{endpoint}", headers=STRIPE_HEADERS, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def stripe_post(endpoint, data=None):
    r = requests.post(f"{STRIPE_BASE}/{endpoint}", headers=STRIPE_HEADERS, data=data or {}, timeout=30)
    r.raise_for_status()
    return r.json()

def get_pending_holds():
    """Fetch all payment intents with requires_capture status."""
    all_holds = []
    params = {"limit": 100}
    has_more = True
    while has_more:
        result = stripe_get("payment_intents", {**params, "expand[]": ""})
        for pi in result.get("data", []):
            if pi["status"] == "requires_capture":
                meta = pi.get("metadata", {})
                if meta.get("type") == "parlayguarantee_parlay":
                    all_holds.append(pi)
        has_more = result.get("has_more", False)
        if has_more and result["data"]:
            params["starting_after"] = result["data"][-1]["id"]
    return all_holds

def capture_payment(pi_id):
    """Capture an authorized payment."""
    if DRY_RUN:
        log.info(f"  [DRY RUN] Would CAPTURE {pi_id}")
        return {"id": pi_id, "status": "dry_run_capture"}
    return stripe_post(f"payment_intents/{pi_id}/capture")

def cancel_payment(pi_id):
    """Cancel (release hold) on an authorized payment."""
    if DRY_RUN:
        log.info(f"  [DRY RUN] Would CANCEL {pi_id}")
        return {"id": pi_id, "status": "dry_run_cancel"}
    return stripe_post(f"payment_intents/{pi_id}/cancel")

# ─── Turso helpers ────────────────────────────────────────────────────
def turso_exec(sql, args=None):
    """Execute SQL against Turso."""
    if not TURSO_TOKEN:
        return None
    url = TURSO_URL.replace("libsql://", "https://")
    body = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [{"type": "text", "value": str(a)} for a in (args or [])]}}
        ]
    }
    try:
        r = requests.post(url, json=body, headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json",
        }, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Turso error: {e}")
        return None

# ─── Score fetching ───────────────────────────────────────────────────
_scores_cache = {}

def fetch_all_scores():
    """Fetch completed game scores from Odds API."""
    if _scores_cache:
        return _scores_cache
    
    for sport_key in ["basketball_nba", "basketball_ncaab"]:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/"
        params = {"apiKey": ODDS_API_KEY, "daysFrom": 3, "dateFormat": "iso"}
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            for game in data:
                home = game["home_team"]
                away = game["away_team"]
                completed = game.get("completed", False)
                hs = as_ = None
                for s in game.get("scores", []):
                    if s["name"] == home:
                        hs = int(s["score"])
                    elif s["name"] == away:
                        as_ = int(s["score"])
                
                entry = {
                    "home": home, "away": away,
                    "home_score": hs, "away_score": as_,
                    "completed": completed,
                    "sport": sport_key,
                }
                if completed and hs is not None and as_ is not None:
                    entry["total"] = hs + as_
                    entry["winner"] = home if hs > as_ else away
                    entry["margin"] = hs - as_
                
                _scores_cache[home] = entry
                _scores_cache[away] = entry
                # Also store normalized keys
                _scores_cache[home.lower()] = entry
                _scores_cache[away.lower()] = entry
        except Exception as e:
            log.error(f"Error fetching scores for {sport_key}: {e}")
    
    log.info(f"Loaded scores for {len(set(id(v) for v in _scores_cache.values()))} games")
    return _scores_cache

# ─── Team name fuzzy matching ────────────────────────────────────────
def find_game(team_name, scores):
    """Find a game result by team name (fuzzy)."""
    if not team_name:
        return None
    # Direct match
    if team_name in scores:
        return scores[team_name]
    if team_name.lower() in scores:
        return scores[team_name.lower()]
    # Partial match
    tl = team_name.lower()
    for key, val in scores.items():
        if isinstance(key, str) and (tl in key.lower() or key.lower() in tl):
            return val
    return None

# ─── Leg scoring ─────────────────────────────────────────────────────
def score_leg(leg, scores):
    """
    Score a single parlay leg.
    Returns: 'hit', 'miss', 'push', or 'pending'
    """
    team = leg.get("team", "")
    bet = leg.get("bet", "")
    
    result = find_game(team, scores)
    if not result:
        return "pending", f"No result for {team}"
    if not result.get("completed"):
        return "pending", f"Game not complete: {team}"
    
    home = result["home"]
    away = result["away"]
    hs = result["home_score"]
    as_ = result["away_score"]
    margin = result["margin"]  # home - away
    total = result["total"]
    winner = result["winner"]
    
    bet_lower = bet.lower()
    
    # Moneyline bet
    if "ml" in bet_lower or "moneyline" in bet_lower or "to win" in bet_lower:
        pick_team = team
        if pick_team == winner:
            return "hit", f"{pick_team} won ({hs}-{as_})"
        else:
            return "miss", f"{pick_team} lost ({hs}-{as_})"
    
    # Spread bet: parse spread value from bet string
    # Formats: "Team -3.5", "-3.5", "+5.5", "spread -3.5"
    import re
    spread_match = re.search(r'([+-]?\d+\.?\d*)', bet)
    if spread_match and ("spread" in bet_lower or "ats" in bet_lower or re.match(r'^[+-]?\d', bet.strip())):
        spread = float(spread_match.group(1))
        # Determine if our pick is home or away
        team_lower = team.lower()
        if team_lower == home.lower() or home.lower() in team_lower or team_lower in home.lower():
            adjusted = margin + spread  # home margin + spread
        elif team_lower == away.lower() or away.lower() in team_lower or team_lower in away.lower():
            adjusted = -margin + spread  # away margin + spread
        else:
            # Try to match
            adjusted = None
        
        if adjusted is not None:
            if adjusted > 0:
                return "hit", f"{team} {bet} covered (margin: {margin})"
            elif adjusted == 0:
                return "push", f"{team} {bet} push (margin: {margin})"
            else:
                return "miss", f"{team} {bet} didn't cover (margin: {margin})"
    
    # Over/Under
    if "over" in bet_lower or "under" in bet_lower:
        line_match = re.search(r'(\d+\.?\d*)', bet)
        if line_match:
            line = float(line_match.group(1))
            if "over" in bet_lower:
                if total > line:
                    return "hit", f"Over {line} hit (total: {total})"
                elif total == line:
                    return "push", f"Over {line} push (total: {total})"
                else:
                    return "miss", f"Over {line} missed (total: {total})"
            else:
                if total < line:
                    return "hit", f"Under {line} hit (total: {total})"
                elif total == line:
                    return "push", f"Under {line} push (total: {total})"
                else:
                    return "miss", f"Under {line} missed (total: {total})"
    
    # Fallback: treat as moneyline if we can match the team
    if team.lower() == winner.lower() or winner.lower() in team.lower() or team.lower() in winner.lower():
        return "hit", f"{team} won ({hs}-{as_}) [inferred ML]"
    elif result.get("completed"):
        loser = away if winner == home else home
        if team.lower() == loser.lower() or loser.lower() in team.lower() or team.lower() in loser.lower():
            return "miss", f"{team} lost ({hs}-{as_}) [inferred ML]"
    
    return "pending", f"Could not score leg: {team} / {bet}"

# ─── Main processing ─────────────────────────────────────────────────
def process_holds():
    log.info("=" * 60)
    log.info(f"AUTO CAPTURE — {datetime.now(EST).strftime('%Y-%m-%d %H:%M EST')}")
    log.info(f"Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
    log.info("=" * 60)
    
    # 1. Get all pending holds
    log.info("Fetching requires_capture payment intents from Stripe...")
    holds = get_pending_holds()
    log.info(f"Found {len(holds)} pending holds")
    
    if not holds:
        log.info("✅ No pending holds. Nothing to do.")
        return {"captured": 0, "cancelled": 0, "pending": 0, "errors": 0}
    
    # 2. Fetch scores
    scores = fetch_all_scores()
    
    stats = {"captured": 0, "cancelled": 0, "pending": 0, "errors": 0}
    results_log = []
    
    for pi in holds:
        pi_id = pi["id"]
        meta = pi.get("metadata", {})
        email = meta.get("email", "unknown")
        tier = meta.get("tier", "unknown")
        amount = pi["amount"] / 100  # cents to dollars
        created = datetime.fromtimestamp(pi["created"], tz=EST).strftime("%Y-%m-%d %H:%M")
        
        log.info(f"\n{'─' * 50}")
        log.info(f"Payment: {pi_id}")
        log.info(f"  Email: {email} | Tier: {tier} | Amount: ${amount:.2f} | Created: {created}")
        
        # Parse parlay legs from metadata
        parlay_data = meta.get("parlay_data", "{}")
        try:
            parlay = json.loads(parlay_data)
        except:
            log.warning(f"  ⚠️ Could not parse parlay_data for {pi_id}")
            stats["errors"] += 1
            continue
        
        legs = parlay.get("legs", [])
        if not legs:
            log.warning(f"  ⚠️ No legs found in parlay_data for {pi_id}")
            stats["errors"] += 1
            continue
        
        log.info(f"  Legs ({len(legs)}):")
        
        # 3. Score each leg
        leg_results = []
        for i, leg in enumerate(legs):
            team = leg.get("team", "?")
            bet = leg.get("bet", "?")
            odds = leg.get("odds", "?")
            status, detail = score_leg(leg, scores)
            leg_results.append({"status": status, "detail": detail, "team": team, "bet": bet})
            
            icon = {"hit": "✅", "miss": "❌", "push": "🟡", "pending": "⏳"}.get(status, "❓")
            log.info(f"    {icon} Leg {i+1}: {team} ({bet}) → {status} — {detail}")
        
        # 4. Determine action
        statuses = [lr["status"] for lr in leg_results]
        
        if "pending" in statuses:
            # Some games haven't finished yet — skip
            log.info(f"  ⏳ SKIP — {statuses.count('pending')} leg(s) still pending")
            stats["pending"] += 1
            results_log.append({"pi": pi_id, "action": "pending", "email": email, "amount": amount})
            
            # Check if hold is about to expire (7 days for Stripe)
            age_hours = (time.time() - pi["created"]) / 3600
            if age_hours > 144:  # 6 days
                log.warning(f"  ⚠️ Hold is {age_hours:.0f}h old! Expires at 168h. Force-score or cancel soon.")
            continue
        
        any_miss = "miss" in statuses
        all_hit = all(s in ("hit", "push") for s in statuses)
        
        if any_miss:
            # Guarantee triggered — cancel hold (full refund)
            log.info(f"  ❌ CANCEL — {statuses.count('miss')} leg(s) lost. Refunding ${amount:.2f}")
            try:
                result = cancel_payment(pi_id)
                stats["cancelled"] += 1
                results_log.append({"pi": pi_id, "action": "cancelled", "email": email, "amount": amount})
                # Update Turso
                turso_exec(
                    "UPDATE purchases SET status = 'refunded' WHERE payment_intent_id = ?",
                    [pi_id]
                )
            except Exception as e:
                log.error(f"  ❌ Error cancelling {pi_id}: {e}")
                stats["errors"] += 1
        
        elif all_hit:
            # All legs hit — capture payment
            log.info(f"  💰 CAPTURE — All {len(legs)} legs hit! Capturing ${amount:.2f}")
            try:
                result = capture_payment(pi_id)
                stats["captured"] += 1
                results_log.append({"pi": pi_id, "action": "captured", "email": email, "amount": amount})
                # Update Turso
                turso_exec(
                    "UPDATE purchases SET status = 'captured' WHERE payment_intent_id = ?",
                    [pi_id]
                )
            except Exception as e:
                log.error(f"  ❌ Error capturing {pi_id}: {e}")
                stats["errors"] += 1
    
    # 5. Summary
    log.info(f"\n{'=' * 60}")
    log.info(f"SUMMARY")
    log.info(f"  💰 Captured: {stats['captured']}")
    log.info(f"  ❌ Cancelled (refunded): {stats['cancelled']}")
    log.info(f"  ⏳ Still pending: {stats['pending']}")
    log.info(f"  ⚠️ Errors: {stats['errors']}")
    
    captured_total = sum(r["amount"] for r in results_log if r["action"] == "captured")
    cancelled_total = sum(r["amount"] for r in results_log if r["action"] == "cancelled")
    log.info(f"  Revenue captured: ${captured_total:.2f}")
    log.info(f"  Holds released: ${cancelled_total:.2f}")
    log.info("=" * 60)
    
    # Save results log
    log_file = ENGINE_DIR / f"capture_results_{datetime.now(EST).strftime('%Y-%m-%d')}.json"
    with open(log_file, "w") as f:
        json.dump({"timestamp": datetime.now(EST).isoformat(), "stats": stats, "results": results_log}, f, indent=2)
    log.info(f"Results saved to {log_file}")
    
    return stats

if __name__ == "__main__":
    process_holds()
