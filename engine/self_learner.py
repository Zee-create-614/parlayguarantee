"""
Self-Learning System for Engine v2
Handles weight recalibration, Bayesian updating, and performance tracking
"""

import sqlite3
import json
import logging
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import numpy as np

logger = logging.getLogger(__name__)

class SelfLearner:
    """
    Manages the self-learning capabilities of Engine v2:
    - Tracks prediction accuracy per factor
    - Recalibrates factor weights based on historical performance
    - Bayesian updating of confidence levels
    - Performance analytics and reporting
    """
    
    def __init__(self, db_path: str = "engine_data.db"):
        self.db_path = db_path
        
        # Default factor weights - based on basketball analytics research
        self.default_weights = {
            # Team Performance (35% total weight)
            'season_win_pct': 0.08,
            'home_win_pct': 0.05,
            'away_win_pct': 0.05,
            'last_10_record': 0.06,
            'last_5_record': 0.04,
            'offensive_rating': 0.04,
            'defensive_rating': 0.05,
            'net_rating': 0.06,
            'pace': 0.0,  # REMOVED: negatively correlated
            'ppg': 0.03,
            'points_allowed': 0.03,
            
            # Situational (25% total weight) 
            'rest_days': 0.10,  # B2B penalty is significant — BOOSTED (corr +0.1172)
            'day_of_week': 0.0,  # REMOVED v5: negatively correlated
            'game_time': 0.02,
            'travel_distance': 0.04,
            'timezone_change': 0.03,
            'days_since_last': 0.02,
            
            # Matchup (15% total weight)
            'head_to_head': 0.04,
            'division_rivalry': 0.0,  # REMOVED v5: negatively correlated
            'conference_game': 0.01,
            
            # Advanced (20% total weight)
            'strength_of_schedule': 0.03,
            'clutch_performance': 0.06,  # BOOSTED (corr +0.0963)
            'turnover_diff': 0.05,  # BOOSTED (corr +0.1289)
            'rebound_diff': 0.03,
            'ft_rate_diff': 0.0,  # REMOVED v5: negatively correlated
            'three_pt_pct': 0.03,
            'assists_pg': 0.0,  # REMOVED v5: negatively correlated
            'defensive_activity': 0.02,
            
            # Injuries (3% total weight)
            'key_player_status': 0.02,
            'star_player_penalty': 0.01,
            
            # Market (2% total weight)  
            'line_movement': 0.01,
            'public_betting': 0.005,
            'closing_line_value': 0.005,
            
            # Home court advantage
            'home_court': 0.035,  # ~3.5% home court boost
            
            # New v3 factors
            'streak_diff': 0.03,
            'scoring_margin_trend': 0.07,  # BOOSTED (corr +0.1228)
            'away_road_trip': 0.0,  # REMOVED v5: negatively correlated
            'miles_traveled_diff': 0.02,
            'overtime_fatigue': 0.0,  # REMOVED v5: negatively correlated
            'revenge_game': 0.02,
            'trap_game': 0.02,
            'altitude_factor': 0.03,
            'arena_hostility': 0.0,  # REMOVED: negatively correlated
            'marquee_matchup': 0.0,  # REMOVED: negatively correlated
            'b2b_status': 0.07,  # BOOSTED (corr +0.1038)
            'schedule_density': 0.05,  # BOOSTED (corr +0.1109)
            'last_3_record': 0.03,
            'oreb_diff': 0.02,
            'three_pt_volume': 0.01,
        }
        
        # Initialize database after default weights are set
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for self-learning data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Predictions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                game_date DATE,
                home_team TEXT,
                away_team TEXT,
                predicted_winner TEXT,
                confidence REAL,
                all_factors_json TEXT,
                actual_result TEXT,
                correct INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_id)
            )
        ''')
        
        # Factor weights table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_weights (
                factor_name TEXT PRIMARY KEY,
                weight REAL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                historical_accuracy REAL,
                sample_size INTEGER DEFAULT 0
            )
        ''')
        
        # Model performance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE,
                total_predictions INTEGER,
                correct_predictions INTEGER,
                accuracy REAL,
                avg_confidence REAL,
                calibration_score REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        ''')
        
        # Factor performance tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS factor_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT,
                date DATE,
                predictions_count INTEGER,
                correct_predictions INTEGER,
                accuracy REAL,
                avg_factor_value REAL,
                correlation_with_outcome REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_name, date)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Initialize default weights if table is empty
        self.init_default_weights()
    
    def get_default_weights(self) -> Dict[str, float]:
        """Get default factor weights"""
        return self.default_weights
    
    def init_default_weights(self):
        """Initialize factor weights with defaults if not present"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for factor, weight in self.default_weights.items():
            cursor.execute('''
                INSERT OR IGNORE INTO factor_weights (factor_name, weight, historical_accuracy)
                VALUES (?, ?, ?)
            ''', (factor, weight, 0.5))  # Start with 50% assumed accuracy
        
        conn.commit()
        conn.close()
    
    def load_weights(self) -> Dict[str, float]:
        """Load current factor weights from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT factor_name, weight FROM factor_weights')
        weights = dict(cursor.fetchall())
        
        conn.close()
        
        # Use defaults for any missing factors 
        default_weights = self.get_default_weights()
        for factor in default_weights:
            if factor not in weights:
                weights[factor] = default_weights[factor]
        
        return weights
    
    def record_prediction(self, game_id: str, game_date: date, home_team: str, 
                         away_team: str, predicted_winner: str, confidence: float,
                         all_factors: Dict) -> bool:
        """Record a prediction for later evaluation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO predictions
                (game_id, game_date, home_team, away_team, predicted_winner, 
                 confidence, all_factors_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                game_id, game_date.isoformat(), home_team, away_team,
                predicted_winner, confidence, json.dumps(all_factors)
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error recording prediction: {e}")
            conn.close()
            return False
    
    def record_result(self, game_id: str, actual_winner: str) -> bool:
        """Record actual game result and mark prediction as correct/incorrect"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Update the prediction with actual result
            cursor.execute('''
                UPDATE predictions 
                SET actual_result = ?, correct = (predicted_winner = ?)
                WHERE game_id = ?
            ''', (actual_winner, actual_winner, game_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                
                # Trigger factor performance analysis
                self.update_factor_performance(game_id)
                return True
            else:
                logger.warning(f"No prediction found for game_id: {game_id}")
                conn.close()
                return False
                
        except Exception as e:
            logger.error(f"Error recording result: {e}")
            conn.close()
            return False
    
    def update_factor_performance(self, game_id: str):
        """Update factor performance metrics after result is recorded"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get the prediction with result
        cursor.execute('''
            SELECT game_date, all_factors_json, correct
            FROM predictions 
            WHERE game_id = ? AND actual_result IS NOT NULL
        ''', (game_id,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return
        
        game_date, factors_json, correct = result
        factors = json.loads(factors_json)
        
        # Update each factor's performance
        for factor_name, factor_value in factors.items():
            if factor_name in self.default_weights:
                cursor.execute('''
                    INSERT OR REPLACE INTO factor_performance
                    (factor_name, date, predictions_count, correct_predictions, 
                     accuracy, avg_factor_value)
                    VALUES (?, ?, 
                        COALESCE((SELECT predictions_count FROM factor_performance 
                                 WHERE factor_name = ? AND date = ?), 0) + 1,
                        COALESCE((SELECT correct_predictions FROM factor_performance 
                                 WHERE factor_name = ? AND date = ?), 0) + ?,
                        CASE WHEN COALESCE((SELECT predictions_count FROM factor_performance 
                                           WHERE factor_name = ? AND date = ?), 0) + 1 > 0 
                             THEN CAST((COALESCE((SELECT correct_predictions FROM factor_performance 
                                               WHERE factor_name = ? AND date = ?), 0) + ?) AS REAL) / 
                                     (COALESCE((SELECT predictions_count FROM factor_performance 
                                              WHERE factor_name = ? AND date = ?), 0) + 1)
                             ELSE 0.5 END,
                        ?)
                ''', (
                    factor_name, game_date,
                    factor_name, game_date,  # for predictions_count lookup
                    factor_name, game_date, correct,  # for correct_predictions lookup  
                    factor_name, game_date,  # for accuracy calculation
                    factor_name, game_date, correct,  # for accuracy numerator
                    factor_name, game_date,  # for accuracy denominator
                    factor_value
                ))
        
        conn.commit()
        conn.close()
    
    def recalibrate_weights(self, min_sample_size: int = 50) -> Dict[str, float]:
        """
        Recalibrate factor weights based on historical performance
        Uses correlation analysis and accuracy metrics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all completed predictions
        cursor.execute('''
            SELECT all_factors_json, correct 
            FROM predictions 
            WHERE actual_result IS NOT NULL
        ''')
        
        predictions = cursor.fetchall()
        
        if len(predictions) < min_sample_size:
            logger.info(f"Not enough samples for recalibration ({len(predictions)} < {min_sample_size})")
            conn.close()
            return self.load_weights()
        
        # Analyze factor performance
        factor_accuracies = defaultdict(list)
        factor_correlations = {}
        
        for factors_json, correct in predictions:
            factors = json.loads(factors_json)
            
            for factor_name, factor_value in factors.items():
                if factor_name in self.default_weights:
                    factor_accuracies[factor_name].append((factor_value, correct))
        
        # Calculate correlation between each factor and outcomes
        new_weights = {}
        
        for factor_name in self.default_weights:
            if factor_name not in factor_accuracies or len(factor_accuracies[factor_name]) < 10:
                # Not enough data, keep default
                new_weights[factor_name] = self.default_weights[factor_name]
                continue
            
            values_and_outcomes = factor_accuracies[factor_name]
            values = [x[0] for x in values_and_outcomes]
            outcomes = [x[1] for x in values_and_outcomes]
            
            # Calculate correlation coefficient
            correlation = self.calculate_correlation(values, outcomes)
            
            # Calculate accuracy when this factor is above average
            factor_mean = np.mean(values)
            above_avg_outcomes = [outcome for value, outcome in values_and_outcomes if value > factor_mean]
            accuracy_above_avg = np.mean(above_avg_outcomes) if above_avg_outcomes else 0.5
            
            # Combine correlation and accuracy to determine new weight
            # Higher correlation and accuracy = higher weight
            base_weight = self.default_weights[factor_name]
            
            # Weight adjustment factor (0.5 to 2.0)
            correlation_multiplier = 1.0 + (abs(correlation) * 0.5)
            accuracy_multiplier = 1.0 + ((accuracy_above_avg - 0.5) * 0.5)
            
            adjustment = (correlation_multiplier + accuracy_multiplier) / 2
            new_weight = base_weight * adjustment
            
            # Constrain to reasonable bounds
            new_weight = max(0.001, min(0.15, new_weight))
            
            new_weights[factor_name] = new_weight
            factor_correlations[factor_name] = correlation
        
        # Normalize weights to sum to 1.0
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            for factor in new_weights:
                new_weights[factor] /= total_weight
        
        # Update database
        timestamp = datetime.now()
        for factor_name, new_weight in new_weights.items():
            accuracy = np.mean([outcome for _, outcome in factor_accuracies.get(factor_name, [(0, 0.5)])])
            
            cursor.execute('''
                UPDATE factor_weights 
                SET weight = ?, last_updated = ?, historical_accuracy = ?,
                    sample_size = ?
                WHERE factor_name = ?
            ''', (
                new_weight, timestamp, accuracy, 
                len(factor_accuracies.get(factor_name, [])), factor_name
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Recalibrated weights based on {len(predictions)} predictions")
        
        # Log significant changes
        old_weights = self.default_weights
        for factor in new_weights:
            change = abs(new_weights[factor] - old_weights[factor])
            if change > 0.01:  # 1% change threshold
                logger.info(f"Weight change {factor}: {old_weights[factor]:.3f} -> {new_weights[factor]:.3f}")
        
        return new_weights
    
    def calculate_correlation(self, values: List[float], outcomes: List[int]) -> float:
        """Calculate Pearson correlation coefficient"""
        if len(values) != len(outcomes) or len(values) < 2:
            return 0.0
        
        n = len(values)
        sum_x = sum(values)
        sum_y = sum(outcomes)
        sum_xy = sum(x * y for x, y in zip(values, outcomes))
        sum_x2 = sum(x * x for x in values)
        sum_y2 = sum(y * y for y in outcomes)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    def bayesian_update_confidence(self, base_confidence: float, 
                                  historical_performance: Dict) -> float:
        """
        Apply Bayesian updating to confidence based on historical performance
        """
        overall_accuracy = historical_performance.get('overall_accuracy', 0.5)
        sample_size = historical_performance.get('sample_size', 0)
        
        # Bayesian prior - start with base confidence  
        prior = base_confidence
        
        # Evidence - how well have we done historically?
        if sample_size < 10:
            # Not enough data, stick close to prior
            posterior = prior * 0.8 + overall_accuracy * 0.2
        else:
            # More data, trust the evidence more
            confidence_in_evidence = min(0.7, sample_size / 100)  # Max 70% trust in evidence
            posterior = prior * (1 - confidence_in_evidence) + overall_accuracy * confidence_in_evidence
        
        # Ensure reasonable bounds
        return max(0.1, min(0.95, posterior))
    
    def get_accuracy_report(self, days_back: int = 30) -> Dict:
        """Generate comprehensive accuracy report"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_date = (date.today() - timedelta(days=days_back)).isoformat()
        
        # Overall performance
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(correct) as correct,
                AVG(CAST(correct AS REAL)) as accuracy,
                AVG(confidence) as avg_confidence
            FROM predictions 
            WHERE actual_result IS NOT NULL AND game_date >= ?
        ''', (cutoff_date,))
        
        overall = cursor.fetchone()
        
        # Per-factor accuracy
        cursor.execute('''
            SELECT 
                factor_name,
                AVG(accuracy) as avg_accuracy,
                SUM(predictions_count) as total_predictions,
                MAX(date) as last_updated
            FROM factor_performance 
            WHERE date >= ?
            GROUP BY factor_name
        ''', (cutoff_date,))
        
        factor_performance = {row[0]: {
            'accuracy': row[1],
            'predictions': row[2], 
            'last_updated': row[3]
        } for row in cursor.fetchall()}
        
        # Daily performance trend
        cursor.execute('''
            SELECT 
                game_date,
                COUNT(*) as predictions,
                AVG(CAST(correct AS REAL)) as accuracy
            FROM predictions 
            WHERE actual_result IS NOT NULL AND game_date >= ?
            GROUP BY game_date
            ORDER BY game_date DESC
            LIMIT 10
        ''', (cutoff_date,))
        
        daily_performance = [{'date': row[0], 'predictions': row[1], 'accuracy': row[2]} 
                           for row in cursor.fetchall()]
        
        conn.close()
        
        report = {
            'overall': {
                'total_predictions': overall[0],
                'correct_predictions': overall[1],
                'accuracy': overall[2] or 0.0,
                'average_confidence': overall[3] or 0.0
            },
            'factor_performance': factor_performance,
            'daily_trend': daily_performance,
            'report_period': f"Last {days_back} days",
            'generated_at': datetime.now().isoformat()
        }
        
        return report
    
    def get_calibration_score(self) -> float:
        """
        Calculate model calibration - how well confidence matches actual accuracy
        Perfect calibration = 1.0, poor calibration approaches 0
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT confidence, correct 
            FROM predictions 
            WHERE actual_result IS NOT NULL
        ''')
        
        predictions = cursor.fetchall()
        conn.close()
        
        if len(predictions) < 20:
            return 0.5  # Not enough data
        
        # Bin predictions by confidence levels
        bins = [(i/10, (i+1)/10) for i in range(10)]  # 0.0-0.1, 0.1-0.2, etc.
        
        calibration_errors = []
        
        for bin_start, bin_end in bins:
            bin_predictions = [(conf, correct) for conf, correct in predictions 
                              if bin_start <= conf < bin_end]
            
            if len(bin_predictions) < 5:  # Skip bins with too few predictions
                continue
            
            avg_confidence = np.mean([conf for conf, _ in bin_predictions])
            actual_accuracy = np.mean([correct for _, correct in bin_predictions])
            
            # Calibration error = |predicted accuracy - actual accuracy|
            calibration_error = abs(avg_confidence - actual_accuracy)
            calibration_errors.append(calibration_error)
        
        if not calibration_errors:
            return 0.5
        
        # Average calibration error
        avg_calibration_error = np.mean(calibration_errors)
        
        # Convert to calibration score (lower error = higher score)
        calibration_score = max(0.0, 1.0 - (avg_calibration_error * 2))
        
        return calibration_score


if __name__ == "__main__":
    # Test the self-learning system
    logging.basicConfig(level=logging.INFO)
    
    learner = SelfLearner()
    
    # Simulate some predictions and results
    from datetime import date
    import uuid
    
    # Test recording predictions
    test_factors = {
        'season_win_pct': 0.65,
        'rest_days': 1.0,
        'home_win_pct': 0.70,
        'travel_distance': 500.0
    }
    
    game_id = str(uuid.uuid4())
    learner.record_prediction(
        game_id, date.today(), "Los Angeles Lakers", "Boston Celtics", 
        "Los Angeles Lakers", 0.63, test_factors
    )
    
    # Simulate recording result
    learner.record_result(game_id, "Los Angeles Lakers")  # Correct prediction
    
    # Get accuracy report
    report = learner.get_accuracy_report()
    print("Accuracy Report:")
    print(json.dumps(report, indent=2))
    
    # Test weight recalibration (needs more data in practice)
    weights = learner.recalibrate_weights(min_sample_size=1)
    print(f"\nCurrent weights: {len(weights)} factors")
    for factor, weight in sorted(weights.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {factor}: {weight:.4f}")