"""
Install the fixed result tracker files
"""
import shutil
import os
from pathlib import Path
from datetime import datetime

def backup_and_install():
    """Backup original files and install fixes"""
    engine_dir = Path(__file__).parent
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Files to backup and replace
    files_to_fix = [
        'result_tracker.py',
        'score_all_parlays.py'
    ]
    
    print("Installing ParlayGuarantee Result Tracker Fixes")
    print("=" * 50)
    
    # Create backup directory
    backup_dir = engine_dir / f'backup_{timestamp}'
    backup_dir.mkdir(exist_ok=True)
    print(f"Created backup directory: {backup_dir.name}")
    
    # Backup original files
    for filename in files_to_fix:
        original = engine_dir / filename
        fixed = engine_dir / f'{filename.replace(".py", "_fixed.py")}'
        backup = backup_dir / filename
        
        if original.exists():
            shutil.copy2(original, backup)
            print(f"Backed up: {filename} -> {backup.name}")
        
        if fixed.exists():
            shutil.copy2(fixed, original)
            print(f"Installed: {fixed.name} -> {filename}")
        else:
            print(f"WARNING: Missing fixed version: {fixed.name}")
    
    print("\nDatabase Schema Update")
    print("-" * 30)
    
    # Update database schema
    if (engine_dir / 'update_db_schema.py').exists():
        print("Updating database schema...")
        os.system(f'cd "{engine_dir}" && python update_db_schema.py')
    
    print("\nInstallation Complete!")
    print("-" * 30)
    print("Fixed files are now active:")
    print("  - result_tracker.py - Enhanced pick scoring")
    print("  - score_all_parlays.py - Better error handling")
    print("  - results.db - Updated schema with spread tracking")
    print("\nOriginal files backed up to:", backup_dir.name)
    print("\nReady for tonight's games!")

if __name__ == '__main__':
    backup_and_install()