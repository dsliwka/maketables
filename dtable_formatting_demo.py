# Comprehensive demonstration of enhanced DTable formatting
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
import pandas as pd
from maketables import DTable

# Create sample data with various scales
np.random.seed(42)
df = pd.DataFrame({
    'small_values': np.random.normal(0.001, 0.0002, 100),  # Very small numbers
    'wages': np.random.normal(50000, 15000, 100),          # Medium numbers
    'large_values': np.random.normal(1000000, 200000, 100), # Large numbers
})

print("=== Comprehensive DTable Formatting Demonstration ===\n")

print("Sample data ranges:")
for col in df.columns:
    print(f"  {col}: {df[col].min():.6f} to {df[col].max():.6f}")

# Demo 1: Default intelligent formatting
print("\n1. Default formatting (intelligent defaults based on value ranges):")
print("DTable(df, ['small_values', 'wages', 'large_values'], stats=['mean', 'std', 'count'])")
table1 = DTable(df, ['small_values', 'wages', 'large_values'], stats=['mean', 'std', 'count'])
print("Output shows intelligent formatting based on value magnitude\n")

# Demo 2: Scientific notation for small values
print("2. Scientific notation for precise small values:")
format_specs_sci = {
    'mean': '.3e',
    'std': '.2e',
    'count': ',.0f'
}
print(f"format_spec = {format_specs_sci}")
table2 = DTable(df, ['small_values'], stats=['mean', 'std', 'count'], format_spec=format_specs_sci)

# Demo 3: Comma formatting for large values  
print("\n3. Comma separators for large values:")
format_specs_comma = {
    'mean': ',.0f',  # No decimals with commas
    'std': ',.0f',   # No decimals with commas
    'count': ',.0f'
}
print(f"format_spec = {format_specs_comma}")
table3 = DTable(df, ['large_values'], stats=['mean', 'std', 'count'], format_spec=format_specs_comma)

# Demo 4: Mixed precision formatting
print("\n4. Mixed precision for different statistics:")
format_specs_mixed = {
    'mean': '.1f',    # 1 decimal for means
    'std': '.3f',     # 3 decimals for standard deviations
    'min': '.0f',     # No decimals for min/max
    'max': '.0f',
    'count': ',.0f'   # Commas for counts
}
print(f"format_spec = {format_specs_mixed}")
table4 = DTable(df, ['wages'], stats=['mean', 'std', 'min', 'max', 'count'], 
               format_spec=format_specs_mixed)

# Demo 5: Combined statistics with custom formatting
print("\n5. Combined mean_std statistic with custom formatting:")
format_specs_combined = {
    'mean': ',.0f',   # Comma format for means in combined stat
    'std': '.2f'      # 2 decimals for std in combined stat
}
print(f"format_spec = {format_specs_combined}")
table5 = DTable(df, ['wages'], stats=['mean_std', 'count'], format_spec=format_specs_combined)

# Demo 6: Backward compatibility with digits parameter
print("\n6. Backward compatibility - digits parameter still works:")
print("DTable(df, ['wages'], digits=1)  # Old style still supported")
table6 = DTable(df, ['wages'], digits=1)

print("\n=== All demonstrations completed! ===")
print("\nKey benefits of enhanced DTable formatting:")
print("✓ Format specifiers provide precise control (.3f, .2e, ,.0f, etc.)")
print("✓ Per-statistic formatting (different formats for mean vs count)")
print("✓ Backward compatible with existing digits parameter")
print("✓ Intelligent defaults based on data magnitude")
print("✓ Scientific notation support for very small/large values")
print("✓ Combined statistics (mean_std) respect individual formatting")