# Proposed formatting enhancements for DTable
# This demonstrates how DTable could be enhanced with format specifiers similar to ETable

import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

class DTableWithFormatting:
    """
    Enhanced DTable class with flexible formatting capabilities similar to ETable.
    
    Key additions:
    1. format_spec parameter - dictionary for per-statistic formatting
    2. Backward compatible digits parameter 
    3. Intelligent default formatting based on statistic type
    4. Support for format specifiers like .3f, .2e, ,.0f, etc.
    """
    
    # Class defaults for formatting different statistics
    DEFAULT_FORMAT_SPECS = {
        'mean': '.3f',
        'std': '.3f', 
        'count': ',.0f',
        'median': '.3f',
        'min': '.3f',
        'max': '.3f',
        'var': '.4f',
        'quantile': '.3f',
        'sum': ',.2f',
        'mean_std': None,  # handled separately
        'mean_newline_std': None,  # handled separately
    }
    
    def __init__(
        self,
        df: pd.DataFrame,
        vars: list,
        stats: Optional[list] = None,
        bycol: Optional[list[str]] = None,
        byrow: Optional[str] = None,
        labels: dict | None = None,
        stats_labels: dict | None = None,
        format_spec: Optional[Dict[str, str]] = None,
        digits: int = 2,
        notes: str = "",
        counts_row_below: bool = False,
        hide_stats: bool = False,
        observed: bool = False,
        **kwargs,
    ):
        """
        Enhanced DTable constructor with formatting capabilities.
        
        Parameters
        ----------
        format_spec : dict, optional
            Dictionary specifying format for each statistic type. Keys should match 
            statistic names, values should be format specifiers.
            Example: {'mean': '.3f', 'std': '.2f', 'count': ',.0f'}
            If None, uses intelligent defaults based on statistic type.
        digits : int, optional
            Number of decimal places for statistics display. This parameter is only
            applied when format_spec is None or when specific statistics are not
            specified in format_spec. Default is 2.
        """
        
        if stats is None:
            stats = ["count", "mean", "std"]
            
        # Handle format specifications - merge user provided with defaults
        self._setup_formatting(format_spec, digits)
        
        # ... rest of DTable initialization would go here
        
    def _setup_formatting(self, format_spec: Optional[Dict[str, str]], digits: int):
        """Set up formatting specifications for statistics."""
        if format_spec is None:
            # Use class defaults but convert digits to format specs where needed
            self.format_specs = dict(self.DEFAULT_FORMAT_SPECS)
            # Apply digits to statistics that don't have specific format specs
            digit_format = f'.{digits}f'
            for stat in ['mean', 'std', 'median', 'min', 'max']:
                if self.format_specs[stat] == '.3f':  # Only update defaults
                    self.format_specs[stat] = digit_format
        else:
            # Start with defaults and update with user specifications
            self.format_specs = dict(self.DEFAULT_FORMAT_SPECS)
            self.format_specs.update(format_spec)
            
            # For any stats not specified by user, use digits parameter
            digit_format = f'.{digits}f'
            for stat in format_spec.keys():
                if stat not in self.format_specs:
                    self.format_specs[stat] = digit_format
    
    def _format_statistic(self, value: float, stat_name: str) -> str:
        """Format a single statistic value according to its format specification."""
        if pd.isna(value) or (isinstance(value, float) and np.isnan(value)):
            return "-"
            
        format_spec = self.format_specs.get(stat_name, '.3f')
        return self._format_number(value, format_spec)
    
    def _format_number(self, x: float, format_spec: str = None) -> str:
        """Format a number with optional format specifier."""
        if pd.isna(x) or (isinstance(x, float) and np.isnan(x)):
            return "-"
        
        if format_spec is None:
            # Sensible default formatting
            abs_x = abs(x)
            
            if abs_x < 0.001 and abs_x > 0:
                return f"{x:.6f}".rstrip('0').rstrip('.')
            elif abs_x < 1:
                return f"{x:.3f}".rstrip('0').rstrip('.')
            elif abs_x < 1000:
                return f"{x:.3f}"
            elif abs_x >= 1000:
                if abs(x - round(x)) < 1e-10:  # essentially an integer
                    return f"{int(round(x)):,}"
                else:
                    return f"{x:,.2f}"
            else:
                return f"{x:.3f}"
        
        try:
            if format_spec == 'd':
                return f"{int(round(x)):d}"
            return f"{x:{format_spec}}"
        except (ValueError, TypeError):
            return self._format_number(x, None)
    
    def _format_mean_std_enhanced(self, data: pd.Series, newline: bool = True) -> str:
        """Enhanced mean_std formatting with format specifications."""
        mean = data.mean()
        std = data.std()
        
        mean_str = self._format_statistic(mean, 'mean')
        std_str = self._format_statistic(std, 'std')
        
        if newline:
            return f"{mean_str}\n({std_str})"
        else:
            return f"{mean_str} ({std_str})"


# Example usage demonstrations
def demonstrate_dtable_formatting():
    """Demonstrate the enhanced formatting capabilities."""
    
    # Create sample data
    np.random.seed(42)
    df = pd.DataFrame({
        'wage': np.random.normal(50000, 15000, 1000),
        'age': np.random.randint(22, 65, 1000),
        'experience': np.random.randint(0, 40, 1000),
        'education': np.random.choice(['High School', 'College', 'Graduate'], 1000),
    })
    
    # Example 1: Default formatting (backward compatible)
    print("=== Example 1: Default formatting (backward compatible) ===")
    print("DTable(df, ['wage', 'age'], digits=2)")
    print("Output would show means/stds with 2 decimal places\n")
    
    # Example 2: Custom format specifications
    print("=== Example 2: Custom format specifications ===")
    format_specs = {
        'mean': '.1f',      # 1 decimal for means
        'std': '.2f',       # 2 decimals for standard deviations  
        'count': ',.0f',    # Comma separators for counts
        'min': '.0f',       # No decimals for min/max
        'max': '.0f'
    }
    print(f"DTable(df, ['wage', 'age'], format_spec={format_specs})")
    print("Output would show customized formatting per statistic\n")
    
    # Example 3: Scientific notation for small values
    print("=== Example 3: Scientific notation ===")
    format_specs_sci = {
        'mean': '.2e',      # Scientific notation
        'std': '.2e',
        'count': ',.0f'
    }
    print(f"DTable(df, ['wage'], format_spec={format_specs_sci})")
    print("Output would show: 5.03e+04 (mean) and 1.49e+04 (std)\n")
    
    # Example 4: Mixed formatting
    print("=== Example 4: Mixed formatting for different statistics ===")
    format_specs_mixed = {
        'mean': ',.0f',     # Comma separators, no decimals
        'std': '.3f',       # 3 decimal places
        'count': ',.0f',    # Comma separators
        'min': ',.0f',      # Comma separators
        'max': ',.0f'       # Comma separators
    }
    print(f"DTable(df, ['wage'], stats=['mean', 'std', 'min', 'max', 'count'], format_spec={format_specs_mixed})")
    print("Output would show: 50,025 (mean), 14.932 (std), 2,949 (min), etc.\n")
    
    # Example 5: Format specifiers override digits parameter
    print("=== Example 5: Format specifiers override digits ===")
    format_specs_override = {'mean': '.4f', 'count': ',.0f'}
    print(f"DTable(df, ['wage'], format_spec={format_specs_override}, digits=1)")
    print("Mean uses .4f (4 decimals), std uses digits=1, count uses ,.0f\n")


if __name__ == "__main__":
    demonstrate_dtable_formatting()