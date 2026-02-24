"""
Quick backtest: predict totals for recent games using current team stats,
then compare against actual scores from ESPN.
Tests the last N days of games.
"""

import requests
import json
import logging
import sys
from datetime import date, timedelta, datetime
from totals_engine import TotalsEngine, LEAGUE_AVG_PPG

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def fetch_games_with_scores(target_date: date):
    """Fetch completed games from ESPN scoreboard."""
    dt_str = target_date.strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={dt_str}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  ESPN error for {target_date}: {e}")
        return []

    games = []
    for event in data.get('events', []):
        comp = event.get('competitions', [{}])[0]
        competitors = comp.get('competitors', [])
        if len(competitors) < 2:
            continue

        status = comp.get('status', {}).get('type', {}).get('name', '')
        if status != 'STATUS_FINAL':
            continue

        home_data = away_data = None
        for c in competitors:
            if c.get('homeAway') == 'home':
                home_data = c
            else:
                away_data = c

        if not home_data or not away_data:
            continue

        # Get spread/total from odds if available
        odds_info = comp.get('odds', [{}])
        posted_total = None
        spread = 0
        if odds_info:
            posted_total = odds_info[0].get('overUnder')
            spread = odds_info[0].get('spread', 0)

        home_name = home_data['team'].get('displayName', '')
        away_name = away_data['team'].get('displayName', '')

        # Map names
        name_map = {'LA Clippers': 'Los Angeles Clippers'}
        home_name = name_map.get(home_name, home_name)
        away_name = name_map.get(away_name, away_name)

        home_score = int(home_data.get('score', 0))
        away_score = int(away_data.get('score', 0))

        games.append({
            'home_team': home_name,
            'away_team': away_name,
            'home_score': home_score,
            'away_score': away_score,
            'actual_total': home_score + away_score,
            'posted_total': posted_total,
            'spread': spread if spread else 0,
        })

    return games


def main():
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 7

    engine = TotalsEngine()
    engine.fetch_team_stats()
    engine.fetch_pace_data()

    total_correct = 0
    total_games = 0
    total_correct_high_conf = 0
    total_high_conf = 0
    all_results = []

    for i in range(1, days_back + 1):
        d = date.today() - timedelta(days=i)
        games = fetch_games_with_scores(d)
        if not games:
            continue

        day_correct = 0
        day_total = 0

        print(f"\n{'='*70}")
        print(f"  {d} — {len(games)} games")
        print(f"{'='*70}")

        for g in games:
            posted = g['posted_total']
            if posted is None:
                # Estimate posted total from actual total with noise
                # Vegas lines are typically within 5-8 points of actual
                # Use actual total as a stand-in (this makes the backtest
                # test our directional ability, not our total prediction)
                # Better: use league avg matchup estimate as "posted"
                h_stats = engine.team_stats.get(g['home_team'], {})
                a_stats = engine.team_stats.get(g['away_team'], {})
                h_ppg = h_stats.get('ppg', 113.5)
                h_papg = h_stats.get('papg', 113.5)
                a_ppg = a_stats.get('ppg', 113.5)
                a_papg = a_stats.get('papg', 113.5)
                # Simple estimate of what Vegas would post
                posted = round((h_ppg + a_ppg + h_papg + a_papg) / 4 * 2, 1)
                g['posted_total'] = posted

            pred = engine.predict_total(
                g['home_team'], g['away_team'],
                posted, g['spread']
            )

            actual = g['actual_total']
            actual_result = "OVER" if actual > g['posted_total'] else (
                "UNDER" if actual < g['posted_total'] else "PUSH")

            if actual_result == "PUSH":
                continue

            hit = pred['pick'] == actual_result
            day_correct += 1 if hit else 0
            day_total += 1
            total_games += 1
            total_correct += 1 if hit else 0

            if abs(pred['edge']) >= 4:
                total_high_conf += 1
                total_correct_high_conf += 1 if hit else 0

            icon = "✅" if hit else "❌"
            print(f"  {icon} {g['away_team']} @ {g['home_team']}: "
                  f"{pred['pick']} {g['posted_total']} (pred {pred['predicted_total']}, "
                  f"actual {actual}, edge {pred['edge']:+.1f})")

            all_results.append({
                'date': d.isoformat(),
                'matchup': f"{g['away_team']}@{g['home_team']}",
                'pick': pred['pick'],
                'posted': g['posted_total'],
                'predicted': pred['predicted_total'],
                'actual': actual,
                'edge': pred['edge'],
                'hit': hit,
                'high_conf': abs(pred['edge']) >= 4,
            })

        if day_total > 0:
            print(f"  Day: {day_correct}/{day_total} ({100*day_correct/day_total:.0f}%)")

    print(f"\n{'='*70}")
    print(f"  BACKTEST SUMMARY — Last {days_back} days")
    print(f"{'='*70}")
    if total_games > 0:
        print(f"  Overall: {total_correct}/{total_games} ({100*total_correct/total_games:.1f}%)")
    if total_high_conf > 0:
        print(f"  High-confidence (4+ edge): {total_correct_high_conf}/{total_high_conf} "
              f"({100*total_correct_high_conf/total_high_conf:.1f}%)")

    # Breakdown by edge size
    for threshold in [1, 2, 3, 4, 6]:
        subset = [r for r in all_results if abs(r['edge']) >= threshold]
        if subset:
            hits = sum(1 for r in subset if r['hit'])
            print(f"  Edge >= {threshold}: {hits}/{len(subset)} ({100*hits/len(subset):.1f}%)")

    # Over vs Under breakdown
    overs = [r for r in all_results if r['pick'] == 'OVER']
    unders = [r for r in all_results if r['pick'] == 'UNDER']
    if overs:
        oh = sum(1 for r in overs if r['hit'])
        print(f"  OVERs: {oh}/{len(overs)} ({100*oh/len(overs):.1f}%)")
    if unders:
        uh = sum(1 for r in unders if r['hit'])
        print(f"  UNDERs: {uh}/{len(unders)} ({100*uh/len(unders):.1f}%)")


if __name__ == "__main__":
    main()
