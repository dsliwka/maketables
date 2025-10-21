from typing import ClassVar

import numpy as np
import pandas as pd

from .importdta import get_var_labels
from .mtable import MTable


class DTable(MTable):
    """
    DTable extends MTable to provide descriptive statistics table functionality.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing the table to be displayed.
    vars : list
        List of variables to be included in the table.
    stats : list, optional
        List of statistics to be calculated. The default is None, that sets ['count','mean', 'std'].
        All pandas aggregation functions are supported.
    bycol : list, optional
        List of variables to be used to group the data by columns. The default is None.
    byrow : str, optional
        Variable to be used to group the data by rows. The default is None.
    type : str, optional
        Type of table to be created. The default is 'gt'.
        Type can be 'gt' for great_tables, 'tex' for LaTeX or 'df' for dataframe.
    labels : dict, optional
        Dictionary containing display labels for variables. If None, labels are taken
        from the DataFrame via get_var_labels(df) (which reads df.attrs['variable_labels']
        and fills missing entries from MTable.DEFAULT_LABELS). When provided, this mapping
        is used as-is (no automatic merge).
    stats_labels : dict, optional
        Dictionary containing the labels for the statistics. The default is None.
    format_spec : dict, optional
        Dictionary specifying format for each statistic type. Keys should match statistic names,
        values should be format specifiers (e.g., '.3f', '.2e', ',.0f').
        Example: {'mean': '.3f', 'std': '.2f', 'count': ',.0f'}
        If None, uses sensible defaults.
    digits : int, optional
        Number of decimal places for statistics display. This parameter is only
        applied when format_spec is None or when specific statistics are not
        specified in format_spec. Default is 2.
    notes : str
        Table notes to be displayed at the bottom of the table.
    counts_row_below : bool
        Whether to display the number of observations at the bottom of the table.
        Will only be carried out when each var has the same number of obs and when
        byrow is None. The default is False
    hide_stats : bool
        Whether to hide the names of the statistics in the table header. When stats
        are hidden and the user provides no notes string the labels of the stats are
        listed in the table notes. The default is False.
    observed : bool
        Whether to only consider the observed categories of categorical variables
        when grouping. The default is False.
    kwargs : dict
        Additional arguments to be passed to the make_table function.

    Returns
    -------
    A table in the specified format.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        vars: list,
        stats: list | None = None,
        bycol: list[str] | None = None,
        byrow: str | None = None,
        type: str = "gt",
        labels: dict | None = None,
        stats_labels: dict | None = None,
        format_spec: dict | None = None,
        digits: int = 2,
        notes: str = "",
        counts_row_below: bool = False,
        hide_stats: bool = False,
        observed: bool = False,
        **kwargs,
    ):
        # --- Begin dtable logic ---
        if stats is None:
            stats = ["count", "mean", "std"]

        # Use user-provided format_spec or empty dict
        self.format_specs = format_spec if format_spec is not None else {}

        # Determine labels: prefer DataFrame attrs; fall back to MTable defaults
        try:
            df_labels = get_var_labels(df, include_defaults=True)
        except Exception:
            df_labels = dict(getattr(MTable, "DEFAULT_LABELS", {}))
        labels = df_labels if labels is None else dict(labels)

        assert isinstance(df, pd.DataFrame), "df must be a pandas DataFrame."
        assert all(pd.api.types.is_numeric_dtype(df[var]) for var in vars), (
            "Variables must be numerical."
        )
        assert type in ["gt", "tex", "df"], "type must be either 'gt' or 'tex' or 'df'."
        assert byrow is None or byrow in df.columns, (
            "byrow must be a column in the DataFrame."
        )
        assert bycol is None or all(col in df.columns for col in bycol), (
            "bycol must be a list of columns in the DataFrame."
        )

        stats_dict = {
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
        if stats_labels:
            stats_dict.update(stats_labels)

        # If counts_row_below is True add count to stats if not already present
        if counts_row_below:
            if byrow is not None:
                counts_row_below = False
            elif "count" not in stats:
                stats = ["count"] + stats

        def mean_std(x):
            return _format_mean_std(
                x,
                digits=digits,
                newline=False,
                format_specs=self.format_specs,
                format_number_func=self._format_number,
            )

        def mean_newline_std(x):
            return _format_mean_std(
                x,
                digits=digits,
                newline=True,
                format_specs=self.format_specs,
                format_number_func=self._format_number,
            )

        custom_funcs = {"mean_std": mean_std, "mean_newline_std": mean_newline_std}
        agg_funcs = {
            var: [custom_funcs.get(stat, stat) for stat in stats] for var in vars
        }

        # Calculate the desired statistics
        if (byrow is not None) and (bycol is not None):
            bylist = [byrow, *bycol]
            res = df.groupby(bylist, observed=observed).agg(agg_funcs)
        if (byrow is None) and (bycol is None):
            res = df.agg(agg_funcs)
        elif (byrow is not None) and (bycol is None):
            res = df.groupby(byrow, observed=observed).agg(agg_funcs)
        elif (byrow is None) and (bycol is not None):
            res = df.groupby(bycol, observed=observed).agg(agg_funcs)

        if (byrow is not None) or ("count" not in stats):
            counts_row_below = False

        if res.columns.nlevels == 1:
            if counts_row_below:
                if res.loc["count"].nunique() == 1:
                    nobs = res.loc["count"].iloc[0]
                    res = res.drop("count", axis=0)
                    if "count" in stats:
                        stats.remove("count")
                else:
                    counts_row_below = False

            res = res.transpose(copy=True)

            for col in res.columns:
                # Skip formatting for combined statistics that are already formatted strings
                if res[col].name in ["mean_std", "mean_newline_std"]:
                    continue
                elif res[col].dtype == float or res[col].name in self.format_specs:
                    stat_name = res[col].name
                    res[col] = res[col].apply(
                        lambda x, sn=stat_name: self._format_number(x, self.format_specs.get(sn, None), digits=digits)
                    )

            if counts_row_below:
                obs_row = [self._format_number(nobs, self.format_specs.get("count", None), digits=digits)] + [""] * (
                    len(res.columns) - 1
                )
                res.loc[stats_dict["count"]] = obs_row

        else:
            if counts_row_below:
                count_columns = res.xs("count", axis=1, level=-1)
                if isinstance(count_columns, pd.Series):
                    count_columns = count_columns.to_frame()
                if count_columns.nunique(axis=1).eq(1).all():
                    nobs = count_columns.iloc[:, 0]
                    res = res.drop("count", axis=1, level=-1)
                    if "count" in stats:
                        stats.remove("count")
                    res[stats_dict["count"], stats[0]] = nobs
                else:
                    counts_row_below = False

            for col in res.columns:
                stat_name = col[-1] if isinstance(res.columns, pd.MultiIndex) else col
                if stat_name in ["mean_std", "mean_newline_std"]:
                    continue
                elif res[col].dtype == float:
                    res[col] = res[col].apply(
                        lambda x, sn=stat_name: self._format_number(x, self.format_specs.get(sn, None), digits=digits)
                    )

            res = pd.DataFrame(res.stack(level=0, future_stack=True))
            res.columns.names = ["Statistics"]
            if bycol is not None:
                res = pd.DataFrame(res.unstack(level=tuple(bycol)))
                if not isinstance(res.columns, pd.MultiIndex):
                    res.columns = pd.MultiIndex.from_tuples(res.columns)
                res.columns = res.columns.reorder_levels([*bycol, "Statistics"])
                levels_to_sort = list(range(res.columns.nlevels - 1))
                res = res.sort_index(axis=1, level=levels_to_sort, sort_remaining=False)

            if hide_stats:
                res.columns = res.columns.droplevel(-1)
                if notes == "":
                    notes = (
                        "Note: Displayed statistics are "
                        + ", ".join([stats_dict.get(k, k) for k in stats])
                        + "."
                    )

        res = res.fillna("")
        res.columns = _relabel_index(res.columns, labels, stats_dict)
        res.index = _relabel_index(res.index, labels)

        if counts_row_below:
            res.index = pd.MultiIndex.from_tuples([("stats", i) for i in res.index])
            new_index = list(res.index)
            new_index[-1] = ("nobs", stats_dict["count"])
            res.index = pd.MultiIndex.from_tuples(new_index)

        rgroup_display = byrow is not None

        # --- End dtable logic ---

        # Call MTable constructor with processed table and metadata
        super().__init__(res, notes=notes, rgroup_display=rgroup_display, **kwargs)

    def _format_number(self, x: float, format_spec: str | None = None, digits: int = 2) -> str:
        """Format a number with optional format specifier or sensible default."""
        import pandas as pd
        import numpy as np

        if pd.isna(x) or (isinstance(x, float) and np.isnan(x)):
            return "-"

        if format_spec is None:
            abs_x = abs(x)
            if abs_x < 0.001 and abs_x > 0:
                return f"{x:.6f}".rstrip("0").rstrip(".")
            elif abs_x < 1:
                return f"{x:.{digits}f}".rstrip("0").rstrip(".")
            elif abs_x < 1000:
                return f"{x:.{digits}f}"
            elif abs_x >= 10000:
                return f"{x:,.0f}"
            elif abs_x >= 1000:
                if abs(x - round(x)) < 1e-10:
                    return f"{int(round(x)):,}"
                else:
                    return f"{x:,.2f}"
            else:
                return f"{x:.{digits}f}"
        try:
            if format_spec == "d":
                return f"{int(round(x)):d}"
            return f"{x:{format_spec}}"
        except (ValueError, TypeError):
            # fallback to sensible default
            return self._format_number(x, None, digits=digits)


def _relabel_index(index, labels=None, stats_labels=None):
    if stats_labels is None:
        if isinstance(index, pd.MultiIndex):
            index = pd.MultiIndex.from_tuples(
                [tuple(labels.get(k, k) for k in i) for i in index]
            )
        else:
            index = [labels.get(k, k) for k in index]
    else:
        # if stats_labels is provided, we relabel the lowest level of the index with it
        if isinstance(index, pd.MultiIndex):
            new_index = []
            for i in index:
                new_index.append(
                    tuple(
                        [labels.get(k, k) for k in i[:-1]]
                        + [stats_labels.get(i[-1], i[-1])]
                    )
                )
            index = pd.MultiIndex.from_tuples(new_index)
        else:
            index = [stats_labels.get(k, k) for k in index]
    return index


def _format_mean_std(
    data: pd.Series,
    digits: int = 2,
    newline: bool = True,
    format_specs: dict | None = None,
    format_number_func=None,
) -> str:
    """
    Calculate the mean and standard deviation of a pandas Series and return as a string of the format "mean /n (std)".

    Parameters
    ----------
    data : pd.Series
        The pandas Series for which to calculate the mean and standard deviation.
    digits : int, optional
        The number of decimal places to round the mean and standard deviation to. The default is 2.
    newline : bool, optional
        Whether to add a newline character between the mean and standard deviation. The default is True.
    format_specs : dict, optional
        Format specifications for mean and std. Keys should be 'mean' and 'std'.

    Returns
    -------
    _format_mean_std : str
        The mean and standard deviation of the pandas Series formated as a string.

    """
    mean = data.mean()
    std = data.std()
    if format_number_func is None:
        mean_str = f"{mean:.{digits}f}"
        std_str = f"{std:.{digits}f}"
    else:
        mean_str = format_number_func(mean, format_specs.get("mean") if format_specs else None, digits)
        std_str = format_number_func(std, format_specs.get("std") if format_specs else None, digits)
    if newline:
        return f"{mean_str}\n({std_str})"
    else:
        return f"{mean_str} ({std_str})"
