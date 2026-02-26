"""
ParlayGuarantee NCAAB Challenger Engine — "REX"
================================================
Challenger to the OG NCAAB engine.

KEY DIFFERENCE: Minimum confidence threshold on spread picks.
OG picks dogs at 50.0-50.5% spread confidence just because taking points
inflates cover probability slightly. That's noise, not signal.

Rex says: if the spread math can't clear 55%, it's a PASS.
The ML side shows real conviction (65-95%). The spread side should too,
or it shouldn't be a pick.

FROZEN: Do not modify OG. Rex runs alongside it. Data decides the winner.
"""

import sys
import json
import logging
import os
from datetime import date
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import the OG engine — Rex inherits everything, only overrides spread logic
from ncaab_engine import NCAABEngine, DEFAULT_WEIGHTS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('ncaab_engine_rex.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ─── Rex Configuration ──────────────────────────────────────
SPREAD_CONFIDENCE_FLOOR = 0.55   # Below this = PASS (not a real pick)
ML_CONFIDENCE_FLOOR = 0.58       # ML picks also need conviction
ENGINE_NAME = "Rex"
ENGINE_VERSION = "1.0"


class NCAABEngineRex(NCAABEngine):
    """
    Challenger engine that filters out noise picks.
    
    Same 30-factor model as OG, but:
    1. Spread picks require >= 55% confidence or they're a PASS
    2. ML picks require >= 58% confidence or they're a PASS  
    3. Picks that are PASS still show in output (for comparison) but are flagged
    4. Confidence recalibration: spreads use a steeper curve so near-50% 
       doesn't sneak through
    """

    def __init__(self, tournament_mode: bool = False):
        super().__init__(tournament_mode=tournament_mode)
        self.engine_name = ENGINE_NAME
        self.engine_version = ENGINE_VERSION

    def predict_games(self, target_date: Optional[date] = None,
                      seeds: Optional[Dict[str, int]] = None) -> List[Dict]:
        """Run OG pipeline, then apply Rex filters."""
        # Get all predictions from OG engine
        predictions = super().predict_games(target_date, seeds)
        
        rex_predictions = []
        passed = 0
        promoted = 0
        
        for pred in predictions:
            pred['engine'] = ENGINE_NAME
            pred['engine_version'] = ENGINE_VERSION
            
            # ── Apply spread confidence floor ──
            spread_conf = pred.get('spread_confidence', 0)
            ml_conf = pred.get('confidence', 0)
            
            # Flag spread picks that don't clear the threshold
            if pred.get('spread_pick') and spread_conf < SPREAD_CONFIDENCE_FLOOR:
                pred['spread_pick_original'] = pred['spread_pick']
                pred['spread_confidence_original'] = spread_conf
                pred['spread_pick'] = None  # PASS
                pred['spread_confidence'] = 0
                pred['spread_status'] = 'PASS'
                pred['spread_pass_reason'] = f'Below {SPREAD_CONFIDENCE_FLOOR:.0%} floor ({spread_conf:.1%})'
                passed += 1
            elif pred.get('spread_pick'):
                pred['spread_status'] = 'PICK'
                promoted += 1
            
            # Flag ML picks that don't clear threshold
            if ml_conf < ML_CONFIDENCE_FLOOR:
                pred['ml_status'] = 'WEAK'
                pred['ml_pass_reason'] = f'Below {ML_CONFIDENCE_FLOOR:.0%} floor ({ml_conf:.1%})'
            else:
                pred['ml_status'] = 'PICK'
            
            # ── Recalibrated spread confidence ──
            # OG's spread confidence clusters at 50-55%. Rex uses a steeper curve
            # that punishes near-coin-flip picks and rewards real edges.
            if pred.get('spread_pick') and spread_conf > 0:
                # Remap: 55% → 55%, 60% → 62%, 70% → 75%, 85% → 85%
                # This stretches the range above the floor
                edge = spread_conf - 0.5
                recalibrated = 0.5 + edge * 1.25  # amplify the edge
                recalibrated = max(SPREAD_CONFIDENCE_FLOOR, min(0.90, recalibrated))
                pred['spread_confidence_recalibrated'] = round(recalibrated, 4)
            
            rex_predictions.append(pred)
        
        # Sort: real picks first (by confidence), then PASSes
        rex_predictions.sort(key=lambda x: (
            x.get('spread_status') == 'PICK',  # PICK first
            x.get('spread_confidence', 0)
        ), reverse=True)
        
        logger.info(f"Rex filter: {promoted} PICKS, {passed} PASSES out of {len(predictions)} games")
        logger.info(f"Spread floor: {SPREAD_CONFIDENCE_FLOOR:.0%} | ML floor: {ML_CONFIDENCE_FLOOR:.0%}")
        
        return rex_predictions


def run_predictions(target_date: Optional[str] = None, tournament: bool = False,
                    seeds_file: Optional[str] = None, output_file: Optional[str] = None):
    """CLI entry point for Rex challenger engine."""
    engine = NCAABEngineRex(tournament_mode=tournament)
    
    td = date.fromisoformat(target_date) if target_date else date.today()
    
    seeds = None
    if seeds_file and os.path.exists(seeds_file):
        with open(seeds_file) as f:
            seeds = json.load(f)
    
    predictions = engine.predict_games(td, seeds)
    
    if not predictions:
        print("No games found.")
        return
    
    picks = [p for p in predictions if p.get('spread_status') == 'PICK']
    passes = [p for p in predictions if p.get('spread_status') == 'PASS']
    
    print(f"\n{'='*70}")
    print(f"  🦖 REX NCAAB CHALLENGER — {td.strftime('%A %B %d, %Y')}")
    print(f"  Spread floor: {SPREAD_CONFIDENCE_FLOOR:.0%} | ML floor: {ML_CONFIDENCE_FLOOR:.0%}")
    print(f"  {len(picks)} PICKS | {len(passes)} PASSES | {len(predictions)} total games")
    print(f"{'='*70}\n")
    
    if picks:
        print(f"  ── REAL PICKS (spread ≥ {SPREAD_CONFIDENCE_FLOOR:.0%}) ──\n")
        for i, p in enumerate(picks, 1):
            winner = p['predicted_winner']
            loser = p['away_team'] if winner == p['home_team'] else p['home_team']
            conf = p['confidence']
            upset = p.get('upset_composite', 0)
            
            conf_bar = '█' * int(conf * 20) + '░' * (20 - int(conf * 20))
            upset_flag = ' 🔥 UPSET' if upset > 0.5 else ''
            
            print(f"  {i:2d}. {winner} over {loser}")
            print(f"      ML: [{conf_bar}] {conf:.1%}{upset_flag}")
            if p.get('spread_pick'):
                s_conf = p['spread_confidence']
                s_bar = '█' * int(s_conf * 20) + '░' * (20 - int(s_conf * 20))
                print(f"      Spread: {p['spread_pick']} [{s_bar}] {s_conf:.1%}")
            if p.get('ou_pick'):
                print(f"      O/U: {p['ou_pick']}")
            print(f"      {p['home_team']} ({p.get('home_record','')}) vs {p['away_team']} ({p.get('away_record','')})")
            print()
    
    if passes:
        print(f"\n  ── PASSES (spread < {SPREAD_CONFIDENCE_FLOOR:.0%} = noise) ──\n")
        for p in passes:
            orig = p.get('spread_pick_original', '?')
            orig_conf = p.get('spread_confidence_original', 0)
            ml_conf = p['confidence']
            ml_winner = p['predicted_winner']
            print(f"      PASS: {p['away_team']} @ {p['home_team']}")
            print(f"            ML says {ml_winner} ({ml_conf:.1%}) | Spread was {orig} ({orig_conf:.1%}) ← not enough edge")
    
    # Save output
    out = output_file or f"rex_ncaab_picks_{td.isoformat()}.json"
    clean = []
    for p in predictions:
        pc = dict(p)
        pc.pop('factors', None)
        clean.append(pc)
    
    out_path = os.path.join(os.path.dirname(__file__), out)
    with open(out_path, 'w') as f:
        json.dump(clean, f, indent=2)
    print(f"\nSaved to {out}")
    
    # Also save side-by-side comparison data
    comparison = {
        'date': td.isoformat(),
        'engine': ENGINE_NAME,
        'version': ENGINE_VERSION,
        'spread_floor': SPREAD_CONFIDENCE_FLOOR,
        'ml_floor': ML_CONFIDENCE_FLOOR,
        'total_games': len(predictions),
        'spread_picks': len(picks),
        'spread_passes': len(passes),
        'picks_summary': [
            {
                'game': f"{p['away_team']} @ {p['home_team']}",
                'spread_pick': p.get('spread_pick'),
                'spread_confidence': p.get('spread_confidence'),
                'ml_pick': p['predicted_winner'],
                'ml_confidence': p['confidence'],
                'spread_status': p.get('spread_status'),
            }
            for p in predictions
        ]
    }
    comp_path = os.path.join(os.path.dirname(__file__), f"rex_comparison_{td.isoformat()}.json")
    with open(comp_path, 'w') as f:
        json.dump(comparison, f, indent=2)
    print(f"Comparison data: {comp_path}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Rex NCAAB Challenger Engine')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--tournament', action='store_true', help='March Madness mode')
    parser.add_argument('--seeds', type=str, help='Path to seeds JSON file')
    parser.add_argument('--output', type=str, help='Output file path')
    args = parser.parse_args()
    run_predictions(args.date, args.tournament, args.seeds, args.output)
