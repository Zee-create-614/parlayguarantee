"""
MMA Backtest Engine — Historical accuracy analysis for ParlayGuarantee
Scrapes completed UFC events, runs model predictions, compares to actual results.
"""

import sys
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mma_scraper import UFCScraper, MMADataDB
from mma_engine import MMAEngine

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(Path(__file__).parent / "mma_backtest.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

ENGINE_DIR = Path(__file__).parent


class MMABacktester:
    """Backtest the MMA engine against completed UFC events."""

    def __init__(self):
        self.engine = MMAEngine()
        self.scraper = self.engine.scraper
        self.db = self.engine.db

    def scrape_completed_events(self, months: int = 6) -> List[Dict]:
        """Scrape completed UFC events from the last N months."""
        from bs4 import BeautifulSoup
        import requests

        cutoff = datetime.now() - timedelta(days=months * 30)
        url = "http://www.ufcstats.com/statistics/events/completed?page=all"

        cached = self.db.cache_get(f"completed_events_{months}m", max_age_hours=24)
        if cached:
            return json.loads(cached)

        logger.info(f"Scraping completed events (last {months} months)...")
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"Failed to fetch completed events: {e}")
            return []

        events = []
        rows = soup.select("tr.b-statistics__table-row")
        for row in rows:
            link = row.select_one("a.b-link")
            if not link:
                continue
            name = link.get_text(strip=True)
            href = link.get("href", "")
            date_el = row.select_one("span.b-statistics__date")
            date_text = (date_el.get_text(strip=True) if date_el else "").strip()

            if not date_text or not href:
                continue

            # Parse date
            event_date = None
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
                try:
                    event_date = datetime.strptime(date_text, fmt)
                    break
                except ValueError:
                    continue

            if not event_date or event_date < cutoff:
                continue

            events.append({
                "name": name,
                "url": href,
                "date": date_text,
                "date_parsed": event_date.strftime("%Y-%m-%d"),
            })

        logger.info(f"Found {len(events)} completed events in last {months} months")
        self.db.cache_set(f"completed_events_{months}m", json.dumps(events))
        return events

    def scrape_event_results(self, event_url: str) -> List[Dict]:
        """Scrape fight results from a completed event."""
        from bs4 import BeautifulSoup
        import requests

        cached = self.db.cache_get(f"results:{event_url}", max_age_hours=168)  # 1 week
        if cached:
            return json.loads(cached)

        time.sleep(1.5)  # throttle
        try:
            resp = requests.get(event_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.error(f"Failed to fetch event results: {e}")
            return []

        fights = []
        rows = soup.select("tr.b-fight-details__table-row")
        for row in rows:
            cols = row.select("td")
            if len(cols) < 8:
                continue

            # Fighters
            links = row.select("a.b-link_style_black")
            if len(links) < 2:
                continue
            f1 = links[0].get_text(strip=True)
            f2 = links[1].get_text(strip=True)

            # Result: first column has W/L indicator
            result_col = cols[0].get_text(strip=True).lower()
            # The winner is the first fighter listed if result is "win"
            winner = f1 if result_col in ("win", "w") else f2

            # Method
            method_col = cols[7].get_text(separator="|", strip=True) if len(cols) > 7 else ""
            method_parts = method_col.split("|")
            method = method_parts[0].strip() if method_parts else ""

            # Weight class
            wc = cols[6].get_text(strip=True) if len(cols) > 6 else ""

            # Round
            round_col = cols[8].get_text(strip=True) if len(cols) > 8 else ""

            fights.append({
                "fighter1": f1,
                "fighter2": f2,
                "winner": winner,
                "method": method,
                "weight_class": wc,
                "round": round_col,
                "is_draw": result_col in ("draw", "d", "nc"),
            })

        self.db.cache_set(f"results:{event_url}", json.dumps(fights))
        return fights

    def run_backtest(self, months: int = 6, max_events: int = 20) -> Dict:
        """Run full backtest across completed events."""
        events = self.scrape_completed_events(months)
        if not events:
            logger.error("No completed events found")
            return {"error": "No events found"}

        events = events[:max_events]
        results = {
            "total_fights": 0,
            "correct_picks": 0,
            "incorrect_picks": 0,
            "skipped": 0,
            "draws": 0,
            "by_confidence_tier": {
                "70+": {"total": 0, "correct": 0},
                "60-70": {"total": 0, "correct": 0},
                "50-60": {"total": 0, "correct": 0},
            },
            "method_accuracy": {
                "KO/TKO": {"predicted": 0, "correct": 0},
                "Submission": {"predicted": 0, "correct": 0},
                "Decision": {"predicted": 0, "correct": 0},
            },
            "event_results": [],
            "fight_log": [],
            "parlay_simulations": [],
        }

        for event in events:
            logger.info(f"Backtesting: {event['name']} ({event['date']})")
            event_fights = self.scrape_event_results(event["url"])
            if not event_fights:
                logger.warning(f"No results for {event['name']}")
                continue

            event_record = {
                "event": event["name"],
                "date": event.get("date_parsed", event["date"]),
                "fights": len(event_fights),
                "correct": 0,
                "incorrect": 0,
                "picks": [],
            }

            event_picks = []  # for parlay simulation

            for fight in event_fights:
                if fight.get("is_draw"):
                    results["draws"] += 1
                    continue

                f1 = fight["fighter1"]
                f2 = fight["fighter2"]
                actual_winner = fight["winner"]
                actual_method = fight.get("method", "")

                try:
                    matchup = self.engine.calculate_matchup(f1, f2, event_name=event["name"])
                except Exception as e:
                    logger.warning(f"Error predicting {f1} vs {f2}: {e}")
                    results["skipped"] += 1
                    continue

                if matchup.get("note"):  # default/insufficient data
                    results["skipped"] += 1
                    continue

                predicted_winner = matchup["predicted_winner"]
                confidence = matchup["confidence"]
                predicted_method = matchup["method_prediction"]

                # Normalize names for comparison
                correct = self._names_match(predicted_winner, actual_winner)

                results["total_fights"] += 1
                if correct:
                    results["correct_picks"] += 1
                    event_record["correct"] += 1
                else:
                    results["incorrect_picks"] += 1
                    event_record["incorrect"] += 1

                # Confidence tiers
                if confidence >= 70:
                    tier = "70+"
                elif confidence >= 60:
                    tier = "60-70"
                else:
                    tier = "50-60"
                results["by_confidence_tier"][tier]["total"] += 1
                if correct:
                    results["by_confidence_tier"][tier]["correct"] += 1

                # Method accuracy
                actual_method_cat = self._categorize_method(actual_method)
                results["method_accuracy"][predicted_method]["predicted"] += 1
                if predicted_method == actual_method_cat:
                    results["method_accuracy"][predicted_method]["correct"] += 1

                fight_entry = {
                    "fighter1": f1,
                    "fighter2": f2,
                    "predicted_winner": predicted_winner,
                    "actual_winner": actual_winner,
                    "correct": correct,
                    "confidence": confidence,
                    "predicted_method": predicted_method,
                    "actual_method": actual_method_cat,
                    "method_correct": predicted_method == actual_method_cat,
                    "event": event["name"],
                }
                results["fight_log"].append(fight_entry)
                event_record["picks"].append(fight_entry)

                # Build pick-like object for parlay simulation
                event_picks.append({
                    "type": "straight",
                    "games": [{
                        "home_team": f1,
                        "away_team": f2,
                        "predicted_winner": predicted_winner,
                        "confidence": confidence,
                        "method_prediction": predicted_method,
                        "home_probability": matchup["f1_probability"],
                        "away_probability": matchup["f2_probability"],
                    }],
                    "_actual_winner": actual_winner,
                    "_correct": correct,
                })

            results["event_results"].append(event_record)

            # Parlay simulation for this event
            if len(event_picks) >= 2:
                parlays = self.engine.generate_mma_parlays(event_picks)
                for parlay in parlays:
                    legs_correct = 0
                    legs_total = len(parlay.get("legs", []))
                    for leg in parlay.get("legs", []):
                        # Find corresponding actual result
                        for ep in event_picks:
                            g = ep["games"][0]
                            if leg["fighter"] == g["predicted_winner"]:
                                if ep["_correct"]:
                                    legs_correct += 1
                                break

                    parlay_hit = legs_correct == legs_total
                    results["parlay_simulations"].append({
                        "event": event["name"],
                        "leg_count": legs_total,
                        "tier": parlay.get("tier", ""),
                        "legs_correct": legs_correct,
                        "parlay_hit": parlay_hit,
                        "payout_per_100": parlay.get("payout_per_100", 0),
                    })

        # Compute summary stats
        total = results["total_fights"]
        results["overall_accuracy"] = round(results["correct_picks"] / max(total, 1) * 100, 1)

        for tier, data in results["by_confidence_tier"].items():
            data["accuracy"] = round(data["correct"] / max(data["total"], 1) * 100, 1)

        for method, data in results["method_accuracy"].items():
            data["accuracy"] = round(data["correct"] / max(data["predicted"], 1) * 100, 1)

        # Parlay summary
        parlay_sims = results["parlay_simulations"]
        if parlay_sims:
            total_parlays = len(parlay_sims)
            hit_parlays = sum(1 for p in parlay_sims if p["parlay_hit"])
            results["parlay_summary"] = {
                "total_simulated": total_parlays,
                "hit": hit_parlays,
                "hit_rate": round(hit_parlays / max(total_parlays, 1) * 100, 1),
                "by_tier": {},
            }
            for tier in ["Safe", "Medium", "Aggressive", "Moonshot"]:
                tier_parlays = [p for p in parlay_sims if p["tier"] == tier]
                if tier_parlays:
                    hits = sum(1 for p in tier_parlays if p["parlay_hit"])
                    results["parlay_summary"]["by_tier"][tier] = {
                        "total": len(tier_parlays),
                        "hit": hits,
                        "hit_rate": round(hits / len(tier_parlays) * 100, 1),
                    }

        results["run_timestamp"] = datetime.now().isoformat()
        results["model_version"] = "2.0-32factor"
        results["events_tested"] = len(events)

        return results

    def _names_match(self, name1: str, name2: str) -> bool:
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        if n1 == n2:
            return True
        # Partial match (last name)
        parts1 = n1.split()
        parts2 = n2.split()
        if parts1 and parts2 and parts1[-1] == parts2[-1]:
            return True
        if n1 in n2 or n2 in n1:
            return True
        return False

    def _categorize_method(self, method: str) -> str:
        m = method.upper()
        if any(k in m for k in ("KO", "TKO")):
            return "KO/TKO"
        if any(k in m for k in ("SUB", "SUBMISSION")):
            return "Submission"
        return "Decision"

    def generate_report(self, results: Dict) -> str:
        """Generate markdown backtest report."""
        r = results
        lines = [
            "# MMA Engine Backtest Report",
            f"**Model Version:** {r.get('model_version', 'unknown')}",
            f"**Run Date:** {r.get('run_timestamp', 'unknown')}",
            f"**Events Tested:** {r.get('events_tested', 0)}",
            "",
            "---",
            "",
            "## Overall Results",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Fights Predicted | {r['total_fights']} |",
            f"| Correct Picks | {r['correct_picks']} |",
            f"| Incorrect Picks | {r['incorrect_picks']} |",
            f"| Skipped (insufficient data) | {r['skipped']} |",
            f"| Draws / No Contests | {r['draws']} |",
            f"| **Overall Accuracy** | **{r['overall_accuracy']}%** |",
            "",
            "## Accuracy by Confidence Tier",
            "",
            "| Tier | Total | Correct | Accuracy |",
            "|------|-------|---------|----------|",
        ]

        for tier in ["70+", "60-70", "50-60"]:
            data = r["by_confidence_tier"][tier]
            lines.append(f"| {tier}% | {data['total']} | {data['correct']} | {data.get('accuracy', 0)}% |")

        lines += [
            "",
            "## Method Prediction Accuracy",
            "",
            "| Method | Predicted | Correct | Accuracy |",
            "|--------|-----------|---------|----------|",
        ]

        for method in ["KO/TKO", "Submission", "Decision"]:
            data = r["method_accuracy"][method]
            lines.append(f"| {method} | {data['predicted']} | {data['correct']} | {data.get('accuracy', 0)}% |")

        # Parlay summary
        ps = r.get("parlay_summary", {})
        if ps:
            lines += [
                "",
                "## Parlay Simulation",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Total Parlays Simulated | {ps['total_simulated']} |",
                f"| Parlays Hit | {ps['hit']} |",
                f"| **Hit Rate** | **{ps['hit_rate']}%** |",
                "",
                "### By Tier",
                "",
                "| Tier | Total | Hit | Hit Rate |",
                "|------|-------|-----|----------|",
            ]
            for tier, data in ps.get("by_tier", {}).items():
                lines.append(f"| {tier} | {data['total']} | {data['hit']} | {data['hit_rate']}% |")

        # Event breakdown
        lines += [
            "",
            "## Event Breakdown",
            "",
            "| Event | Date | Fights | Correct | Incorrect | Accuracy |",
            "|-------|------|--------|---------|-----------|----------|",
        ]
        for ev in r.get("event_results", []):
            total = ev["correct"] + ev["incorrect"]
            acc = round(ev["correct"] / max(total, 1) * 100, 1)
            lines.append(f"| {ev['event'][:40]} | {ev['date']} | {ev['fights']} | {ev['correct']} | {ev['incorrect']} | {acc}% |")

        lines += [
            "",
            "---",
            f"*Generated by ParlayGuarantee MMA Engine v2.0 (32-factor model)*",
        ]

        return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MMA Backtest Engine")
    parser.add_argument("--months", type=int, default=6, help="Months of history to test")
    parser.add_argument("--max-events", type=int, default=15, help="Max events to backtest")
    args = parser.parse_args()

    backtester = MMABacktester()

    logger.info(f"Starting backtest: {args.months} months, max {args.max_events} events")
    results = backtester.run_backtest(months=args.months, max_events=args.max_events)

    if "error" in results:
        logger.error(f"Backtest failed: {results['error']}")
        return

    # Save JSON
    json_path = ENGINE_DIR / "mma_backtest_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Results saved to {json_path}")

    # Save markdown report
    report = backtester.generate_report(results)
    md_path = ENGINE_DIR / "MMA_BACKTEST_REPORT.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Report saved to {md_path}")

    # Print summary
    print(f"\n{'='*50}")
    print(f"BACKTEST COMPLETE")
    print(f"{'='*50}")
    print(f"Fights: {results['total_fights']}")
    print(f"Accuracy: {results['overall_accuracy']}%")
    print(f"Correct: {results['correct_picks']} / {results['total_fights']}")
    for tier, data in results["by_confidence_tier"].items():
        print(f"  {tier}%: {data.get('accuracy', 0)}% ({data['correct']}/{data['total']})")
    ps = results.get("parlay_summary", {})
    if ps:
        print(f"Parlays: {ps['hit']}/{ps['total_simulated']} hit ({ps['hit_rate']}%)")


if __name__ == "__main__":
    main()
