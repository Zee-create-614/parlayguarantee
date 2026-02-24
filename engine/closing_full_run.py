"""
CLOSING FULL RUN — 6:45 PM EST wrapper
Runs closing_snapshot.py + all new engines, saves everything with today's date.
"""
import sys, os, json, subprocess, importlib
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DIR = os.path.dirname(os.path.abspath(__file__))
DATE = datetime.now().strftime("%Y-%m-%d")
PYTHON = sys.executable


def run_script(label, args, check=True):
    """Run a Python script and return success bool."""
    print(f"\n{'='*60}")
    print(f"  STEP: {label}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(
            [PYTHON] + args,
            cwd=DIR, capture_output=False, text=True, timeout=120
        )
        if result.returncode != 0 and check:
            print(f"  WARNING: {label} exited with code {result.returncode}")
            return False
        return True
    except Exception as e:
        print(f"  ERROR in {label}: {e}")
        return False


def main():
    start = datetime.now()
    print(f"\n{'#'*60}")
    print(f"  CLOSING FULL RUN — {start.strftime('%I:%M %p EST')} — {DATE}")
    print(f"{'#'*60}")

    results = {}

    # 1. Closing snapshot (existing)
    ok = run_script("Closing Snapshot (lines + parlays)",
                    ["closing_snapshot.py"])
    results["closing_snapshot"] = ok

    # 2. Moneyline parlays — NBA
    nba_ml_out = os.path.join(DIR, f"moneyline_parlays_{DATE}_nba.json")
    ok = run_script("Moneyline Parlays — NBA",
                    ["moneyline_parlay.py", "--sport", "basketball_nba",
                     "--output", nba_ml_out])
    results["moneyline_nba"] = ok

    # 2b. Moneyline parlays — NCAAB
    ncaab_ml_out = os.path.join(DIR, f"moneyline_parlays_{DATE}_ncaab.json")
    ok = run_script("Moneyline Parlays — NCAAB",
                    ["moneyline_parlay.py", "--sport", "basketball_ncaab",
                     "--output", ncaab_ml_out])
    results["moneyline_ncaab"] = ok

    # Merge into single file
    try:
        combined = {"date": DATE, "generated_at": datetime.now().isoformat()}
        for label, path in [("nba", nba_ml_out), ("ncaab", ncaab_ml_out)]:
            if os.path.exists(path):
                with open(path) as f:
                    combined[label] = json.load(f)
        merged = os.path.join(DIR, f"moneyline_parlays_{DATE}.json")
        with open(merged, "w") as f:
            json.dump(combined, f, indent=2)
        print(f"  -> Merged: moneyline_parlays_{DATE}.json")
    except Exception as e:
        print(f"  Merge error: {e}")

    # 3. Player props — NBA
    props_out = os.path.join(DIR, f"player_props_{DATE}.json")
    ok = run_script("Player Props — NBA",
                    ["player_props.py", "--sport", "basketball_nba",
                     "--no-nba-api", "--output", props_out])
    results["player_props"] = ok

    # 4. SGP — NBA
    sgp_out = os.path.join(DIR, f"sgp_picks_{DATE}.json")
    ok = run_script("SGP — NBA",
                    ["sgp.py", "--sport", "basketball_nba",
                     "--no-nba-api", "--output", sgp_out])
    results["sgp"] = ok

    # 5. CLV Tracker — store opening odds
    ok = run_script("CLV Tracker — Store Opening Odds",
                    ["clv_tracker.py", "--action", "store_opening",
                     "--sport", "basketball_nba"])
    results["clv_store"] = ok

    # Summary
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'#'*60}")
    print(f"  CLOSING FULL RUN COMPLETE — {elapsed:.0f}s")
    print(f"{'#'*60}")
    for step, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {step:.<40} {status}")

    # Save run metadata
    meta = {
        "date": DATE,
        "started_at": start.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "results": {k: "ok" if v else "failed" for k, v in results.items()},
        "files_generated": [
            f"moneyline_parlays_{DATE}.json",
            f"player_props_{DATE}.json",
            f"sgp_picks_{DATE}.json",
        ]
    }
    meta_path = os.path.join(DIR, f"closing_full_run_{DATE}.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\n  Metadata: closing_full_run_{DATE}.json")


if __name__ == "__main__":
    main()
