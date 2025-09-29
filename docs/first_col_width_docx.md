# First Column Width Functionality for DOCX Output

The `MTable` class now supports setting a custom width for the first column in DOCX output. This feature is available through several methods:

## Usage Examples

### 1. Using the `make()` method

```python
import pandas as pd
from maketables.mtable import MTable

# Create sample data
df = pd.DataFrame({
    'Treatment A': [1.23, 2.45, 3.67],
    'Treatment B': [4.89, 5.12, 6.34],
    'Treatment C': [7.56, 8.78, 9.90]
}, index=['Group 1', 'Group 2', 'Group 3'])

# Create table with custom first column width
table = MTable(df, caption="Table with Custom First Column Width")

# Generate DOCX with 2.5 inch first column
doc = table.make(type="docx", first_col_width="2.5in")
doc.save("my_table.docx")
```

### 2. Using the `save()` method

```python
# Save directly with custom first column width
table.save(
    type="docx", 
    file_name="table_custom_width.docx", 
    first_col_width="4cm"
)
```

### 3. Using the `docx_style` parameter

```python
# Set first column width through style dictionary
table.save(
    type="docx", 
    file_name="table_style_width.docx", 
    docx_style={"first_col_width": "120pt"}
)
```

### 4. Using the `update_docx()` method

```python
# Update existing document with custom first column width
table.update_docx(
    file_name="existing_document.docx",
    first_col_width="3.5in"
)
```

## Supported Units

The `first_col_width` parameter accepts the following units:

- **Inches**: `"2.5in"`, `"1.75in"`
- **Centimeters**: `"4cm"`, `"6.5cm"`
- **Points**: `"120pt"`, `"90pt"`
- **No unit (defaults to points)**: `"100"`, `"150"`

## Default Behavior

If `first_col_width` is not specified or is set to `None`, the first column will use automatic width sizing based on content.

## Global Default

You can set a global default for all tables by modifying the class default:

```python
# Set global default first column width
MTable.DEFAULT_DOCX_STYLE["first_col_width"] = "2in"

# All subsequent tables will use this default unless overridden
table1 = MTable(df1)
table1.save(type="docx", file_name="table1.docx")  # Uses 2in width

# Override for specific table
table2 = MTable(df2)
table2.save(type="docx", file_name="table2.docx", first_col_width="3cm")  # Uses 3cm width
```