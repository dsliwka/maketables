# Format Specifier System for ETable

The `coef_fmt` parameter supports Python-style format specifiers for complete control over number formatting. The system provides sensible defaults without scientific notation and eliminates the need for separate formatting parameters.

## Default Behavior (No Parameters Needed)

The system uses intelligent defaults based on number magnitude:
- **Very small numbers** (< 0.001): 6 decimals, strip trailing zeros → `0.001`
- **Small numbers** (< 1): 3 decimals, strip trailing zeros → `0.123`  
- **Medium numbers** (1-999): 3 decimal places → `1.235`
- **Large numbers** (≥ 1000): Comma separators, integers when appropriate → `1,234,567`

```python
# Default formatting - no parameters needed
ETable(models, coef_fmt="b \n (se)")
# Automatically handles: 0.001, 1.235, 1,234.57, 1,234,567
```

## Format Specifiers

### Decimal Places
```python
ETable(models, coef_fmt="b:.4f \n (se:.2f)")
# Output: 1.2340 \n (0.46)
```

### Scientific Notation (when needed)
```python
ETable(models, coef_fmt="b:.2e \n (se:.2e)")
# Output: 1.23e+00 \n (4.56e-01)
```

### Comma Thousands Separator
```python
ETable(models, coef_fmt="b:,.0f \n (se:.3f)")
# Output: 1,234 \n (0.456)
```

### Integer Formatting
```python
ETable(models, coef_fmt="b:d \n (se:.3f)")
# Output: 1234 \n (0.456)
```

## Advanced Examples

### Mixed Formatting
```python
ETable(models, coef_fmt="b:,.2f [t:.1f] \n (se:.3f)")
# Output: 1,234.57 [2.7] \n (0.456)
```

### Economic Data
```python
ETable(models, coef_fmt="b:$,.0f \n (se:,.0f)")
# Output: $1,234 \n (456)
```

## Format Specifier Reference

- `.Nf` - Fixed point with N decimal places
- `.Ne` - Scientific notation with N decimal places  
- `,.Nf` - Comma separator with N decimal places
- `d` - Integer formatting
- Custom prefixes/suffixes as literal text

The system follows Python's string formatting conventions and provides sensible defaults that avoid scientific notation for typical statistical values.