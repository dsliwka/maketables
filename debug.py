# run a regression with statsmodels, then create ETable
import statsmodels.formula.api as smf

import maketables as mt

# Load sample dataset
df = pd.read_csv("data/salaries.csv")

# Estimate regressions for examples
est1 = smf.ols("logwage ~ age", data=df)
mt.ETable([est1])
