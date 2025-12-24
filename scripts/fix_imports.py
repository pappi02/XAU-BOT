"""
Script to fix imports in all subfolder files after reorganization.
"""

import os
import re

# Files that need import fixes (in subfolders)
files_to_fix = [
    'execution/scalper_executor.py',
    'execution/trade_executor.py',
    'indicators/rsi_divergence.py',
    'indicators/fibonacci.py',
    'risk/position_sizer.py',
    'risk/risk_manager.py',
    'strategies/expert_scalper.py',
    'strategies/multi_timeframe.py',
    'strategies/trend_reversal.py',
    'backtest/backtest_expert_scalper.py',
    'backtest/backtest_runner.py',
    'tests/test_expert_scalper.py',
    'tests/test_risk_manager.py',
]

import_fix_code = """import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""

def fix_file_imports(filepath):
    """Add sys path fix to a file if not already present."""
    if not os.path.exists(filepath):
        print(f"⚠️  File not found: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already fixed
    if 'sys.path.insert(0' in content:
        print(f"✓ Already fixed: {filepath}")
        return True
    
    # Find where to insert (after docstring, before first import)
    lines = content.split('\n')
    insert_index = 0
    in_docstring = False
    docstring_count = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Count triple quotes
        if '"""' in stripped or "'''" in stripped:
            docstring_count += stripped.count('"""') + stripped.count("'''")
            if docstring_count >= 2:  # Docstring closed
                insert_index = i + 1
                break
        elif docstring_count >= 2 and (stripped.startswith('import ') or stripped.startswith('from ')):
            insert_index = i
            break
        elif docstring_count == 0 and (stripped.startswith('import ') or stripped.startswith('from ')):
            insert_index = i
            break
    
    # Insert the import fix
    lines.insert(insert_index, import_fix_code)
    
    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ Fixed: {filepath}")
    return True

if __name__ == "__main__":
    print("=" * 60)
    print("FIXING IMPORTS IN SUBFOLDER FILES")
    print("=" * 60)
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base_dir)
    
    fixed_count = 0
    skipped_count = 0
    
    for file in files_to_fix:
        if os.path.exists(file):
            if fix_file_imports(file):
                fixed_count += 1
        else:
            print(f"⚠️  Skipped (not found): {file}")
            skipped_count += 1
    
    print(f"\n{'=' * 60}")
    print(f"✅ Fixed: {fixed_count} files")
    print(f"⚠️  Skipped: {skipped_count} files")
    print(f"{'=' * 60}")