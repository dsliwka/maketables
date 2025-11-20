import contextlib
import math
import re
import warnings
from collections import Counter
from collections.abc import ValuesView
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from .extractors import ModelExtractor, get_extractor
from .mtable import MTable


class ETable(MTable):
    r"""
    Regression table builder on top of MTable.

    ETable extracts coefficients and model statistics from supported model
    objects, assembles a publication-style table, and delegates rendering/export to MTable.

    Parameters
    ----------
    models : 
        One or more fitted models. Accepts single models, lists, or multi-model 
        containers (e.g., pyfixest's FixestMulti). Supported packages are 
        automatically detected via registered extractors (see extractors.py).
        Built-in support: pyfixest, statsmodels, linearmodels.
    signif_code : list[float], optional
        Three ascending p-value cutoffs for significance stars, default
        ETable.DEFAULT_SIGNIF_CODE = [0.01, 0.05, 0.10].
    coef_fmt : str, optional
        Cell layout for each coefficient. Tokens:
          - 'b' (estimate), 'se' (std. error), 't' (t value), 'p' (p-value),
          - whitespace, ',', parentheses '(', ')', brackets '[', ']', and
          - '\\n' for line breaks.
        You may also reference keys from custom_stats to inject custom values.
        Format specifiers can be added after tokens (e.g., 'b:.3f', 'se:.2e', 'N:,.0f'):
          - '.Nf' for N decimal places (e.g., '.3f' for 3 decimals)
          - '.Ne' for scientific notation with N decimals (e.g., '.2e')
          - ',.Nf' for comma thousands separator (e.g., ',.0f')
          - ':d' for integer formatting
        Default ETable.DEFAULT_COEF_FMT = "b \\n (se)".
    model_stats : list[str], optional
        Bottom panel statistics to display (order is kept). Examples:
        'N', 'r2', 'adj_r2', 'r2_within', 'se_type'. If None, defaults to
        ETable.DEFAULT_MODEL_STATS (currently ['N','r2']).
    model_stats_labels : dict[str, str], optional
        Mapping from stat key to display label (e.g., {'N': 'Observations'}).
        Defaults come from ETable.DEFAULT_STAT_LABELS; user-provided entries override.
    custom_stats : dict, optional
        Custom per-coefficient values to splice into coef cells via coef_fmt.
        Shape: {key: list_of_per_model_lists}, where for each key in coef_fmt,
        custom_stats[key][i] is a list aligned to model i’s coefficient index.
    custom_model_stats : dict, optional
        Additional bottom rows. Shape: {'Row label': [val_m1, val_m2, ...]}.
    keep : list[str] | str, optional
        Regex patterns (or exact names with exact_match=True) to keep and order
        coefficients. If provided, output order follows the pattern order.
    drop : list[str] | str, optional
        Regex patterns (or exact names with exact_match=True) to exclude after
        applying keep.
    exact_match : bool, default False
        If True, treat keep/drop patterns as exact names (no regex).
    labels : dict, optional
        Variable labels for relabeling dependent vars, regressors, and (if not
        provided in felabels) fixed effects. If None, labels are collected from
        each model's source DataFrame via the extractor (e.g., PyFixest: model._data;
        Statsmodels: result.model.data.frame), merged across models (first seen wins),
        and any missing entries are filled from MTable.DEFAULT_LABELS.
    cat_template : str, optional
        Template to relabel categorical terms, using placeholders
        '{variable}' and '{value}'. Default ETable.DEFAULT_CAT_TEMPLATE
        = "{variable}={value}". Use "{value}" to show only category names.
    show_fe : bool, optional
        Whether to add a fixed-effects presence panel. Defaults to
        ETable.DEFAULT_SHOW_FE (True).
    felabels : dict, optional
        Custom labels for the fixed-effects rows; falls back to labels when
        not provided.
    notes : str, optional
        Table notes. If "", a default note with significance levels and the
        coef cell format is generated.
    model_heads : list[str], optional
        Optional model headers (e.g., country names).
    head_order : {"dh","hd","d","h",""}, optional
        Header level order: d=dep var, h=model header. "" shows only model numbers.
        Default ETable.DEFAULT_HEAD_ORDER = "dh".
    caption : str, optional
        Table caption (passed to MTable).
    tab_label : str, optional
        Label/anchor for LaTeX/HTML (passed to MTable).
    digits : int, optional
        Number of decimal places for coefficient display. This parameter is only
        applied when coef_fmt does not already contain format specifiers. If coef_fmt
        contains format specifiers (e.g., 'b:.3f'), this parameter is ignored.
        For precise control, use format specifiers in coef_fmt directly.
    **kwargs
        Forwarded to MTable (e.g., rgroup_display, rendering options).

    Notes
    -----
    - To display the SE type, include "se_type" in model_stats.
    - Categorical term relabeling applies to plain categorical columns and to
      formula encodings that expose variable/value names.
    - When labels is None, labels are sourced from each model's DataFrame (if
      available) and supplemented by MTable.DEFAULT_LABELS. Use set_var_labels()
      or import_dta() to populate df.attrs['variable_labels'].
    - Supported model types are automatically detected via their extractor.

    Returns
    -------
    ETable
        An object holding the assembled table data (as a DataFrame in MTable)
        and rendering helpers (via MTable.make/save).
    """

    # ---- Class defaults ----
    DEFAULT_SIGNIF_CODE: ClassVar[list[float]] = [0.01, 0.05, 0.10]
    DEFAULT_COEF_FMT: ClassVar[str] = "b:.3f \n (se:.3f)"
    DEFAULT_MODEL_STATS: ClassVar[list[str]] = ["N", "r2"]
    # Canonical stat key -> printable label (used if model_stats_labels is None)
    DEFAULT_STAT_LABELS: ClassVar[dict[str, str]] = {
        "N": "Observations",
        "se_type": "S.E. type",
        "r2": "R²",
        "adj_r2": "Adj. R²",
        "r2_within": "Within R²",
        "r2_between": "Between R²",
        "adj_r2_within": "Within Adj. R²",
        "pseudo_r2": "Pseudo R²",
        "ll": "Log-likelihood",
        "llnull": "Null log-likelihood",
        "aic": "AIC",
        "bic": "BIC",
        "df_model": "df(model)",
        "df_resid": "df(resid)",
        "deviance": "Deviance",
        "null_deviance": "Null deviance",
        "fvalue": "F statistic",
        "f_pvalue": "F p-value",
        "rmse": "RMSE",
        "fstat_1st": "First-stage F",
    }
    DEFAULT_SHOW_SE_TYPE = True
    DEFAULT_SHOW_FE = True
    DEFAULT_HEAD_ORDER = "dh"
    DEFAULT_FELABELS: ClassVar[dict[str, str]] = {}
    DEFAULT_CAT_TEMPLATE = "{variable}={value}"
    DEFAULT_LINEBREAK = "\n"

    def __init__(
        self,
        models: Any, 
        *,
        signif_code: list | None = None,
        coef_fmt: str | None = None,
        model_stats: list[str] | None = None,
        model_stats_labels: dict[str, str] | None = None,
        custom_stats: dict | None = None,
        custom_model_stats: dict | None = None,
        keep: list | str | None = None,
        drop: list | str | None = None,
        exact_match: bool | None = False,
        labels: dict | None = None,
        cat_template: str | None = None,
        show_fe: bool | None = None,
        felabels: dict | None = None,
        notes: str = "",
        model_heads: list | None = None,
        head_order: str | None = None,
        caption: str | None = None,
        tab_label: str | None = None,
        digits: int | None = None,
        **kwargs,
    ):
        # --- defaults from class attributes ---
        signif_code = self.DEFAULT_SIGNIF_CODE if signif_code is None else signif_code
        coef_fmt = self.DEFAULT_COEF_FMT if coef_fmt is None else coef_fmt

        # --- Handle digits parameter for backward compatibility ---
        if digits is not None:
            # Check if coef_fmt already has format specifiers
            if not _has_format_specifiers(coef_fmt):
                # Apply digits to the default or user-provided coef_fmt
                coef_fmt = _apply_digits_to_coef_fmt(coef_fmt, digits)
            else:
                warnings.warn(
                    "The 'digits' parameter is ignored when coef_fmt already contains format specifiers "
                    "(e.g., 'b:.3f'). Use format specifiers in coef_fmt for precise control.",
                    UserWarning,
                    stacklevel=2,
                )
        cat_template = (
            self.DEFAULT_CAT_TEMPLATE if cat_template is None else cat_template
        )
        show_fe = self.DEFAULT_SHOW_FE if show_fe is None else show_fe
        felabels = dict(self.DEFAULT_FELABELS) if felabels is None else felabels
        head_order = self.DEFAULT_HEAD_ORDER if head_order is None else head_order
        custom_stats = {} if custom_stats is None else custom_stats
        keep = [] if keep is None else keep
        drop = [] if drop is None else drop

        # --- checks  ---
        assert isinstance(signif_code, list) and len(signif_code) == 3
        if signif_code:
            assert all(0 < i < 1 for i in signif_code)
            assert signif_code[0] < signif_code[1] < signif_code[2]

        models = self._normalize_models(models)

        # Determine labels:
        # 1) if user provided labels, use them as-is
        # 2) otherwise, collect from models' DataFrames and fill from MTable defaults
        if labels is None:
            labels = self._collect_labels_from_models(models)
        else:
            labels = dict(labels)

        if custom_stats:
            assert isinstance(custom_stats, dict)
            for key in custom_stats:
                assert isinstance(custom_stats[key], list)
                assert len(custom_stats[key]) == len(models)

        if model_heads is not None:
            assert len(model_heads) == len(models)

        assert head_order in ["dh", "hd", "d", "h", ""]

        # --- metadata from models (modular) ---
        dep_var_list = [self._extract_depvar(m) for m in models]
        # relabel dependent variables
        if labels:
            dep_var_list = [labels.get(d, d) for d in dep_var_list]
        fixef_list = self._collect_fixef_list(models, show_fe)

        # --- bottom model stats keys (modular default) ---
        if model_stats is None:
            model_stats = list(self.DEFAULT_MODEL_STATS)
        model_stats = list(model_stats)
        assert all(isinstance(s, str) for s in model_stats)
        assert len(model_stats) == len(set(model_stats))

        # --- build blocks (modular) ---
        res, coef_fmt_title = self._build_coef_table(
            models=models,
            coef_fmt=coef_fmt,
            signif_code=signif_code,
            custom_stats=custom_stats,
            keep=keep,
            drop=drop,
            exact_match=exact_match,
            labels=labels,
            cat_template=cat_template,
        )

        fe_df = self._build_fe_df(
            models=models,
            fixef_list=fixef_list,
            show_fe=show_fe,
            labels=labels,
            felabels=felabels,
            like_columns=res.columns,
        )

        model_stats_df = self._build_model_stats(
            models=models,
            stat_keys=model_stats,
            stat_labels=model_stats_labels,
            custom_model_stats=custom_model_stats,
            like_index=res.index,
            like_columns=res.columns,
        )

        # --- assemble columns header (modular) ---
        header = self._build_header_columns(
            dep_var_list=dep_var_list,
            model_heads=model_heads,
            head_order=head_order,
            n_models=len(models),
        )

        # --- assemble final df ---
        res_all = pd.concat([res, fe_df, model_stats_df], keys=["coef", "fe", "stats"])
        if isinstance(header, list):
            res_all.columns = pd.Index(header)
        else:
            res_all.columns = header
        with contextlib.suppress(Exception):
            res_all.columns.names = [None] * res_all.columns.nlevels

        # --- notes ---
        if notes == "":
            notes = (
                f"Significance levels: * p < {signif_code[2]}, ** p < {signif_code[1]}, *** p < {signif_code[0]}. "
                + f"Format of coefficient cell: {coef_fmt_title}"
            )
            # Remove line breaks from notes "\n"
            notes = notes.replace("\n", " ")

        super().__init__(
            res_all,
            notes=notes,
            caption=caption,
            tab_label=tab_label,
            rgroup_display=False,
            **kwargs,
        )

    # ---------- Dispatch helpers (package detection) ----------

    def _normalize_models(self, models: Any) -> list[Any]:
        """
        Normalize models to a list, expanding multi-model containers.
        
        Uses duck typing to detect FixestMulti-like objects (anything with a to_list() method).
        This keeps etable.py package-agnostic.
        """
        # Check for multi-model container (has to_list method)
        if hasattr(models, 'to_list') and callable(getattr(models, 'to_list', None)):
            return models.to_list()
        
        # Handle lists/tuples/ValuesView
        if isinstance(models, (list, tuple, ValuesView)):
            return list(models)
        
        # Single model
        return [models]

    def _get_extractor(self, model: Any) -> ModelExtractor:
        return get_extractor(model)

    # --- delegate helpers to extractor ---

    def _extract_depvar(self, model: Any) -> str:
        return self._get_extractor(model).depvar(model)

    def _extract_fixef_string(self, model: Any) -> str | None:
        return self._get_extractor(model).fixef_string(model)

    def _extract_vcov_info(self, model: Any) -> dict[str, Any]:
        return self._get_extractor(model).vcov_info(model)

    def _extract_tidy_df(self, model: Any) -> pd.DataFrame:
        df = self._get_extractor(model).coef_table(model)
        # enforce index name
        if df.index.name != "Coefficient":
            df.index.name = "Coefficient"
        return df

    def _extract_stat(self, model: Any, key: str) -> str:
        raw = self._get_extractor(model).stat(model, key)
        # format uniformly
        if key == "se_type":
            return raw or "-"
        if raw is None:
            return "-"
        if isinstance(raw, (int, np.integer)):
            return _format_number(float(raw))
        if isinstance(raw, (float, np.floating)):
            return "-" if math.isnan(raw) else _format_number(float(raw))
        return str(raw)

    def _collect_labels_from_models(self, models: list[Any]) -> dict[str, str]:
        """
        Gather variable labels from each model via its extractor, merging across
        models (first seen wins), then fill missing entries from MTable.DEFAULT_LABELS.
        """
        merged: dict[str, str] = {}
        for m in models:
            try:
                extractor = self._get_extractor(m)
                model_labels = (
                    extractor.var_labels(m)
                    if hasattr(extractor, "var_labels")
                    else None
                )
            except Exception:
                model_labels = None
            if isinstance(model_labels, dict):
                for k, v in model_labels.items():
                    if v and (k not in merged):
                        merged[k] = v
        # Fill remaining with global defaults
        try:
            for k, v in getattr(MTable, "DEFAULT_LABELS", {}).items():
                if v and (k not in merged):
                    merged[k] = v
        except Exception:
            pass
        return merged

    def _collect_fixef_list(self, models: list[Any], show_fe: bool) -> list[str]:
        if not show_fe:
            return []
        fixef_list: list[str] = []
        for m in models:
            fx = self._extract_fixef_string(m)
            if fx and fx != "0":
                fixef_list += fx.split("+")
        fixef_list = [x for x in fixef_list if x]
        return sorted(set(fixef_list))

    def _compute_stars(self, p: pd.Series, signif_code: list[float]) -> pd.Series:
        if not signif_code:
            return pd.Series([""] * len(p), index=p.index)
        s = pd.Series("", index=p.index, dtype=object)
        s = np.where(
            p < signif_code[0],
            "***",
            np.where(p < signif_code[1], "**", np.where(p < signif_code[2], "*", "")),
        )
        return pd.Series(s, index=p.index)

    def _build_coef_table(
        self,
        models: list[Any],
        coef_fmt: str,
        signif_code: list[float],
        custom_stats: dict[str, list[list]],
        keep: list[str],
        drop: list[str],
        exact_match: bool,
        labels: dict[str, str],
        cat_template: str,
    ) -> tuple[pd.DataFrame, str]:
        lbcode = self.DEFAULT_LINEBREAK
        coef_fmt_elements, coef_fmt_title = _parse_coef_fmt(coef_fmt, custom_stats)

        cols_per_model = []
        for i, model in enumerate(models):
            tidy = self._extract_tidy_df(model)
            stars = self._compute_stars(tidy["Pr(>|t|)"], signif_code)

            cell = pd.Series("", index=tidy.index, dtype=object)
            for element in coef_fmt_elements:
                token = element["token"]
                format_spec = element["format"]

                if token == "b":
                    cell += (
                        tidy["Estimate"].apply(_format_number, format_spec=format_spec)
                        + stars
                    )
                elif token == "se":
                    cell += tidy["Std. Error"].apply(
                        _format_number, format_spec=format_spec
                    )
                elif token == "t":
                    if "t value" in tidy.columns:
                        cell += tidy["t value"].apply(
                            _format_number, format_spec=format_spec
                        )
                elif token == "p":
                    cell += tidy["Pr(>|t|)"].apply(
                        _format_number, format_spec=format_spec
                    )
                elif token in custom_stats:
                    assert len(custom_stats[token][i]) == len(tidy["Estimate"])
                    cell += pd.Series(custom_stats[token][i], index=tidy.index).apply(
                        _format_number, format_spec=format_spec
                    )
                elif token == "\n":
                    cell += lbcode
                else:
                    cell += token

            # one column per model, indexed by 'Coefficient'
            df_i = pd.DataFrame({f"est{i + 1}": pd.Categorical(cell)}, index=tidy.index)
            df_i.index.name = "Coefficient"
            cols_per_model.append(df_i)

        # align on coefficient names
        res = pd.concat(cols_per_model, axis=1)
        res.index.name = "Coefficient"

        # keep/drop ordering on the index (no reset)
        idxs = (
            _select_order_coefs(res.index.tolist(), keep, drop, exact_match)
            if (keep or drop)
            else res.index.tolist()
        )
        res = res.loc[idxs]

        # fill NA and ensure empty category exists
        for c in res.columns:
            col = res[c]
            if (
                isinstance(col.dtype, pd.CategoricalDtype)
                and "" not in col.cat.categories
            ):
                res[c] = col.cat.add_categories([""])
            res[c] = res[c].fillna("")

        # move intercept to bottom
        if "Intercept" in res.index:
            order = [ix for ix in res.index if ix != "Intercept"] + ["Intercept"]
            res = res.loc[order]

        # relabel coefficient index
        if (labels != {}) or (cat_template != ""):
            res.index = res.index.to_series().apply(
                lambda x: _relabel_expvar(x, labels or {}, " × ", cat_template)
            )
            res.index.name = "Coefficient"

        return res, coef_fmt_title

    def _build_fe_df(
        self,
        models: list[Any],
        fixef_list: list[str],
        show_fe: bool,
        labels: dict[str, str],
        felabels: dict[str, str] | None,
        like_columns: pd.Index,
    ) -> pd.DataFrame:
        if not (show_fe and fixef_list):
            return pd.DataFrame(index=pd.Index([], name=None), columns=like_columns)
        rows = {}
        for fx in fixef_list:
            row = []
            for m in models:
                fx_str = self._extract_fixef_string(m) or ""
                has = (
                    (fx_str != "")
                    and (fx in fx_str.split("+"))
                    and not getattr(m, "_use_mundlak", False)
                )
                row.append("x" if has else "-")
            rows[fx] = row
        fe_df = pd.DataFrame.from_dict(rows, orient="index", columns=list(like_columns))
        # relabel FE names
        felabels = felabels or {}
        labels = labels or {}
        fe_df.index = fe_df.index.to_series().apply(
            lambda x: felabels.get(x, labels.get(x, x))
        )
        return fe_df

    def _build_model_stats(
        self,
        models: list[Any],
        stat_keys: list[str],
        stat_labels: dict[str, str] | None,
        custom_model_stats: dict[str, list] | None,
        like_index: pd.Index,
        like_columns: pd.Index,
    ) -> pd.DataFrame:
        # builtin stats via extractor
        def label_of(k: str) -> str:
            default = self.DEFAULT_STAT_LABELS.get(k, k)
            return stat_labels.get(k, default) if stat_labels else default

        rows = {
            label_of(k): [self._extract_stat(m, k) for m in models] for k in stat_keys
        }
        builtin_df = (
            pd.DataFrame.from_dict(rows, orient="index") if rows else pd.DataFrame()
        )

        # custom bottom rows
        custom_df = (
            pd.DataFrame.from_dict(custom_model_stats, orient="index")
            if custom_model_stats
            else pd.DataFrame()
        )

        if not custom_df.empty and not builtin_df.empty:
            out = pd.concat([custom_df, builtin_df], axis=0)
        elif not custom_df.empty:
            out = custom_df
        else:
            out = builtin_df

        if out.shape[1] == 0:
            out = pd.DataFrame(
                index=pd.Index([], name=like_index.name), columns=like_columns
            )
        else:
            out.columns = like_columns
        return out

    def _build_header_columns(
        self,
        dep_var_list: list[str],
        model_heads: list[str] | None,
        head_order: str,
        n_models: int,
    ) -> list[str] | pd.MultiIndex:
        id_dep = dep_var_list
        id_num = [f"({s})" for s in range(1, n_models + 1)]

        id_head = None
        if model_heads is not None:
            id_head = list(model_heads)
            if not any(str(h).strip() for h in id_head):
                id_head = None

        if head_order == "":
            return id_num

        header_levels: list[list[str]] = []
        for c in head_order:
            if c == "h" and id_head is not None:
                header_levels.append(id_head)
            if c == "d":
                header_levels.append(id_dep)
        header_levels.append(id_num)

        # filter out fully empty levels
        def non_empty(arr: list[str]) -> bool:
            return any((v is not None and str(v) != "") for v in arr)

        header_levels = [lvl for lvl in header_levels if non_empty(lvl)]

        if len(header_levels) == 1:
            return header_levels[0]
        return pd.MultiIndex.from_arrays(header_levels)




def _format_number(x: float, format_spec: str | None = None) -> str:
    """
    Format a number with optional format specifier.

    Parameters
    ----------
    x : float
        The number to format.
    format_spec : str, optional
        Format specifier (e.g., '.3f', '.2e', ',.0f', 'd').
        If None, uses sensible default formatting without scientific notation.

    Returns
    -------
    str
        The formatted number.
    """
    if pd.isna(x) or (isinstance(x, float) and np.isnan(x)):
        return "-"

    if format_spec is None:
        # Sensible default formatting without scientific notation
        abs_x = abs(x)

        # Check if it's essentially an integer first
        if abs(x - round(x)) < 1e-10:  # essentially an integer
            if abs_x >= 1000:
                return f"{int(round(x)):,}"  # Use comma separators for large integers
            else:
                return f"{int(round(x))}"  # No decimals for smaller integers

        # For very small numbers (close to zero), show more precision
        if abs_x < 0.001 and abs_x > 0:
            return f"{x:.6f}".rstrip("0").rstrip(".")
        # For small numbers, use standard precision
        elif abs_x < 1:
            return f"{x:.3f}".rstrip("0").rstrip(".")
        # For medium numbers, use standard precision
        elif abs_x < 1000:
            return f"{x:.3f}"
        # For large numbers, use comma separators
        elif abs_x >= 1000:
            return f"{x:,.2f}"
        else:
            return f"{x:.3f}"

    try:
        # Handle integer formatting
        if format_spec == "d":
            return f"{int(round(x)):d}"

        # Use Python's format specification
        return f"{x:{format_spec}}"
    except (ValueError, TypeError):
        # Fallback to default formatting if format_spec is invalid
        return _format_number(x, None)


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


def _parse_coef_fmt(coef_fmt: str, custom_stats: dict):
    """
    Parse the coef_fmt string with format specifiers.

    Parameters
    ----------
    coef_fmt: str
        The coef_fmt string. Supports format specifiers like 'b:.3f', 'se:.2e', etc.
    custom_stats: dict
        A dictionary of custom statistics. Key should be lowercased (e.g., simul_intv).
        If you provide "b", "se", "t", or "p" as a key, it will overwrite the default
        values.

    Returns
    -------
    coef_fmt_elements: list
        List of parsed elements, each being a dict with 'token' and 'format' keys.
    coef_fmt_title: str
        The title for the coef_fmt string.
    """
    custom_elements = list(custom_stats.keys())
    if any(x in ["b", "se", "t", "p"] for x in custom_elements):
        raise ValueError(
            "You cannot use 'b', 'se', 't', or 'p' as a key in custom_stats."
        )

    title_map = {
        "b": "Coefficient",
        "se": "Std. Error",
        "t": "t-stats",
        "p": "p-value",
    }

    # All possible tokens (base + custom)
    all_tokens = ["b", "se", "t", "p"] + custom_elements

    coef_fmt_elements = []
    title_parts = []
    i = 0

    while i < len(coef_fmt):
        found_token = False

        # Check for tokens with potential format specifiers
        for token in all_tokens:
            if coef_fmt[i:].startswith(token):
                # Check if followed by format specifier
                after_token_pos = i + len(token)
                if after_token_pos < len(coef_fmt) and coef_fmt[after_token_pos] == ":":
                    # Find the end of the format specifier
                    format_start = after_token_pos + 1
                    format_end = format_start
                    # Read until we hit a delimiter or token (but allow comma in format spec)
                    while (
                        format_end < len(coef_fmt)
                        and coef_fmt[format_end]
                        not in [" ", "\n", "(", ")", "[", "]", "\\"]
                        and not any(
                            coef_fmt[format_end:].startswith(t) for t in all_tokens
                        )
                    ):
                        format_end += 1

                    format_spec = coef_fmt[format_start:format_end]
                    coef_fmt_elements.append({"token": token, "format": format_spec})
                    title_parts.append(title_map.get(token, token))
                    i = format_end
                else:
                    # No format specifier
                    coef_fmt_elements.append({"token": token, "format": None})
                    title_parts.append(title_map.get(token, token))
                    i = after_token_pos
                found_token = True
                break

        if not found_token:
            # Handle special sequences and single characters
            if coef_fmt[i : i + 2] == "\\n":
                coef_fmt_elements.append({"token": "\n", "format": None})
                title_parts.append("\n")
                i += 2
            elif coef_fmt[i : i + 2] == "\\(":
                coef_fmt_elements.append({"token": r"\(", "format": None})
                title_parts.append("(")
                i += 2
            elif coef_fmt[i : i + 2] == "\\)":
                coef_fmt_elements.append({"token": r"\)", "format": None})
                title_parts.append(")")
                i += 2
            elif coef_fmt[i : i + 2] == "\\[":
                coef_fmt_elements.append({"token": r"\[", "format": None})
                title_parts.append("[")
                i += 2
            elif coef_fmt[i : i + 2] == "\\]":
                coef_fmt_elements.append({"token": r"\]", "format": None})
                title_parts.append("]")
                i += 2
            else:
                # Single character literal
                char = coef_fmt[i]
                coef_fmt_elements.append({"token": char, "format": None})
                title_parts.append(char)
                i += 1

    coef_fmt_title = "".join(title_parts)
    return coef_fmt_elements, coef_fmt_title


def _select_order_coefs(
    coefs: list,
    keep: list | str | None = None,
    drop: list | str | None = None,
    exact_match: bool | None = False,
):
    r"""
    Select and order the coefficients based on the pattern.

    Parameters
    ----------
    coefs: list
        Coefficient names to be selected and ordered.
    keep: str or list of str, optional
        The pattern for retaining coefficient names. You can pass a string (one
        pattern) or a list (multiple patterns). Default is keeping all coefficients.
        You should use regular expressions to select coefficients.
            "age",            # would keep all coefficients containing age
            r"^tr",           # would keep all coefficients starting with tr
            r"\\d$",          # would keep all coefficients ending with number
        Output will be in the order of the patterns.
    drop: str or list of str, optional
        The pattern for excluding coefficient names. You can pass a string (one
        pattern) or a list (multiple patterns). Syntax is the same as for `keep`.
        Default is keeping all coefficients. Parameter `keep` and `drop` can be
        used simultaneously.
    exact_match: bool, optional
        Whether to use exact match for `keep` and `drop`. Default is False.
        If True, the pattern will be matched exactly to the coefficient name
        instead of using regular expressions.

    Returns
    -------
    res: list
        The filtered and ordered coefficient names.
    """
    if keep is None:
        keep = []
    if drop is None:
        drop = []

    if isinstance(keep, str):
        keep = [keep]
    if isinstance(drop, str):
        drop = [drop]

    coefs = list(coefs)
    res = [] if keep else coefs[:]  # Store matched coefs
    for pattern in keep:
        _coefs = []  # Store remaining coefs
        for coef in coefs:
            if (exact_match and pattern == coef) or (
                exact_match is False and re.findall(pattern, coef)
            ):
                res.append(coef)
            else:
                _coefs.append(coef)
        coefs = _coefs

    for pattern in drop:
        _coefs = []
        for coef in res:  # Remove previously matched coefs that match the drop pattern
            if (exact_match and pattern == coef) or (
                exact_match is False and re.findall(pattern, coef)
            ):
                continue
            else:
                _coefs.append(coef)
        res = _coefs

    return res


def _has_format_specifiers(coef_fmt: str) -> bool:
    """
    Check if coef_fmt contains any format specifiers (e.g., 'b:.3f', 'se:.2e').

    Parameters
    ----------
    coef_fmt : str
        The coefficient format string to check.

    Returns
    -------
    bool
        True if format specifiers are found, False otherwise.
    """
    # Look for pattern like 'token:format' where token is b, se, t, p or custom
    # This is a simple check - if there's a colon after known tokens, assume format specs
    import re

    # Match patterns like 'b:', 'se:', 't:', 'p:', or any word followed by ':'
    return bool(re.search(r"\w+:", coef_fmt))


def _apply_digits_to_coef_fmt(coef_fmt: str, digits: int) -> str:
    """
    Apply digits formatting to a coef_fmt string that doesn't have format specifiers.

    Parameters
    ----------
    coef_fmt : str
        The coefficient format string.
    digits : int
        Number of decimal places to use.

    Returns
    -------
    str
        The updated coef_fmt string with format specifiers applied.
    """
    if digits < 0:
        digits = 0

    format_spec = f".{digits}f"

    # Replace tokens with formatted versions
    updated_fmt = coef_fmt

    # Replace 'b' with 'b:.Nf' (but not if it's already formatted)
    updated_fmt = re.sub(r"\bb\b(?!:)", f"b:{format_spec}", updated_fmt)

    # Replace 'se' with 'se:.Nf' (but not if it's already formatted)
    updated_fmt = re.sub(r"\bse\b(?!:)", f"se:{format_spec}", updated_fmt)

    # Replace 't' with 't:.Nf' (but not if it's already formatted)
    updated_fmt = re.sub(r"\bt\b(?!:)", f"t:{format_spec}", updated_fmt)

    # Replace 'p' with 'p:.Nf' (but not if it's already formatted)
    updated_fmt = re.sub(r"\bp\b(?!:)", f"p:{format_spec}", updated_fmt)

    return updated_fmt


def _relabel_expvar(
    varname: str, labels: dict, interaction_symbol: str, cat_template=""
):
    """
    Relabel a variable name using the labels dictionary
    Also automatically relabel interaction terms using the labels of the individual variables
    and categorical variables using the cat_template.

    Parameters
    ----------
    varname: str
        The varname in the regression.
    labels: dict
        A dictionary to relabel the variables. The keys are the original variable names and the values the new names.
    interaction_symbol: str
        The symbol to use for displaying the interaction term.
    cat_template: str
        Template to relabel categorical variables. When empty, the function will not relabel categorical variables.
        You can use {variable}, {value}, or {value_int} placeholders.
        e.g. "{variable}::{value_int}" if you want to force integer format when possible.

    Returns
    -------
    str
        The relabeled variable
    """
    # First split the variable name by the interaction symbol
    # Note: will just be equal to varname when no interaction term
    vars = varname.split(":")
    # Loop over the variables and relabel them
    for i in range(len(vars)):
        # Check whether template for categorical variables is provided &
        # whether the variable is a categorical variable
        v = vars[i]
        if cat_template != "" and ("C(" in v or "[" in v):
            vars[i] = _rename_categorical(v, template=cat_template, labels=labels)
        else:
            vars[i] = labels.get(v, v)
    # Finally join the variables using the interaction symbol
    return interaction_symbol.join(vars)


def _rename_categorical(
    col_name, template="{variable}::{value}", labels: dict | None = None
):
    """
    Rename categorical variables, optionally converting floats to ints in the category label.

    Parameters
    ----------
    col_name : str
        A single coefficient string (e.g. "C(var)[T.1]").
    template: str, optional
        String template for formatting. You can use {variable}, {value}, or {value_int} placeholders.
        e.g. "{variable}::{value_int}" if you want to force integer format when possible.
    labels: dict, optional
        Dictionary that replaces variable names with user-specified labels.

    Returns
    -------
    str
        The renamed categorical variable.
    """
    # Here two patterns are used to extract the variable and level
    # Note the second pattern matches the notation when the variable is categorical at the outset
    if col_name.startswith("C("):
        pattern = r"C\(([^,]+)(?:,[^]]+)?\)\[(?:T\.)?([^]]+)\]"
    else:
        pattern = r"([^[]+)\[(?:T\.)?([^]]+)\]"

    # Replace labels with empty dictionary if not provided
    if labels is None:
        labels = {}
    # Apply the regex to extract the variable and value
    match = re.search(pattern, col_name)
    if match:
        variable = match.group(1)
        variable = labels.get(variable, variable)  # apply label if any
        value_raw = match.group(2)

        # Try parsing as float so that e.g. "2.0" can become "2"
        value_int = value_raw
        try:
            numeric_val = float(value_raw)
            value_int = int(numeric_val) if numeric_val.is_integer() else numeric_val
        except ValueError:
            # If not numeric at all, we'll leave it as-is
            pass

        return template.format(variable=variable, value=value_raw, value_int=value_int)
    else:
        return col_name
