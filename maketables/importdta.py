from __future__ import annotations

import contextlib
import os
import warnings
from datetime import datetime
from os import PathLike

import pandas as pd
from pandas.io.stata import StataReader

from .mtable import MTable


def import_dta(
    path: str | PathLike[str],
    *,
    convert_categoricals: bool = True,
    store_in_attrs: bool = True,
    update_mtable_defaults: bool = False,
    override: bool = False,
    return_labels: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, str]]:
    """
    Import a Stata .dta into a pandas DataFrame.

    Behavior
    - Preserves Stata value labels by reading labeled variables as pandas.Categorical
      when convert_categoricals=True.
    - Extracts variable (column) labels from the file.
    - Stores variable labels in df.attrs['variable_labels'] by default (store_in_attrs=True).
    - Optionally merges labels into MTable.DEFAULT_LABELS for package-wide defaults.

    Parameters
    ----------
    path : str | os.PathLike
        Local filesystem path to a .dta file.
    convert_categoricals : bool, default True
        Convert Stata value labels to pandas.Categorical (recommended to preserve value labels).
    store_in_attrs : bool, default True
        If True, save extracted variable labels under df.attrs['variable_labels'].
    update_mtable_defaults : bool, default False
        If True, merge extracted labels into MTable.DEFAULT_LABELS.
    override : bool, default False
        Controls merging into MTable.DEFAULT_LABELS when update_mtable_defaults=True:
        - True: overwrite existing keys with new labels.
        - False: only fill keys that are missing.
    return_labels : bool, default False
        If True, also return the labels dict in addition to the DataFrame.

    Returns
    -------
    DataFrame or (DataFrame, dict)
        - If return_labels=False: the DataFrame.
        - If return_labels=True: (df, labels) where labels is {column_name: label}.

    Notes
    -----
    - pandas handles Stata encodings from the file header.
    - API works across pandas versions; if StataReader constructor does not support
      convert_categoricals, it falls back and applies it at read time if needed.

    Examples
    --------
    >>> df = import_dta("data/auto.dta")
    >>> df.attrs["variable_labels"]["price"]
    >>> df, labels = import_dta(
    ...     "data/auto.dta", update_mtable_defaults=True, return_labels=True
    ... )
    """
    try:
        with StataReader(path, convert_categoricals=convert_categoricals) as rdr:
            var_labels: dict[str, str] = {
                k: v for k, v in rdr.variable_labels().items() if v
            }
            df = rdr.read()
    except TypeError:
        with StataReader(path) as rdr:
            var_labels = {k: v for k, v in rdr.variable_labels().items() if v}
            df = rdr.read()

    if store_in_attrs:
        with contextlib.suppress(Exception):
            df.attrs["variable_labels"] = dict(var_labels)

    if update_mtable_defaults:
        if override:
            MTable.DEFAULT_LABELS = {**MTable.DEFAULT_LABELS, **var_labels}
        else:
            merged = dict(MTable.DEFAULT_LABELS)
            for k, v in var_labels.items():
                merged.setdefault(k, v)
            MTable.DEFAULT_LABELS = merged

    if return_labels:
        return df, var_labels
    return df


def export_dta(
    df: pd.DataFrame,
    path: str | PathLike[str],
    *,
    labels: dict[str, str] | None = None,
    use_defaults: bool = True,
    use_df_attrs: bool = True,
    overwrite: bool = False,
    data_label: str | None = None,
    version: int = 118,
    write_index: bool = False,
    compression: str | None = "infer",
    time_stamp: datetime | None = None,
) -> None:
    """
    Export a DataFrame to a Stata .dta file, writing variable labels.

    Variable label sources (later wins on key conflicts):
      1) MTable.DEFAULT_LABELS (if use_defaults=True)
      2) df.attrs['variable_labels'] (if use_df_attrs=True)
      3) labels argument (highest priority)

    Stata value labels
    - pandas writes Categorical columns with their categories as Stata value labels.
      Ensure columns that should carry value labels are dtype 'category'.

    Parameters
    ----------
    df : pandas.DataFrame
        Data to export.
    path : str | os.PathLike
        Output .dta path. Existing file is preserved unless overwrite=True.
    labels : dict, optional
        Explicit variable labels {column: label} to apply (highest priority).
    use_defaults : bool, default True
        Include labels from MTable.DEFAULT_LABELS.
    use_df_attrs : bool, default True
        Include labels from df.attrs['variable_labels'] if present.
    overwrite : bool, default False
        If False and file exists, raise FileExistsError.
    data_label : str, optional
        Stata dataset label.
    version : int, default 118
        Stata file version (118 recommended; 117 is Stata 13).
    write_index : bool, default False
        Whether to write the index as a Stata variable.
    compression : {'zip','gzip','bz2','xz','zst','infer',None}, optional
        Compression mode for the output.
    time_stamp : datetime, optional
        Timestamp written to the Stata file header.

    Returns
    -------
    None

    Notes
    -----
    - Stata variable labels are limited to 80 characters; longer labels are truncated.
    - Some older pandas versions may not support variable_labels=; a warning is emitted and
      the file is written without variable labels in that case.

    Examples
    --------
    >>> export_dta(df, "data/auto_out.dta", overwrite=True)
    >>> export_dta(df, "data/auto_out.dta", labels={"price": "Vehicle price"}, overwrite=True)
    """
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"File exists: {path}. Set overwrite=True to replace.")

    var_labels: dict[str, str] = {}
    if use_defaults and getattr(MTable, "DEFAULT_LABELS", None):
        for k, v in MTable.DEFAULT_LABELS.items():
            if k in df.columns and v:
                var_labels[k] = str(v)
    if use_df_attrs and isinstance(df.attrs.get("variable_labels"), dict):
        for k, v in df.attrs["variable_labels"].items():
            if k in df.columns and v:
                var_labels[k] = str(v)
    if labels:
        for k, v in labels.items():
            if k in df.columns and v:
                var_labels[k] = str(v)

    trimmed = {}
    for k, v in var_labels.items():
        s = str(v)
        if len(s) > 80:
            warnings.warn(
                f"Variable label for '{k}' exceeds 80 chars; truncating.",
                RuntimeWarning,
                stacklevel=2,
            )
            s = s[:80]
        trimmed[k] = s
    var_labels = trimmed

    try:
        df.to_stata(
            path,
            write_index=write_index,
            version=version,
            variable_labels=var_labels if var_labels else None,
            data_label=data_label,
            convert_strl=True,
            time_stamp=time_stamp,
            compression=compression,
        )
    except TypeError:
        warnings.warn(
            "This pandas version does not support writing variable_labels. Writing without labels.",
            RuntimeWarning,
            stacklevel=2,
        )
        df.to_stata(
            path,
            write_index=write_index,
            version=version,
            data_label=data_label,
            convert_strl=True,
            time_stamp=time_stamp,
            compression=compression,
        )


def get_var_labels(
    df: pd.DataFrame, *, include_defaults: bool = False
) -> dict[str, str]:
    """
    Get variable labels for a DataFrame.

    Reads df.attrs['variable_labels'] and optionally fills missing labels from
    MTable.DEFAULT_LABELS.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame to inspect.
    include_defaults : bool, default False
        If True, add labels from MTable.DEFAULT_LABELS for columns missing a label.

    Returns
    -------
    dict
        Mapping {column_name: label}.

    Examples
    --------
    >>> get_var_labels(df)
    >>> get_var_labels(df, include_defaults=True)
    """
    labels: dict[str, str] = {}
    attr = df.attrs.get("variable_labels")
    if isinstance(attr, dict):
        labels.update({k: str(v) for k, v in attr.items() if v})
    if include_defaults and getattr(MTable, "DEFAULT_LABELS", None):
        for k, v in MTable.DEFAULT_LABELS.items():
            if k not in labels and k in df.columns and v:
                labels[k] = str(v)
    return labels


def set_var_labels(
    df: pd.DataFrame,
    labels: dict[str, str],
    *,
    overwrite: bool = True,
    update_mtable_defaults: bool = False,
) -> dict[str, str]:
    """
    Set variable labels on a DataFrame and optionally sync them to MTable.DEFAULT_LABELS.

    Labels are stored in df.attrs['variable_labels'] as a plain dict. Only columns
    present in df are written.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame to modify.
    labels : dict
        Mapping {column_name: label} to set.
    overwrite : bool, default True
        If True, replace existing labels for given columns; if False, only fill missing.
    update_mtable_defaults : bool, default False
        If True, merge the resulting labels dict into MTable.DEFAULT_LABELS
        (respecting the overwrite policy).

    Returns
    -------
    dict
        The updated df.attrs['variable_labels'] mapping.

    Examples
    --------
    >>> set_var_labels(df, {"mpg": "Miles per gallon"}, update_mtable_defaults=True)
    >>> get_var_labels(df)
    """
    current: dict[str, str] = {}
    if isinstance(df.attrs.get("variable_labels"), dict):
        current.update(df.attrs["variable_labels"])

    for k, v in labels.items():
        if k not in df.columns:
            continue
        if overwrite or k not in current:
            current[k] = str(v) if v is not None else v

    df.attrs["variable_labels"] = current

    if update_mtable_defaults:
        if overwrite:
            MTable.DEFAULT_LABELS = {
                **MTable.DEFAULT_LABELS,
                **{k: v for k, v in current.items() if v},
            }
        else:
            merged = dict(MTable.DEFAULT_LABELS)
            for k, v in current.items():
                if v and k not in merged:
                    merged[k] = v
            MTable.DEFAULT_LABELS = merged

    return current
