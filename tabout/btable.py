import numpy as np
import pandas as pd
import pyfixest as pf
from typing import Optional, Union, List, Dict

from .dtable import DTable


class BTable(DTable):
    """
    Balancing table: descriptive stats by group + per-variable p-values from group tests.

    Inherits DTable to build the stats table, then adds a 'p-value' column:
    - For 2 groups: p-value of the single group indicator (t/z test).
    - For >2 groups: joint Wald test that all group indicators are zero.

    Parameters
    ----------
    df : pd.DataFrame
        Source data.
    vars : list[str]
        Variables to include.
    group : str
        Grouping column in df.
    labels : dict, optional
        Variable labels (used for display and in notes).
    digits : int, optional
        Rounding for stats in the DTable. Default 2.
    pdigits : int, optional
        Rounding for p-values. Default 3.
    vcov : str | dict, optional
        VCV for the p-value models ("iid", "hetero", "HC1", "HC2", "HC3" or {"CRV1": "cluster"}). Default "iid".
    fixed_effects : list[str] | None
        Optional fixed effects for the p-value models (cosmetic in notes). Default None.
    stats : list[str] | None
        Stats for DTable (default ["mean", "std"]).
    stats_labels : dict[str, str] | None
        Custom labels for stats (used in header/notes).
    hide_stats : bool
        Hide stats names in the header (list them in notes instead). Default False.
    counts_row_below : bool
        If True and balanced N, show a single counts row at bottom. Default False.
    observed : bool
        Only consider observed categories when grouping. Default False.
    notes : str
        Custom notes. If "", a default is generated mentioning stats/SE/FE.
    kwargs : dict
        Passed through to DTable/MTable (e.g., caption, tab_label, rgroup_display).
    """

    def __init__(
        self,
        df: pd.DataFrame,
        vars: List[str],
        group: str,
        *,
        labels: Optional[Dict[str, str]] = None,
        digits: int = 2,
        pdigits: int = 3,
        vcov: Union[str, Dict[str, str]] = "iid",
        fixed_effects: Optional[List[str]] = None,
        stats: Optional[List[str]] = None,
        stats_labels: Optional[Dict[str, str]] = None,
        hide_stats: bool = False,
        counts_row_below: bool = False,
        observed: bool = False,
        notes: str = "",
        **kwargs,
    ):
        assert group in df.columns, f"group column '{group}' not in DataFrame."
        for v in vars:
            assert v in df.columns, f"Variable '{v}' not in DataFrame."

        labels = {} if labels is None else dict(labels)
        stats = ["mean", "std"] if stats is None else list(stats)
        stats_labels = {} if stats_labels is None else dict(stats_labels)

        # Build the descriptive stats table via DTable
        super().__init__(
            df=df,
            vars=vars,
            stats=stats,
            bycol=[group],
            byrow=None,
            labels=labels,
            stats_labels=stats_labels,
            digits=digits,
            notes="", 
            counts_row_below=counts_row_below,
            hide_stats=hide_stats,
            observed=observed,
            **kwargs,
        )

        # Compute p-values per variable from a group-effects regression
        n_groups = df[group].nunique()
        pvals = pd.Series(index=self.df.index, dtype=float)

        fe_suffix = ""
        if fixed_effects:
            fe_suffix = f" | {'.'.join(fixed_effects)}"

        for i, var in enumerate(vars):
            formula = f"{var} ~ i({group}){fe_suffix}"
            model = pf.feols(formula, data=df, vcov=vcov)

            if n_groups == 2:
                # p-value of the single group indicator
                pval = float(model._pvalue[1])
            else:
                # Joint test of all group indicators
                k = model._k
                R = np.zeros((k - 1, k))
                for j in range(1, k):
                    R[j - 1, j] = 1
                q = np.zeros(k - 1)
                pval = float(model.wald_test(R, q, distribution="chi2").pvalue)

            pvals.iloc[i] = round(pval, pdigits)

        # Append the p-value column; handle MultiIndex columns gracefully
        if isinstance(self.df.columns, pd.MultiIndex):
            new_key = tuple(["p-value"] + [""] * (self.df.columns.nlevels - 1))
            self.df[new_key] = pvals
        else:
            self.df["p-value"] = pvals

        # Build default notes if not provided
        if notes == "":
            # Stats dictionary (for notes when hidden)
            sdict = {
                "count": "N",
                "mean": "Mean",
                "std": "Std. Dev.",
                "mean_std": "Mean (Std. Dev.)",
                "mean_newline_std": "Mean (Std. Dev.)",
                "min": "Min",
                "max": "Max",
                "var": "Variance",
                "median": "Median",
            }
            sdict.update(stats_labels)

            chunks = []
            if hide_stats:
                slist = [sdict.get(k, k) for k in stats]
                if counts_row_below:
                    slist = [s for s in slist if s.lower() != "n"]
                chunks.append("Displayed statistics are " + ", ".join(slist) + ".")

            se_str = ""
            if isinstance(vcov, str) and vcov in {"hetero", "HC1", "HC2", "HC3"}:
                se_str = "robust standard errors."
            elif isinstance(vcov, dict):
                clusters = []
                for k, v in vcov.items():
                    if k in {"CRV1", "CRV3"}:
                        clusters.append(labels.get(v, v))
                if clusters:
                    se_str = "standard errors clustered on " + ", ".join(clusters)

            fe_str = ""
            if fixed_effects:
                fe_str = ", ".join(labels.get(fx, fx) for fx in fixed_effects)

            if fe_str and se_str:
                chunks.append(f"p-values based on specifications including {fe_str} fixed effects and {se_str}")
            elif fe_str:
                chunks.append(f"p-values based on specifications including {fe_str} fixed effects.")
            elif se_str:
                chunks.append(f"p-values based on {se_str}.")

            if chunks:
                n = " ".join(chunks)
                n = n[0] + n[1:].lower()
                self.notes = "Note: " + n
        else:
            self.notes = notes