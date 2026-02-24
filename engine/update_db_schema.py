"""
Update the results.db schema to support spread tracking and other enhancements
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def update_schema():
    """Add missing columns to support spread tracking"""
    conn = sqlite3.connect('results.db')
    c = conn.cursor()
    
    # Get current pick_results schema
    current_cols = [col[1] for col in c.execute('PRAGMA table_info(pick_results)').fetchall()]
    logger.info(f"Current pick_results columns: {current_cols}")
    
    # Add missing columns to pick_results
    new_pick_cols = [
        ('spread', 'REAL'),
        ('spread_pick', 'TEXT'),
        ('spread_correct', 'INTEGER'),
        ('pick_label', 'TEXT'),
        ('upset_score', 'REAL'),
        ('value_score', 'REAL')
    ]
    
    for col_name, col_type in new_pick_cols:
        if col_name not in current_cols:
            try:
                c.execute(f'ALTER TABLE pick_results ADD COLUMN {col_name} {col_type}')
                logger.info(f"Added column {col_name} to pick_results")
            except Exception as e:
                logger.error(f"Failed to add column {col_name}: {e}")
    
    # Get current daily_summaries schema
    current_summary_cols = [col[1] for col in c.execute('PRAGMA table_info(daily_summaries)').fetchall()]
    logger.info(f"Current daily_summaries columns: {current_summary_cols}")
    
    # Add missing columns to daily_summaries
    new_summary_cols = [
        ('spread_correct', 'INTEGER', '0'),
        ('spread_total', 'INTEGER', '0'),
        ('spread_accuracy', 'REAL', '0')
    ]
    
    for col_name, col_type, default_val in new_summary_cols:
        if col_name not in current_summary_cols:
            try:
                c.execute(f'ALTER TABLE daily_summaries ADD COLUMN {col_name} {col_type} DEFAULT {default_val}')
                logger.info(f"Added column {col_name} to daily_summaries")
            except Exception as e:
                logger.error(f"Failed to add column {col_name}: {e}")
    
    conn.commit()
    
    # Verify the updates
    logger.info("\nUpdated schemas:")
    new_pick_cols = [col[1] for col in c.execute('PRAGMA table_info(pick_results)').fetchall()]
    logger.info(f"pick_results: {new_pick_cols}")
    
    new_summary_cols = [col[1] for col in c.execute('PRAGMA table_info(daily_summaries)').fetchall()]
    logger.info(f"daily_summaries: {new_summary_cols}")
    
    conn.close()
    logger.info("Database schema update complete!")

if __name__ == '__main__':
    update_schema()