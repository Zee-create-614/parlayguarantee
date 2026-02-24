# -*- coding: utf-8 -*-
"""
Soccer Totals Engine — Over/Under goals predictions for ParlayGuarantee
Analyzes scoring tendencies, defensive records, and match context
to predict total goals and generate over/under picks.
"""

import sys
import json
import math
import logging
import os
from datetime import date
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from soccer_data_fetcher import SoccerDataFetcher, LEAGUES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('soccer_totals.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# League average goals per game
LEAGUE_AVG_GOALS = {
    'soccer_epl': 2.75,
    'soccer_spain_la_liga': 2.60,
    'soccer_germany_bundesliga': 3.05,
    'soccer_italy_serie_a': 2.65,
    'soccer_france_ligue_one': 2.55,
    'soccer_usa_mls': 2.95,
    'soccer_uefa_champs_league': 2.90,
}


class SoccerTotalsEngine:
    """Predicts over/under for soccer matches."""

    def __init__(self):
        self.fetcher = SoccerDataFetcher()

    def generate_picks(self, target_date: Optional[date] = None,
                       leagues: Optional[List[str]] = None) -> List[Dict]:
        target = target_date or date.today()
        logger.info(f"Soccer Totals: generating picks for {target}")

        all_games = self.fetcher.fetch_all_games(target, leagues)
        if not all_games:
            return []

        standings_map = {}
        for lk in all_games:
            standings_map[lk] = {s['team'].lower(): s
                                 for s in self.fetcher.get_standings(lk)}

        picks = []
        for league_key, games in all_games.items():
            standings = standings_map.get(league_key, {})
            avg_goals = LEAGUE_AVG_GOALS.get(league_key, 2.75)

            for game in games:
                try:
                    pick = self._analyze_total(game, standings, league_key, avg_goals)
                    if pick:
                        picks.append(pick)
                except Exception as e:
                    logger.error(f"Totals error {game.get('home_team')} vs "
                                 f"{game.get('away_team')}: {e}")

        picks.sort(key=lambda x: abs(x.get('edge', 0)), reverse=True)
        logger.info(f"Generated {len(picks)} totals picks")
        return picks

    def _analyze_total(self, game: Dict, standings: Dict,
                       league_key: str, league_avg: float) -> Optional[Dict]:
        home = game['home_team']
        away = game['away_team']
        total_line = game.get('total')

        h_stand = standings.get(home.lower(), self._default(home))
        a_stand = standings.get(away.lower(), self._default(away))

        gp_h = max(h_stand.get('games_played', 1), 1)
        gp_a = max(a_stand.get('games_played', 1), 1)

        # Goals scored/conceded per game
        h_gf = h_stand.get('goals_for', 0) / gp_h
        h_ga = h_stand.get('goals_against', 0) / gp_h
        a_gf = a_stand.get('goals_for', 0) / gp_a
        a_ga = a_stand.get('goals_against', 0) / gp_a

        # Expected goals for each team using Poisson-style estimate
        # Home team expected = (home_attack * away_defense) / league_avg
        home_attack = h_gf
        away_defense = a_ga
        away_attack = a_gf
        home_defense = h_ga

        if league_avg > 0:
            h_expected = (home_attack * away_defense) / (league_avg / 2)
            a_expected = (away_attack * home_defense) / (league_avg / 2)
        else:
            h_expected = home_attack
            a_expected = away_attack

        # Home boost (~10% more goals at home)
        h_expected *= 1.08
        a_expected *= 0.92

        predicted_total = h_expected + a_expected

        # Blend with league average (regression to mean)
        predicted_total = predicted_total * 0.7 + league_avg * 0.3

        # Determine pick
        if total_line is None:
            total_line = 2.5  # default

        edge = predicted_total - total_line
        if abs(edge) < 0.15:
            ou_pick = None
            confidence = 0.50
        elif edge > 0:
            ou_pick = f"Over {total_line}"
            confidence = min(0.80, 0.50 + abs(edge) * 0.15)
        else:
            ou_pick = f"Under {total_line}"
            confidence = min(0.80, 0.50 + abs(edge) * 0.15)

        # Probability of over 2.5 using Poisson approximation
        lam = predicted_total
        # P(0) + P(1) + P(2) = sum of Poisson(k, lambda) for k=0,1,2
        p_under_2_5 = sum(
            (lam ** k) * math.exp(-lam) / math.factorial(k)
            for k in range(3)
        )
        p_over_2_5 = 1 - p_under_2_5

        return {
            'game_id': game.get('game_id', ''),
            'game_date': game.get('game_date', ''),
            'sport': 'Soccer',
            'league': league_key,
            'league_name': game.get('league_name', ''),
            'home_team': home,
            'away_team': away,
            'predicted_total': round(predicted_total, 2),
            'total_line': total_line,
            'ou_pick': ou_pick,
            'confidence': round(confidence, 4),
            'edge': round(edge, 2),
            'home_expected_goals': round(h_expected, 2),
            'away_expected_goals': round(a_expected, 2),
            'over_2_5_prob': round(p_over_2_5, 4),
            'under_2_5_prob': round(p_under_2_5, 4),
            'pick_type': 'total',
        }

    def _default(self, team: str) -> Dict:
        return {
            'team': team, 'games_played': 10,
            'goals_for': 13, 'goals_against': 13,
            'wins': 3, 'draws': 4, 'losses': 3,
        }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Soccer Totals Engine')
    parser.add_argument('--date', type=str)
    parser.add_argument('--league', type=str)
    args = parser.parse_args()

    engine = SoccerTotalsEngine()
    td = date.fromisoformat(args.date) if args.date else date.today()
    leagues = [args.league] if args.league else None
    picks = engine.generate_picks(td, leagues)

    print(f"\n{'='*60}")
    print(f"  SOCCER TOTALS \u2014 {td}")
    print(f"{'='*60}\n")

    for p in picks:
        if p.get('ou_pick'):
            print(f"  [{p['league_name']}] {p['home_team']} vs {p['away_team']}")
            print(f"    {p['ou_pick']} (pred: {p['predicted_total']:.1f}, "
                  f"conf: {p['confidence']:.0%}, edge: {p['edge']:+.2f})")
            print(f"    O2.5: {p['over_2_5_prob']:.0%} | U2.5: {p['under_2_5_prob']:.0%}")
            print()
