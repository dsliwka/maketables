from __future__ import annotations

from typing import Dict, Tuple, Optional
from os import PathLike
import warnings

import pandas as pd
from pandas.io.stata import StataReader

from .mtable import MTable


def import_stata(
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