"""
FULL MULTI-SPORT ANALYSIS: NBA + NCAAB
Wires both sports through tier_engine_v2 analysis + upset composite + injuries.
Outputs analyzed_games.json for the UI picks API.
"""
import json
import logging
import sys
import math
from itertools import combinations
from datetime import datetime, date, timedelta, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

from tier_engine_v2 import fetch_games, analyze_game
from injury_scraper import get_injuries, STAR_IMPACT

# Line movement disabled for now — extra API calls + slow
LM_AVAILABLE = False

# ─── TEAM ABBREVIATIONS ───
TEAM_ABBREVS = {
    # NBA
    'Cleveland Cavaliers': 'CLE', 'Charlotte Hornets': 'CHA',
    'Utah Jazz': 'UTA', 'Memphis Grizzlies': 'MEM',
    'Indiana Pacers': 'IND', 'Washington Wizards': 'WAS',
    'Miami Heat': 'MIA', 'Atlanta Hawks': 'ATL',
    'Dallas Mavericks': 'DAL', 'Minnesota Timberwolves': 'MIN',
    'Brooklyn Nets': 'BKN', 'Oklahoma City Thunder': 'OKC',
    'Milwaukee Bucks': 'MIL', 'New Orleans Pelicans': 'NOP',
    'Denver Nuggets': 'DEN', 'Portland Trail Blazers': 'POR',
    'Los Angeles Clippers': 'LAC', 'Los Angeles Lakers': 'LAL',
    'Houston Rockets': 'HOU', 'New York Knicks': 'NYK',
    'Phoenix Suns': 'PHX', 'Orlando Magic': 'ORL',
    'Chicago Bulls': 'CHI', 'Detroit Pistons': 'DET',
    'San Antonio Spurs': 'SAS', 'Sacramento Kings': 'SAC',
    'Golden State Warriors': 'GSW', 'Toronto Raptors': 'TOR',
    'Boston Celtics': 'BOS', 'Philadelphia 76ers': 'PHI',
}

def abbrev(team):
    return TEAM_ABBREVS.get(team, team[:3].upper())


def compute_upset_composite(game, injuries_by_team, lm_score_data):
    """Compute upset composite. Returns (score, reasons)."""
    spread = game.get('spread', 0)
    if not spread:
        return 0.0, []

    if spread < 0:
        fav, dog = game['home'], game['away']
        dog_side = 'away'
    else:
        fav, dog = game['away'], game['home']
        dog_side = 'home'

    score = game.get('upset_score', 0) / 100.0  # from tier_engine_v2 (0-100 → 0-1)
    reasons = list(game.get('upset_reasons', []))

    # Injury impact
    fav_inj = injuries_by_team.get(fav, [])
    dog_inj = injuries_by_team.get(dog, [])
    fav_star_out = sum(1 for i in fav_inj if i.get('player','') in STAR_IMPACT and i.get('status') in ('Out','Doubtful'))
    dog_star_out = sum(1 for i in dog_inj if i.get('player','') in STAR_IMPACT and i.get('status') in ('Out','Doubtful'))

    if fav_star_out > 0 and dog_star_out == 0:
        boost = fav_star_out * 0.15
        score += boost
        reasons.append(f'🏥 Favorite missing {fav_star_out} star(s): +{boost:.2f}')
    elif dog_star_out > 0 and fav_star_out == 0:
        penalty = dog_star_out * 0.10
        score -= penalty
        reasons.append(f'🏥 Dog missing {dog_star_out} star(s): -{penalty:.2f}')

    # Line movement
    if lm_score_data:
        lm_val = lm_score_data.get('score', 0)
        if lm_val > 0:
            score += lm_val
            reasons.append(f'📈 Line moving toward DOG: +{lm_val:.2f}')
        elif lm_val < 0:
            score += lm_val
            reasons.append(f'📉 Line moving toward FAV: {lm_val:.2f}')

    # Home dog bonus
    if dog_side == 'home':
        score += 0.1
        reasons.append('🏠 Home dog bonus +0.10')

    return round(max(score, 0), 4), reasons


def main():
    est = timezone(timedelta(hours=-5))
    today = datetime.now(est).strftime('%Y-%m-%d')
    tomorrow = (datetime.now(est) + timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"{'='*60}")
    print(f"MULTI-SPORT FULL ANALYSIS — {today}")
    print(f"{'='*60}")

    # ─── STEP 1: Fetch games for both sports ───
    all_analyzed = []

    for sport_key, sport_label in [('basketball_nba', 'NBA'), ('basketball_ncaab', 'NCAAB')]:
        print(f"\nFetching {sport_label} odds...")
        try:
            raw = fetch_games(sport_key)
            print(f"  Got {len(raw)} {sport_label} events from Odds API")
        except Exception as e:
            print(f"  ERROR fetching {sport_label}: {e}")
            continue

        count = 0
        for g in raw:
            result = analyze_game(g)
            if result:
                result['sport'] = sport_label
                result['sport_key'] = sport_key
                all_analyzed.append(result)
                count += 1
        print(f"  Analyzed {count} {sport_label} games with spreads")

    # Filter to today + tomorrow
    target_games = [g for g in all_analyzed if g['game_date'] in (today, tomorrow)]
    today_games = [g for g in target_games if g['game_date'] == today]
    tomorrow_games = [g for g in target_games if g['game_date'] == tomorrow]

    nba_count = sum(1 for g in target_games if g['sport'] == 'NBA')
    ncaab_count = sum(1 for g in target_games if g['sport'] == 'NCAAB')
    print(f"\nTarget games: {len(target_games)} total ({nba_count} NBA, {ncaab_count} NCAAB)")
    print(f"  Today ({today}): {len(today_games)} | Tomorrow ({tomorrow}): {len(tomorrow_games)}")

    # ─── STEP 2: Injuries ───
    print("\nFetching live injury data...")
    try:
        injuries_raw = get_injuries(force_refresh=True)
        print(f"  Got injury data for {len(injuries_raw)} teams")
    except Exception as e:
        print(f"  Injury fetch error: {e}")
        injuries_raw = {}

    # ─── STEP 3: Line movement ───
    lm_data = {}
    if LM_AVAILABLE:
        print("\nTaking line movement snapshots...")
        try:
            lm_init_db()
            for sport_key in ['nba', 'ncaab']:
                snap = fetch_odds_snapshot(sport_key)
                if snap:
                    store_snapshot(snap, sport_key)
                    for g in target_games:
                        if g.get('sport_key', '').endswith(sport_key):
                            try:
                                lm = get_line_movement_score(g['home'], g['away'], sport=sport_key)
                                if lm:
                                    lm_data[f"{g['away']}@{g['home']}"] = lm
                            except:
                                pass
            print(f"  Line movement data for {len(lm_data)} games")
        except Exception as e:
            print(f"  Line movement error: {e}")

    # ─── STEP 4: Upset composites + enhanced scoring ───
    print("\nComputing upset composites...")
    for g in target_games:
        key = f"{g['away']}@{g['home']}"
        lm = lm_data.get(key, None)

        upset_score, upset_reasons = compute_upset_composite(g, injuries_raw, lm)
        g['upset_score'] = upset_score
        g['upset_reasons'] = upset_reasons
        g['line_movement'] = lm

        # Injuries
        home_inj = injuries_raw.get(g['home'], [])
        away_inj = injuries_raw.get(g['away'], [])
        g['home_injuries'] = [{'player': i.get('player',''), 'status': i.get('status',''),
                               'star': i.get('player','') in STAR_IMPACT} for i in home_inj if i.get('status') in ('Out','Doubtful','Questionable')]
        g['away_injuries'] = [{'player': i.get('player',''), 'status': i.get('status',''),
                               'star': i.get('player','') in STAR_IMPACT} for i in away_inj if i.get('status') in ('Out','Doubtful','Questionable')]

        # Enhanced prob: upset composite adjustments
        spread = g.get('spread', 0)
        if spread < 0:
            favorite, dog = g['home'], g['away']
        elif spread > 0:
            favorite, dog = g['away'], g['home']
        else:
            favorite, dog = None, None

        if dog and g['pick'] == dog and upset_score > 0.3:
            boost = min(upset_score * 0.05, 0.04)
            g['enhanced_prob'] = round(g['cover_prob'] + boost, 4)
        elif favorite and g['pick'] == favorite and upset_score > 0.5:
            penalty = min(upset_score * 0.03, 0.03)
            g['enhanced_prob'] = round(g['cover_prob'] - penalty, 4)
        else:
            g['enhanced_prob'] = g['cover_prob']

        # Edge
        g['edge'] = g.get('edge', 0)

        # Upset flip — only if strong signal
        g['upset_flip'] = False
        if upset_score >= 0.8 and abs(spread) <= 10 and dog:
            if g['pick'] != dog:
                g['original_pick'] = g['pick']
                g['pick'] = dog
                g['enhanced_prob'] = round(1 - g['cover_prob'] + 0.02, 4)
                g['upset_flip'] = True
                g['pick_label'] = '🔄 UPSET FLIP'
                # Recalculate spread_str for the flipped pick
                if spread < 0:
                    g['pick_spread'] = round(-spread, 1)
                    g['spread_str'] = f"+{-spread}" if -spread > 0 else str(-spread)
                else:
                    g['pick_spread'] = spread
                    g['spread_str'] = f"+{spread}" if spread > 0 else str(spread)

    # Sort by enhanced probability
    target_games.sort(key=lambda x: x.get('enhanced_prob', 0), reverse=True)

    # ─── STEP 5: Save analyzed_games.json ───
    outfile = 'analyzed_games.json'
    with open(outfile, 'w', encoding='utf-8') as f:
        json.dump(target_games, f, indent=2, default=str)
    print(f"\n✅ Saved {len(target_games)} games to {outfile}")

    # ─── STEP 6: Also regenerate picks_output.json with tiers ───
    from tier_engine_v2 import generate_parlays, TIERS
    output = {
        'date': today,
        'generated_at': datetime.now(est).isoformat(),
        'total_games': len(target_games),
        'tiers': {},
        '_metadata': {
            'nba_games': nba_count,
            'ncaab_games': ncaab_count,
            'source': 'run_full_multi_sport.py',
        }
    }

    # For tier parlays, use only top-confidence games to avoid combinatorial explosion
    top_games = sorted(target_games, key=lambda x: x.get('enhanced_prob', 0), reverse=True)[:25]
    top_today = [g for g in top_games if g['game_date'] == today]

    for tier_id, cfg in TIERS.items():
        legs = cfg['legs']
        count = cfg['count']
        pool = top_today if legs <= 2 else top_games
        if len(pool) < legs:
            pool = top_games
        picks = generate_parlays(pool, legs, count)
        output['tiers'][tier_id] = {
            'tier_id': tier_id,
            'legs': legs,
            'picks': picks,
            'game_pool_size': len(pool),
        }

    # Also store flat all_games
    output['all_games'] = target_games

    with open('picks_output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"✅ Saved picks_output.json with tiers")

    # ─── STEP 7: Print summary ───
    print(f"\n{'='*60}")
    print(f"PICKS SUMMARY")
    print(f"{'='*60}")

    for sport in ['NBA', 'NCAAB']:
        games = [g for g in target_games if g['sport'] == sport]
        if not games:
            continue
        print(f"\n🏀 {sport} ({len(games)} games)")
        for g in games:
            flip = ' 🔄FLIP' if g.get('upset_flip') else ''
            upset = f" [upset:{g['upset_score']:.2f}]" if g.get('upset_score', 0) > 0 else ''
            inj_home = len(g.get('home_injuries', []))
            inj_away = len(g.get('away_injuries', []))
            inj = f" [inj:H{inj_home}/A{inj_away}]" if inj_home + inj_away > 0 else ''
            print(f"  • {g['away']} @ {g['home']} → {g['pick']} {g['spread_str']} ({g['enhanced_prob']:.0%}){upset}{inj}{flip}")

    print(f"\nDone! {len(target_games)} games analyzed with full composite scoring.")


if __name__ == '__main__':
    main()
