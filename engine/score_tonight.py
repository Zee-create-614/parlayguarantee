"""
Unified result scorer for tonight's picks.
Scores NBA ML, NBA O/U, NCAAB ML, and NCAAB O/U.
Run the morning after games to get results.

Usage:
  python score_tonight.py                  # Score yesterday
  python score_tonight.py 2026-02-20      # Score specific date
"""

import sys
import json
import sqlite3
import requests
import logging
from datetime import date, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).parent


def fetch_nba_scores(target_date: date) -> dict:
    """Fetch NBA final scores from ESPN."""
    dt_str = target_date.strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt_str}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"NBA scores fetch failed: {e}")
        return {}

    scores = {}
    for event in data.get('events', []):
        comp = event.get('competitions', [{}])[0]
        status = comp.get('status', {}).get('type', {}).get('name', '')
        if status != 'STATUS_FINAL':
            continue
        competitors = comp.get('competitors', [])
        home_data = away_data = None
        for c in competitors:
            if c.get('homeAway') == 'home':
                home_data = c
            else:
                away_data = c
        if not home_data or not away_data:
            continue
        home_name = _map_nba_name(home_data['team'].get('displayName', ''))
        away_name = _map_nba_name(away_data['team'].get('displayName', ''))
        home_score = int(home_data.get('score', 0))
        away_score = int(away_data.get('score', 0))
        winner = home_name if home_score > away_score else away_name
        scores[f"{away_name}@{home_name}"] = {
            'home_team': home_name, 'away_team': away_name,
            'home_score': home_score, 'away_score': away_score,
            'total': home_score + away_score, 'winner': winner,
        }
    return scores


def fetch_ncaab_scores(target_date: date) -> dict:
    """Fetch NCAAB final scores from ESPN."""
    dt_str = target_date.strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?dates={dt_str}&limit=200"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"NCAAB scores fetch failed: {e}")
        return {}

    scores = {}
    for event in data.get('events', []):
        comp = event.get('competitions', [{}])[0]
        status = comp.get('status', {}).get('type', {}).get('name', '')
        if status != 'STATUS_FINAL':
            continue
        competitors = comp.get('competitors', [])
        home_data = away_data = None
        for c in competitors:
            if c.get('homeAway') == 'home':
                home_data = c
            else:
                away_data = c
        if not home_data or not away_data:
            continue
        home_name = home_data['team'].get('displayName', '')
        away_name = away_data['team'].get('displayName', '')
        home_score = int(home_data.get('score', 0))
        away_score = int(away_data.get('score', 0))
        winner = home_name if home_score > away_score else away_name
        scores[f"{away_name}@{home_name}"] = {
            'home_team': home_name, 'away_team': away_name,
            'home_score': home_score, 'away_score': away_score,
            'total': home_score + away_score, 'winner': winner,
        }
    return scores


def _map_nba_name(name: str) -> str:
    mapping = {'LA Clippers': 'Los Angeles Clippers'}
    return mapping.get(name, name)


def _fuzzy_find(scores: dict, home: str, away: str):
    """Find a score entry by exact or fuzzy match."""
    key = f"{away}@{home}"
    if key in scores:
        return scores[key]
    # Fuzzy: check if team names are substrings
    hl = home.lower()
    al = away.lower()
    for k, v in scores.items():
        kl = k.lower()
        if hl in kl and al in kl:
            return v
        # Try just the last word (mascot)
        h_mascot = hl.split()[-1]
        a_mascot = al.split()[-1]
        if h_mascot in kl and a_mascot in kl:
            return v
    return None


def score_nba_ou(target_date: date, scores: dict) -> dict:
    """Score NBA O/U predictions."""
    db_path = ENGINE_DIR / "totals_engine.db"
    if not db_path.exists():
        return {'sport': 'NBA O/U', 'error': 'No predictions DB'}

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute('''SELECT home_team, away_team, predicted_total, posted_total, pick, edge, confidence
                 FROM totals_predictions WHERE game_date = ?''', (target_date.isoformat(),))
    preds = c.fetchall()
    conn.close()

    if not preds:
        return {'sport': 'NBA O/U', 'error': 'No predictions for this date'}

    results = []
    correct = total = 0

    for home, away, pred_total, posted, pick, edge, conf in preds:
        actual = _fuzzy_find(scores, home, away)
        if not actual:
            results.append({'matchup': f"{away} @ {home}", 'pick': pick, 'edge': edge,
                           'posted': posted, 'predicted': pred_total, 'actual': None,
                           'result': 'NO SCORE'})
            continue

        actual_total = actual['total']
        actual_result = "OVER" if actual_total > posted else ("UNDER" if actual_total < posted else "PUSH")

        if actual_result == "PUSH":
            hit = True
        else:
            hit = (pick == actual_result)
            total += 1
            if hit:
                correct += 1

        # Update DB
        conn2 = sqlite3.connect(str(db_path))
        conn2.execute('''UPDATE totals_predictions SET actual_total = ?, result = ?
                     WHERE game_date = ? AND home_team = ? AND away_team = ?''',
                   (actual_total, "HIT" if hit else "MISS", target_date.isoformat(), home, away))
        conn2.commit()
        conn2.close()

        results.append({
            'matchup': f"{away} @ {home}",
            'pick': pick, 'edge': edge, 'posted': posted,
            'predicted': pred_total, 'actual': actual_total,
            'result': 'HIT' if hit else 'MISS',
        })

    return {
        'sport': 'NBA O/U',
        'date': target_date.isoformat(),
        'results': results,
        'correct': correct, 'total': total,
        'accuracy': correct / total if total > 0 else 0,
    }


def score_ncaab_ou(target_date: date, scores: dict) -> dict:
    """Score NCAAB O/U predictions."""
    db_path = ENGINE_DIR / "ncaab_totals.db"
    if not db_path.exists():
        return {'sport': 'NCAAB O/U', 'error': 'No predictions DB'}

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute('''SELECT home_team, away_team, predicted_total, posted_total, pick, edge
                 FROM ncaab_totals_predictions WHERE game_date = ?''', (target_date.isoformat(),))
    preds = c.fetchall()
    conn.close()

    if not preds:
        return {'sport': 'NCAAB O/U', 'error': 'No predictions for this date'}

    results = []
    correct = total = 0

    for home, away, pred_total, posted, pick, edge in preds:
        actual = _fuzzy_find(scores, home, away)
        if not actual:
            results.append({'matchup': f"{away} @ {home}", 'pick': pick, 'edge': edge,
                           'posted': posted, 'predicted': pred_total, 'actual': None,
                           'result': 'NO SCORE'})
            continue

        actual_total = actual['total']
        actual_result = "OVER" if actual_total > posted else ("UNDER" if actual_total < posted else "PUSH")

        if actual_result == "PUSH":
            hit = True
        else:
            hit = (pick == actual_result)
            total += 1
            if hit:
                correct += 1

        # Update DB
        conn2 = sqlite3.connect(str(db_path))
        conn2.execute('''UPDATE ncaab_totals_predictions SET actual_total = ?, result = ?
                     WHERE game_date = ? AND home_team = ? AND away_team = ?''',
                   (actual_total, "HIT" if hit else "MISS", target_date.isoformat(), home, away))
        conn2.commit()
        conn2.close()

        results.append({
            'matchup': f"{away} @ {home}",
            'pick': pick, 'edge': edge, 'posted': posted,
            'predicted': pred_total, 'actual': actual_total,
            'result': 'HIT' if hit else 'MISS',
        })

    return {
        'sport': 'NCAAB O/U',
        'date': target_date.isoformat(),
        'results': results,
        'correct': correct, 'total': total,
        'accuracy': correct / total if total > 0 else 0,
    }


def print_section(data: dict):
    """Pretty-print a scoring section."""
    sport = data.get('sport', '?')
    if 'error' in data:
        print(f"\n  {sport}: {data['error']}")
        return

    correct = data['correct']
    total = data['total']
    acc = data['accuracy']
    print(f"\n{'='*70}")
    print(f"  {sport} -- {data['date']}")
    print(f"  Record: {correct}/{total} ({acc*100:.0f}%)")
    print(f"{'='*70}")

    for r in data['results']:
        if r['actual'] is None:
            icon = "?"
        elif r['result'] == 'HIT':
            icon = "V"
        else:
            icon = "X"
        actual_str = str(r['actual']) if r['actual'] is not None else 'N/A'
        print(f"  {icon} {r['matchup']}: {r['pick']} {r['posted']} "
              f"(pred {r['predicted']}, actual {actual_str}, edge {r['edge']:+.1f})")


def main():
    if len(sys.argv) > 1:
        try:
            target = date.fromisoformat(sys.argv[1])
        except:
            target = date.today() - timedelta(days=1)
    else:
        target = date.today() - timedelta(days=1)

    print(f"\n  Scoring all picks for {target}...")

    # Fetch scores
    nba_scores = fetch_nba_scores(target)
    ncaab_scores = fetch_ncaab_scores(target)

    print(f"  NBA games found: {len(nba_scores)}")
    print(f"  NCAAB games found: {len(ncaab_scores)}")

    # Score each category
    nba_ou = score_nba_ou(target, nba_scores)
    ncaab_ou = score_ncaab_ou(target, ncaab_scores)

    print_section(nba_ou)
    print_section(ncaab_ou)

    # Summary
    all_correct = sum(d.get('correct', 0) for d in [nba_ou, ncaab_ou] if 'correct' in d)
    all_total = sum(d.get('total', 0) for d in [nba_ou, ncaab_ou] if 'total' in d)
    if all_total > 0:
        print(f"\n{'='*70}")
        print(f"  COMBINED O/U: {all_correct}/{all_total} ({100*all_correct/all_total:.0f}%)")
        print(f"{'='*70}")

    # Save full results
    out = {'date': target.isoformat(), 'nba_ou': nba_ou, 'ncaab_ou': ncaab_ou}
    out_path = ENGINE_DIR / f"scored_results_{target}.json"
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  Saved to {out_path}")


if __name__ == "__main__":
    main()
