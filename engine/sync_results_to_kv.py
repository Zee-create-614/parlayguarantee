"""
Sync results.db → Upstash Redis KV
Pushes pick results and daily summaries so the Vercel dashboard can read them.

Usage:
    python sync_results_to_kv.py              # sync all results
    python sync_results_to_kv.py --date 2026-02-20  # sync specific date

KV Keys:
    results:picks:{date}:{product}   → list of pick results
    results:summary:{date}:{product} → daily summary
    results:dates                    → sorted set of all dates with results
    results:latest                   → latest sync metadata
"""

import sys
import os
import json
import sqlite3
import argparse
import requests
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path(__file__).parent / "results.db"

# Load env from .env.production.local or environment
def load_upstash_creds():
    url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    
    if not url or not token:
        # Try loading from .env.production.local
        env_file = Path(__file__).parent.parent / ".env.production.local"
        if env_file.exists():
            import re
            content = env_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("UPSTASH_REDIS_REST_URL="):
                    url = re.sub(r'[\\]r[\\]n|\\r|\\n|\r|\n', '', line.split("=", 1)[1]).strip().strip('"').strip()
                elif line.startswith("UPSTASH_REDIS_REST_TOKEN="):
                    token = re.sub(r'[\\]r[\\]n|\\r|\\n|\r|\n', '', line.split("=", 1)[1]).strip().strip('"').strip()
    
    if not url or not token:
        raise ValueError("UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN required")
    
    return url, token


class UpstashKV:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def set(self, key: str, value: any, ex: int = None):
        data = json.dumps(value)
        cmd = ["SET", key, data]
        if ex:
            cmd += ["EX", str(ex)]
        r = requests.post(f"{self.url}", headers=self.headers, json=cmd)
        r.raise_for_status()
        return r.json()
    
    def zadd(self, key: str, score: float, member: str):
        r = requests.post(f"{self.url}", headers=self.headers, json=["ZADD", key, str(score), member])
        r.raise_for_status()
        return r.json()
    
    def pipeline(self, commands: list):
        r = requests.post(f"{self.url}/pipeline", headers=self.headers, json=commands)
        r.raise_for_status()
        return r.json()


def get_results(db_path: Path, target_date: str = None):
    if not db_path.exists():
        print(f"No results.db at {db_path}")
        return [], []
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    if target_date:
        picks = conn.execute(
            "SELECT * FROM pick_results WHERE date = ? ORDER BY product, pick_number", (target_date,)
        ).fetchall()
        summaries = conn.execute(
            "SELECT * FROM daily_summaries WHERE date = ? ORDER BY product", (target_date,)
        ).fetchall()
    else:
        picks = conn.execute(
            "SELECT * FROM pick_results ORDER BY date DESC, product, pick_number"
        ).fetchall()
        summaries = conn.execute(
            "SELECT * FROM daily_summaries ORDER BY date DESC, product"
        ).fetchall()
    
    conn.close()
    return [dict(r) for r in picks], [dict(r) for r in summaries]


def sync(target_date: str = None):
    url, token = load_upstash_creds()
    kv = UpstashKV(url, token)
    
    picks, summaries = get_results(DB_PATH, target_date)
    
    if not picks and not summaries:
        print("No results to sync.")
        return
    
    # Group picks by date+product
    picks_by_key = {}
    for p in picks:
        key = f"{p['date']}:{p['product']}"
        picks_by_key.setdefault(key, []).append(p)
    
    # Build pipeline commands
    commands = []
    dates_seen = set()
    
    for key, pick_list in picks_by_key.items():
        date_str, product = key.split(":", 1)
        dates_seen.add(date_str)
        commands.append(["SET", f"results:picks:{date_str}:{product}", json.dumps(pick_list)])
    
    for s in summaries:
        date_str = s['date']
        product = s['product']
        dates_seen.add(date_str)
        commands.append(["SET", f"results:summary:{date_str}:{product}", json.dumps(s)])
    
    # Add dates to sorted set
    for d in dates_seen:
        ts = datetime.strptime(d, "%Y-%m-%d").timestamp()
        commands.append(["ZADD", "results:dates", str(ts), d])
    
    # Sync metadata
    commands.append(["SET", "results:latest", json.dumps({
        "syncedAt": datetime.now().isoformat(),
        "picksCount": len(picks),
        "summariesCount": len(summaries),
        "dates": sorted(dates_seen, reverse=True),
    })])
    
    # Also push a full export for the /api/results fallback
    all_picks, all_summaries = get_results(DB_PATH, None)
    export = {
        "pick_results": all_picks,
        "daily_summaries": all_summaries,
        "exported_at": datetime.now().isoformat(),
    }
    commands.append(["SET", "results:export", json.dumps(export)])
    
    # Execute pipeline in batches of 20
    total = len(commands)
    for i in range(0, total, 20):
        batch = commands[i:i+20]
        kv.pipeline(batch)
    
    print(f"✅ Synced {len(picks)} picks + {len(summaries)} summaries for {len(dates_seen)} date(s) to KV")
    print(f"   Dates: {', '.join(sorted(dates_seen, reverse=True))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Specific date to sync (YYYY-MM-DD)")
    args = parser.parse_args()
    sync(args.date)
