from typing import Optional

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
        If None, uses sensible defaults based on statistic type.
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

    # Class defaults for formatting different statistics
    DEFAULT_FORMAT_SPECS = {
        "mean": ".3f",
        "std": ".3f",
        "count": ",.0f",
        "median": ".3f",
        "min": ".3f",
        "max": ".3f",
        "var": ".4f",
        "quantile": ".3f",
        "sum": ",.2f",
        "mean_std": None,  # handled separately
        "mean_newline_std": None,  # handled separately
    }

    def __init__(
        self,
        df: pd.DataFrame,
        vars: list,
        stats: Optional[list] = None,
        bycol: Optional[list[str]] = None,
        byrow: Optional[str] = None,
        type: str = "gt",
        labels: dict | None = None,
        stats_labels: dict | None = None,
        format_spec: Optional[dict] = None,
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

        # Handle format specifications - merge user provided with defaults
        if format_spec is None:
            self.format_specs = dict(self.DEFAULT_FORMAT_SPECS)
            # Apply digits to statistics that use default .3f format
            digit_format = f".{digits}f"
            for stat in ["mean", "std", "median", "min", "max"]:
                if self.format_specs[stat] == ".3f":
                    self.format_specs[stat] = digit_format
        else:
            # Start with defaults and update with user specifications
            self.format_specs = dict(self.DEFAULT_FORMAT_SPECS)
            self.format_specs.update(format_spec)

            # For any stats the user specified that aren't in our defaults, use digits
            digit_format = f".{digits}f"
            for stat in stats:
                if stat not in self.format_specs and stat not in [
                    "mean_std",
                    "mean_newline_std",
                ]:
                    self.format_specs[stat] = digit_format

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
                type=type,
                format_specs=self.format_specs,
            )

        def mean_newline_std(x):
            return _format_mean_std(
                x,
                digits=digits,
                newline=True,
                type=type,
                format_specs=self.format_specs,
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

        # Define helper function to format statistics using format_specs
        def format_statistic(value, stat_name):
            return self._format_statistic(value, stat_name)

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
                    continue  # These are already formatted by their custom functions
                elif res[col].dtype == float or res[col].name in self.format_specs:
                    stat_name = res[col].name
                    res[col] = res[col].apply(
                        lambda x, sn=stat_name: format_statistic(x, sn)
                    )

            if counts_row_below:
                obs_row = [format_statistic(nobs, "count")] + [""] * (
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
                # Extract stat name from column multiindex
                stat_name = col[-1] if isinstance(res.columns, pd.MultiIndex) else col

                # Skip formatting for combined statistics that are already formatted strings
                if stat_name in ["mean_std", "mean_newline_std"]:
                    continue  # These are already formatted by their custom functions
                elif res[col].dtype == float:
                    res[col] = res[col].apply(
                        lambda x, sn=stat_name: format_statistic(x, sn)
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

    def _format_statistic(self, value: float, stat_name: str) -> str:
        """Format a single statistic value according to its format specification."""
        if pd.isna(value) or (isinstance(value, float) and np.isnan(value)):
            return "-"

        format_spec = self.format_specs.get(stat_name, ".3f")
        return self._format_number(value, format_spec)

    def _format_number(self, x: float, format_spec: str = None) -> str:
        """Format a number with optional format specifier."""
        if pd.isna(x) or (isinstance(x, float) and np.isnan(x)):
            return "-"

        if format_spec is None:
            # Sensible default formatting
            abs_x = abs(x)

            if abs_x < 0.001 and abs_x > 0:
                return f"{x:.6f}".rstrip("0").rstrip(".")
            elif abs_x < 1:
                return f"{x:.3f}".rstrip("0").rstrip(".")
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
            if format_spec == "d":
                return f"{int(round(x)):d}"
            return f"{x:{format_spec}}"
        except (ValueError, TypeError):
            return self._format_number(x, None)


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
    type=str,
    format_specs: dict = None,
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
    type : str, optional
        The type of the table output.
    format_specs : dict, optional
        Format specifications for mean and std. Keys should be 'mean' and 'std'.

    Returns
    -------
    _format_mean_std : str
        The mean and standard deviation of the pandas Series formated as a string.

    """
    mean = data.mean()
    std = data.std()

    # Use format specifications if provided, otherwise fall back to digits
    if format_specs and "mean" in format_specs:
        mean_str = _format_number_dtable(mean, format_specs["mean"])
    else:
        mean_str = f"{mean:.{digits}f}"

    if format_specs and "std" in format_specs:
        std_str = _format_number_dtable(std, format_specs["std"])
    else:
        std_str = f"{std:.{digits}f}"

    if newline:
        return f"{mean_str}\n({std_str})"
    else:
        return f"{mean_str} ({std_str})"


def _format_number_dtable(x: float, format_spec: str = None) -> str:
    """
    Format a number with optional format specifier for DTable.

    Parameters
    ----------
    x : float
        The number to format.
    format_spec : str, optional
        Format specifier (e.g., '.3f', '.2e', ',.0f', 'd').
        If None, uses sensible default formatting.

    Returns
    -------
    str
        The formatted number.
    """
    if pd.isna(x) or (isinstance(x, float) and np.isnan(x)):
        return "-"

    if format_spec is None:
        # Sensible default formatting
        abs_x = abs(x)

        if abs_x < 0.001 and abs_x > 0:
            return f"{x:.6f}".rstrip("0").rstrip(".")
        elif abs_x < 1:
            return f"{x:.3f}".rstrip("0").rstrip(".")
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
        if format_spec == "d":
            return f"{int(round(x)):d}"
        return f"{x:{format_spec}}"
    except (ValueError, TypeError):
        return _format_number_dtable(x, None)
    #     if type == "gt":
    #         return f"{mean:.{digits}f}<br>({std:.{digits}f})"
    #     elif type == "tex":
    #         return f"{mean:.{digits}f}\\\\({std:.{digits}f})"
    #     elif type == "df":
    #         return f"{mean:.{digits}f}\n({std:.{digits}f})"
    #     elif type == "docx":
    #         return f"{mean:.{digits}f}\n({std:.{digits}f})"
    # return f"{mean:.{digits}f} ({std:.{digits}f})"
