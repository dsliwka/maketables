from __future__ import annotations

from typing import Dict, Tuple, Optional
from os import PathLike
import warnings
import os
from datetime import datetime

import pandas as pd
from pandas.io.stata import StataReader

from .mtable import MTable


def import_dta(
    path: str | PathLike[str],
    *,
    convert_categoricals: bool = True,
    encoding: Optional[str] = None,  # ignored; pandas reads encoding from file header
    update_defaults: bool = True,
    override: bool = False,
    return_labels: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Import a Stata .dta into a pandas DataFrame, preserve value labels as categoricals,
    and update MTable.DEFAULT_LABELS with variable labels.

    Parameters
    ----------
    path : str | PathLike
        Path to the .dta file.
    convert_categoricals : bool, default True
        Convert Stata value labels to pandas.Categorical (preserves labeled values).
    encoding : str | None
        Text encoding override if needed.
    update_defaults : bool, default True
        If True, update MTable.DEFAULT_LABELS with the extracted variable labels.
    override : bool, default False
        If True, new labels overwrite existing defaults for the same keys.
        If False, existing defaults are kept (only fill missing keys).
    return_labels : bool, default False
        If True, return the variable labels dict along with the DataFrame.

    Returns
    -------
    (df, var_labels) : (pandas.DataFrame, dict[str, str])
        DataFrame with categorized columns (where value labels exist) and
        a dict of variable labels {column_name: label}.
    """
    # Stata encoding is stored in the file; pandas handles it. Warn if user passed one.
    if encoding is not None:
        warnings.warn("import_stata: 'encoding' is ignored; Stata files carry encoding in the header.", RuntimeWarning)

    # Pass convert_categoricals on the constructor when supported; fall back otherwise.
    try:
        with StataReader(path, convert_categoricals=convert_categoricals) as rdr:
            var_labels: Dict[str, str] = {k: v for k, v in rdr.variable_labels().items() if v}
            df = rdr.read()
    except TypeError:
        # Older/newer pandas signature without convert_categoricals
        with StataReader(path) as rdr:
            var_labels = {k: v for k, v in rdr.variable_labels().items() if v}
            df = rdr.read()

    # Attach labels to DataFrame metadata for downstream access
    try:
        df.attrs["variable_labels"] = dict(var_labels)
    except Exception:
        pass

    if update_defaults:
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
    labels: Optional[Dict[str, str]] = None,
    use_defaults: bool = True,
    use_df_attrs: bool = True,
    overwrite: bool = False,
    data_label: Optional[str] = None,
    version: int = 118,
    write_index: bool = False,
    compression: Optional[str] = "infer",
    time_stamp: Optional[datetime] = None,
) -> None:
    """
    Export a DataFrame to a Stata .dta file and write variable labels.

    Variable labels priority (later wins):
      1) MTable.DEFAULT_LABELS (if use_defaults=True)
      2) df.attrs['variable_labels'] (if use_df_attrs=True)
      3) labels argument (explicit overrides)

    Notes
    - Stata value labels: pandas writes Categorical columns as labeled values
      automatically (use pandas Categorical dtype to preserve them).
    - Stata variable label length is limited (80 chars). Longer labels are truncated.

    Parameters
    ----------
    df : pandas.DataFrame
        Data to export.
    path : str | PathLike
        Output .dta file path.
    labels : dict, optional
        Mapping {column_name: variable_label}. Highest priority.
    use_defaults : bool, default True
        Include labels from MTable.DEFAULT_LABELS.
    use_df_attrs : bool, default True
        Include labels from df.attrs['variable_labels'] if present.
    overwrite : bool, default False
        Overwrite the file if it already exists.
    data_label : str, optional
        Dataset label stored in the Stata file.
    version : int, default 118
        Stata file version (117 = Stata 13, 118 = Stata 14+). 118 recommended.
    write_index : bool, default False
        Whether to write the index to Stata.
    compression : {'zip','gzip','bz2','xz','zst','infer',None}, optional
        Compression mode.
    time_stamp : datetime, optional
        Timestamp stored in the file header.
    """
    # Check overwrite
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"File exists: {path}. Set overwrite=True to replace.")

    # Assemble variable labels with priority
    var_labels: Dict[str, str] = {}
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

    # Enforce Stata's variable label length limit (80 chars)
    trimmed = {}
    for k, v in var_labels.items():
        s = str(v)
        if len(s) > 80:
            warnings.warn(f"Variable label for '{k}' exceeds 80 chars; truncating.", RuntimeWarning)
            s = s[:80]
        trimmed[k] = s
    var_labels = trimmed

    # Write .dta (pandas will write Categoricals as value labels)
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
        # Older pandas without variable_labels support
        warnings.warn("This pandas version does not support writing variable_labels. Writing without labels.", RuntimeWarning)
        df.to_stata(
            path,
            write_index=write_index,
            version=version,
            data_label=data_label,
            convert_strl=True,
            time_stamp=time_stamp,
            compression=compression,
        )