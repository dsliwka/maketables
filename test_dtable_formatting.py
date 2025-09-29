# Test script for enhanced DTable formatting capabilities
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
from maketables import DTable

# Create sample data
np.random.seed(42)
df = pd.DataFrame({
    'wage': np.random.normal(50000, 15000, 100),
    'age': np.random.randint(22, 65, 100),
    'experience': np.random.randint(0, 40, 100),
})

print("=== Enhanced DTable Formatting Test ===\n")

# Test 1: Default behavior (backward compatible)
print("1. Default formatting (backward compatible):")
try:
    table1 = DTable(df, ['wage'], stats=['mean', 'std', 'count'], digits=2)
    print("✓ Default formatting works")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 2: Custom format specifications
print("\n2. Custom format specifications:")
try:
    format_specs = {
        'mean': ',.0f',     # Comma separators, no decimals
        'std': '.3f',       # 3 decimal places
        'count': ',.0f',    # Comma separators
    }
    table2 = DTable(df, ['wage'], stats=['mean', 'std', 'count'], format_spec=format_specs)
    print("✓ Custom format specifications work")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 3: Scientific notation
print("\n3. Scientific notation:")
try:
    format_specs_sci = {
        'mean': '.2e',      # Scientific notation
        'std': '.2e',
        'count': ',.0f'
    }
    table3 = DTable(df, ['wage'], stats=['mean', 'std', 'count'], format_spec=format_specs_sci)
    print("✓ Scientific notation works")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 4: Mixed with digits parameter
print("\n4. Format specs override digits parameter:")
try:
    format_specs_mixed = {'count': ',.0f'}  # Only specify count format
    table4 = DTable(df, ['wage'], stats=['mean', 'std', 'count'], 
                   format_spec=format_specs_mixed, digits=1)
    print("✓ Mixed format specs and digits work")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 5: Mean_std combined statistic
print("\n5. Mean_std combined statistic:")
try:
    format_specs_combined = {
        'mean': '.1f',
        'std': '.2f'
    }
    table5 = DTable(df, ['wage'], stats=['mean_std', 'count'], 
                   format_spec=format_specs_combined)
    print("✓ Mean_std combined statistic works")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n=== All tests completed! ===")