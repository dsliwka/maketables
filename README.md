# MakeTables

A Python package for creating publication-ready tables from regression results (statsmodels, pyfixest, linearmodels), descriptive statistics, and balance tables with output to LaTeX, Word, and HTML via Great Tables. To get started, check out the [Getting Started Notebook](getting-started.ipynb).

## Overview

MakeTables provides a unified interface for generating tables from:
- Regression results (from [statsmodels](https://www.statsmodels.org/stable/index.html), [pyfixest](https://py-econometrics.github.io/pyfixest/pyfixest.html), or (still more experimental) [linearmodels](https://bashtage.github.io/linearmodels/)) and [Stata](https://www.stata.com/python/pystata19/)
- Descriptive statistics 
- Balance tables
- Custom data tables

The package supports multiple output formats including:
- Great Tables (HTML)
- LaTeX
- Microsoft Word (docx) documents

## Origin

MakeTables originated as the table output functionality within the [pyfixest](https://github.com/py-econometrics/pyfixest) package and has been moved to this standalone package to provide broader table creation capabilities also supporting other statistical packages.

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

### Regression Tables

#### with pyfixest
```python
import pyfixest as pf

# Fit your models here using pyfixest
est1 = pf.feols("mpg ~ weight", data=df)
est2 = pf.feols("mpg ~ weight + length", data=df)

# Make the table
mt.ETable([est1, est2])
```

#### with statsmodels
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


## License

This project is licensed under the MIT License - see the LICENSE file for details.



## Acknowledgments

- Built on the excellent [pyfixest](https://github.com/py-econometrics/pyfixest) package for econometric models
- Uses [Great Tables](https://github.com/posit-dev/great-tables) for beautiful HTML table output