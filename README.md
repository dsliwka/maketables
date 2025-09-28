# MakeTables

A Python package for creating publication-ready tables from statistical models and descriptive statistics.

## Overview

MakeTables provides a unified interface for generating tables from:
- Regression results (from [statsmodels](https://www.statsmodels.org/stable/index.html), [pyfixest](https://py-econometrics.github.io/pyfixest/pyfixest.html), or (still more experimental) [linearmodels](https://bashtage.github.io/linearmodels/))
- Descriptive statistics 
- Custom data tables

The package supports multiple output formats including:
- Great Tables (HTML)
- LaTeX
- Microsoft Word (docx) documents


## Installation

### From PyPI (when published)
```bash
pip install maketables
```

### Development Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/maketables.git
cd maketables

# Install in development mode
pip install -e .
```

## Quick Start

### Descriptive Statistics Table

```python
import pandas as pd
import maketables as mt

# Load your data (here using a sample Stata dataset with the import_dta function that also stores variable labels)
df = mt.import_dta("https://www.stata-press.com/data/r18/auto.dta")


# Create descriptive statistics table
mt.DTable(df, vars=["mpg","weight","length"], bycol=["foreign"])
```

**Sample Output:**

|                | Domestic | | | Foreign | | |
|----------------|----------|-------|-------|---------|-------|-------|
|                | N | Mean | Std. Dev. | N | Mean | Std. Dev. |
| Mileage (mpg)  | 52 | 19.83 | 4.74 | 22 | 24.77 | 6.61 |
| Weight (lbs.)  | 52 | 3,317.12 | 695.36 | 22 | 2,315.91 | 433.00 |
| Length (in.)   | 52 | 196.13 | 20.05 | 22 | 168.55 | 13.68 |

### Regression Tables

## With pyfixest
```python
import pyfixest as pf

# Fit your models here using pyfixest
est1 = pf.feols("mpg ~ weight", data=df)
est2 = pf.feols("mpg ~ weight + length", data=df)

# Make the table
mt.ETable([est1, est2])
```
**Sample Output:** [View HTML table](docs/tab2.html)

## With statsmodels
```python
import statsmodels.formula.api as smf

# Generate a dummy variable and label it
df["foreign_i"] = (df["foreign"] == "Foreign")*1
mt.set_var_labels(df, {"foreign_i": "Foreign (indicator)"})

# Fit your models 
est1 = smf.ols("foreign_i ~ weight + length + price", data=df).fit()
est2 = smf.probit("foreign_i ~ weight + length + price", data=df).fit(disp=0)

# Make the table
mt.ETable([est1, est2], model_stats=["N","r2","pseudo_r2",""], model_heads=["OLS","Probit"])
```
**Sample Output:** [View HTML table](docs/tab3.html)


## Main Classes

### `MTable`
Base class for all table types with common functionality:
- Multiple output formats (Great Tables, LaTeX, Word)
- Flexible styling and formatting options
- Save and export capabilities
- Can also update tables in existing word documents
- Adapted for use in Jupyter Notebooks and for quarto use (tables automatically rendered as html in notebooks and as latex when rendering to pdf in quarto)


### `DTable`
Extends MTable for descriptive statistics:
- Automatic calculation of summary statistics
- Grouping by categorical variables (rows and columns)
- Customizable statistic labels and formatting

### `ETable`
Extends MTable for econometric model results:
- Support for statsmodels, pyfixest, and (more experimental) linearmodels 
- Many layout options (relabelling of variables, keep/drop, choice of reported statistics, column headings,...)

### `BTable`
Extends MTable for simple balance tables.

## Key Features

- **Multiple Output Formats**: Generate tables as Great Tables (HTML), LaTeX, or Word documents 
- **Statistical Integration**: Native support for statsmodels, pyfixest, linearmodels
- **Flexible Formatting**: Customizable labels, notes, significance levels, and styling
- **Data Import**: Built-in Stata file (.dta) import/export with variable label preservation
- **Extensible**: Plugin system for custom model extractors

## Output Formats

### Great Tables (HTML)
```python
table = DTable(df, vars=['x1', 'x2'], type='gt')
table.make()  # Displays HTML table
```

### LaTeX
```python
table = DTable(df, vars=['x1', 'x2'], type='tex')
latex_code = table.make()  # Returns LaTeX string
```

### Word Documents
```python
table = DTable(df, vars=['x1', 'x2'], type='docx')
table.save('output.docx')  # Saves to Word file
```

## Dependencies

- pandas (>=1.3.0)
- numpy (>=1.20.0) 
- great-tables (>=0.2.0)
- tabulate (>=0.9.0)
- pyfixest (>=0.13.0)
- python-docx (>=0.8.11)
- ipython (>=7.0.0)


## License

This project is licensed under the MIT License - see the LICENSE file for details.

```

## Acknowledgments

- Built on the excellent [pyfixest](https://github.com/py-econometrics/pyfixest) package for econometric models
- Uses [Great Tables](https://github.com/posit-dev/great-tables) for beautiful HTML table output