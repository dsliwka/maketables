import math
import re
import warnings
from collections import Counter
from collections.abc import ValuesView
from typing import Optional, Union, Any, List, Dict

import numpy as np
import pandas as pd
from tabulate import tabulate

from pyfixest.estimation.feiv_ import Feiv
from pyfixest.estimation.feols_ import Feols
from pyfixest.estimation.fepois_ import Fepois
from pyfixest.estimation.FixestMulti_ import FixestMulti
from pyfixest.report.utils import _relabel_expvar

from .tabout import TabOut
from .extractors import ModelExtractor, get_extractor

ModelInputType = Union[
    FixestMulti, Feols, Fepois, Feiv, list[Union[Feols, Fepois, Feiv]]
]

class ETable(TabOut):
    """
    ETable extends TabOut to generate regression tables from models.
    The class is modular: model extraction is delegated to helper methods
    that can be extended for other packages.
    """

    # ---- Class defaults (single source of truth) ----
    DEFAULT_SIGNIF_CODE = [0.001, 0.01, 0.05]
    DEFAULT_COEF_FMT = "b \n (se)"
    DEFAULT_MODEL_STATS = ["N", "r2"]
    DEFAULT_SHOW_SE_TYPE = True
    DEFAULT_SHOW_FE = True
    DEFAULT_HEAD_ORDER = "dh"
    DEFAULT_DIGITS = 3
    DEFAULT_LABELS: Dict[str, str] = {}
    DEFAULT_FELABELS: Dict[str, str] = {}
    DEFAULT_CAT_TEMPLATE = "{variable}={value}"
    DEFAULT_LINEBREAK = "\n"

    def __init__(
        self,
        models: ModelInputType,
        *,
        signif_code: Optional[list] = None,
        coef_fmt: Optional[str] = None,
        model_stats: Optional[list[str]] = None,
        model_stats_labels: Optional[dict[str, str]] = None,
        custom_stats: Optional[dict] = None,
        custom_model_stats: Optional[dict] = None,
        keep: Optional[Union[list, str]] = None,
        drop: Optional[Union[list, str]] = None,
        exact_match: Optional[bool] = False,
        labels: Optional[dict] = None,
        cat_template: Optional[str] = None,
        show_fe: Optional[bool] = None,
        felabels: Optional[dict] = None,
        notes: str = "",
        model_heads: Optional[list] = None,
        head_order: Optional[str] = None,
        caption: Optional[str] = None,
        tab_label: Optional[str] = None,
        digits: Optional[int] = None,
        **kwargs,
    ):
        # --- defaults from class attributes ---
        signif_code = self.DEFAULT_SIGNIF_CODE if signif_code is None else signif_code
        coef_fmt = self.DEFAULT_COEF_FMT if coef_fmt is None else coef_fmt
        labels = dict(self.DEFAULT_LABELS) if labels is None else labels
        cat_template = self.DEFAULT_CAT_TEMPLATE if cat_template is None else cat_template
        show_fe = self.DEFAULT_SHOW_FE if show_fe is None else show_fe
        felabels = dict(self.DEFAULT_FELABELS) if felabels is None else felabels
        head_order = self.DEFAULT_HEAD_ORDER if head_order is None else head_order
        digits = self.DEFAULT_DIGITS if digits is None else digits
        custom_stats = {} if custom_stats is None else custom_stats
        keep = [] if keep is None else keep
        drop = [] if drop is None else drop

        # --- checks  ---
        assert isinstance(signif_code, list) and len(signif_code) == 3
        if signif_code:
            assert all(0 < i < 1 for i in signif_code)
            assert signif_code[0] < signif_code[1] < signif_code[2]

        models = self._normalize_models(models)

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
            digits=digits,
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
            digits=digits,
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
        try:
            res_all.columns.names = [None] * res_all.columns.nlevels
        except Exception:
            pass

        # --- notes ---
        if notes == "":
            notes = (
                f"Significance levels: * p < {signif_code[2]}, ** p < {signif_code[1]}, *** p < {signif_code[0]}. "
                + f"Format of coefficient cell: {coef_fmt_title}"
            )

        super().__init__(
            res_all,
            notes=notes,
            caption=caption,
            tab_label=tab_label,
            rgroup_display=False,
            **kwargs,
        )

    # ---------- Dispatch helpers (package detection) ----------

    def _normalize_models(self, models: Any) -> List[Any]:
        # Expand FixestMulti if present, otherwise wrap single model into a list
        if isinstance(models, FixestMulti):
            return models.to_list()
        if isinstance(models, (Feols, Fepois, Feiv)):
            return [models]
        if isinstance(models, (list, tuple, ValuesView)):
            return list(models)
        return [models]

    def _get_extractor(self, model: Any) -> ModelExtractor:
        return get_extractor(model)

    # --- delegate helpers to extractor ---

    def _extract_depvar(self, model: Any) -> str:
        return self._get_extractor(model).depvar(model)

    def _extract_fixef_string(self, model: Any) -> Optional[str]:
        return self._get_extractor(model).fixef_string(model)

    def _extract_vcov_info(self, model: Any) -> Dict[str, Any]:
        return self._get_extractor(model).vcov_info(model)

    def _extract_tidy_df(self, model: Any) -> pd.DataFrame:
        df = self._get_extractor(model).coef_table(model)
        # enforce index name
        if df.index.name != "Coefficient":
            df.index.name = "Coefficient"
        return df

    def _extract_stat(self, model: Any, key: str, digits: int) -> str:
        raw = self._get_extractor(model).stat(model, key)
        # format uniformly
        if key == "se_type":
            return raw or "-"
        if raw is None:
            return "-"
        if isinstance(raw, (int, np.integer)):
            return _number_formatter(float(raw), integer=True, digits=digits)
        if isinstance(raw, (float, np.floating)):
            return "-" if math.isnan(raw) else _number_formatter(float(raw), digits=digits)
        return str(raw)

 
    def _collect_fixef_list(self, models: List[Any], show_fe: bool) -> List[str]:
        if not show_fe:
            return []
        fixef_list: List[str] = []
        for m in models:
            fx = self._extract_fixef_string(m)
            if fx and fx != "0":
                fixef_list += fx.split("+")
        fixef_list = [x for x in fixef_list if x]
        return sorted(set(fixef_list))

    def _compute_stars(self, p: pd.Series, signif_code: List[float]) -> pd.Series:
        if not signif_code:
            return pd.Series([""] * len(p), index=p.index)
        s = pd.Series("", index=p.index, dtype=object)
        s = np.where(p < signif_code[0], "***", np.where(p < signif_code[1], "**", np.where(p < signif_code[2], "*", "")))
        return pd.Series(s, index=p.index)

    def _build_coef_table(
        self,
        models: List[Any],
        coef_fmt: str,
        signif_code: List[float],
        digits: int,
        custom_stats: Dict[str, List[list]],
        keep: List[str],
        drop: List[str],
        exact_match: bool,
        labels: Dict[str, str],
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
                if element == "b":
                    cell += tidy["Estimate"].apply(_number_formatter, digits=digits) + stars
                elif element == "se":
                    cell += tidy["Std. Error"].apply(_number_formatter, digits=digits)
                elif element == "t":
                    if "t value" in tidy.columns:
                        cell += tidy["t value"].apply(_number_formatter, digits=digits)
                elif element == "p":
                    cell += tidy["Pr(>|t|)"].apply(_number_formatter, digits=digits)
                elif element in custom_stats:
                    assert len(custom_stats[element][i]) == len(tidy["Estimate"])
                    cell += pd.Series(custom_stats[element][i], index=tidy.index).apply(_number_formatter, digits=digits)
                elif element == "\n":
                    cell += lbcode
                else:
                    cell += element

            # one column per model, indexed by 'Coefficient'
            df_i = pd.DataFrame({f"est{i+1}": pd.Categorical(cell)}, index=tidy.index)
            df_i.index.name = "Coefficient"
            cols_per_model.append(df_i)

        # align on coefficient names
        res = pd.concat(cols_per_model, axis=1)
        res.index.name = "Coefficient"

        # keep/drop ordering on the index (no reset)
        idxs = _select_order_coefs(res.index.tolist(), keep, drop, exact_match) if (keep or drop) else res.index.tolist()
        res = res.loc[idxs]

        # fill NA and ensure empty category exists
        for c in res.columns:
            col = res[c]
            if isinstance(col.dtype, pd.CategoricalDtype) and "" not in col.cat.categories:
                res[c] = col.cat.add_categories([""])
            res[c] = res[c].fillna("")

        # move intercept to bottom
        if "Intercept" in res.index:
            order = [ix for ix in res.index if ix != "Intercept"] + ["Intercept"]
            res = res.loc[order]

        # relabel coefficient index
        if (labels != {}) or (cat_template != ""):
            res.index = res.index.to_series().apply(lambda x: _relabel_expvar(x, labels or {}, " x ", cat_template))
            res.index.name = "Coefficient"

        return res, coef_fmt_title

    def _build_fe_df(
        self,
        models: List[Any],
        fixef_list: List[str],
        show_fe: bool,
        labels: Dict[str, str],
        felabels: Optional[Dict[str, str]],
        like_columns: pd.Index,
    ) -> pd.DataFrame:
        if not (show_fe and fixef_list):
            return pd.DataFrame(index=pd.Index([], name=None), columns=like_columns)
        rows = {}
        for fx in fixef_list:
            row = []
            for m in models:
                fx_str = self._extract_fixef_string(m) or ""
                has = (fx_str != "") and (fx in fx_str.split("+")) and not getattr(m, "_use_mundlak", False)
                row.append("x" if has else "-")
            rows[fx] = row
        fe_df = pd.DataFrame.from_dict(rows, orient="index", columns=list(like_columns))
        # relabel FE names
        felabels = felabels or {}
        labels = labels or {}
        fe_df.index = fe_df.index.to_series().apply(lambda x: felabels.get(x, labels.get(x, x)))
        return fe_df

    def _build_model_stats(
        self,
        models: List[Any],
        stat_keys: List[str],
        stat_labels: Optional[Dict[str, str]],
        custom_model_stats: Optional[Dict[str, list]],
        digits: int,
        like_index: pd.Index,
        like_columns: pd.Index,
    ) -> pd.DataFrame:
        # builtin stats via extractor
        def label_of(k: str) -> str:
            default = {
                "N": "Observations",
                "se_type": "S.E. type",
                "r2": "R2",
                "adj_r2": "Adj. R2",
                "r2_within": "R2 Within",
            }.get(k, k)
            return stat_labels.get(k, default) if stat_labels else default

        rows = {label_of(k): [self._extract_stat(m, k, digits) for m in models] for k in stat_keys}
        builtin_df = pd.DataFrame.from_dict(rows, orient="index") if rows else pd.DataFrame()

        # custom bottom rows
        custom_df = pd.DataFrame.from_dict(custom_model_stats, orient="index") if custom_model_stats else pd.DataFrame()

        if not custom_df.empty and not builtin_df.empty:
            out = pd.concat([custom_df, builtin_df], axis=0)
        elif not custom_df.empty:
            out = custom_df
        else:
            out = builtin_df

        if out.shape[1] == 0:
            out = pd.DataFrame(index=pd.Index([], name=like_index.name), columns=like_columns)
        else:
            out.columns = like_columns
        return out

    def _build_header_columns(
        self,
        dep_var_list: List[str],
        model_heads: Optional[List[str]],
        head_order: str,
        n_models: int,
    ) -> Union[List[str], pd.MultiIndex]:
        id_dep = dep_var_list
        id_num = [f"({s})" for s in range(1, n_models + 1)]

        id_head = None
        if model_heads is not None:
            id_head = list(model_heads)
            if not any(str(h).strip() for h in id_head):
                id_head = None

        if head_order == "":
            return id_num

        header_levels: List[List[str]] = []
        for c in head_order:
            if c == "h" and id_head is not None:
                header_levels.append(id_head)
            if c == "d":
                header_levels.append(id_dep)
        header_levels.append(id_num)

        # filter out fully empty levels
        def non_empty(arr: List[str]) -> bool:
            return any((v is not None and str(v) != "") for v in arr)
        header_levels = [lvl for lvl in header_levels if non_empty(lvl)]

        if len(header_levels) == 1:
            return header_levels[0]
        return pd.MultiIndex.from_arrays(header_levels)


def _post_processing_input_checks(
    models: ModelInputType,
    check_duplicate_model_names: bool = False,
    rename_models: Optional[dict[str, str]] = None,
) -> list[Union[Feols, Fepois, Feiv]]:
    """
    Perform input checks for post-processing models.

    Parameters
    ----------
        models : Union[List[Union[Feols, Fepois, Feiv]], FixestMulti]
                The models to be checked. This can either be a list of models
                (Feols, Fepois, Feiv) or a single FixestMulti object.
        check_duplicate_model_names : bool, optional
                Whether to check for duplicate model names. Default is False.
                Mostly used to avoid overlapping models in plots created via
                pf.coefplot() and pf.iplot().
        rename_models : dict, optional
                A dictionary to rename the models. The keys are the original model names
                and the values are the new model names.

    Returns
    -------
        List[Union[Feols, Fepois]]
            A list of checked and validated models. The returned list contains only
            Feols and Fepois types.

    Raises
    ------
        TypeError: If the models argument is not of the expected type.

    """
    models_list: list[Union[Feols, Fepois, Feiv]] = []

    if isinstance(models, (Feols, Fepois, Feiv)):
        models_list = [models]
    elif isinstance(models, FixestMulti):
        models_list = models.to_list()
    elif isinstance(models, (list, ValuesView)):
        if all(isinstance(m, (Feols, Fepois, Feiv)) for m in models):
            models_list = models
        else:
            raise TypeError(
                "All elements in the models list must be instances of Feols, Feiv, or Fepois."
            )
    else:
        raise TypeError("Invalid type for models argument.")

    if check_duplicate_model_names or rename_models is not None:
        all_model_names = [model._model_name for model in models_list]

    if check_duplicate_model_names:
        # create model_name_plot attribute to differentiate between models with the
        # same model_name / model formula
        for model in models_list:
            model._model_name_plot = model._model_name

        counter = Counter(all_model_names)
        duplicate_model_names = [item for item, count in counter.items() if count > 1]

        for duplicate_model in duplicate_model_names:
            duplicates = [
                model for model in models_list if model._model_name == duplicate_model
            ]
            for i, model in enumerate(duplicates):
                model._model_name_plot = f"Model {i}: {model._model_name}"
                warnings.warn(
                    f"The _model_name attribute {model._model_name}' is duplicated for models in the `models` you provided. To avoid overlapping model names / plots, the _model_name_plot attribute has been changed to '{model._model_name_plot}'."
                )

        if rename_models is not None:
            model_name_diff = set(rename_models.keys()) - set(all_model_names)
            if model_name_diff:
                warnings.warn(
                    f"""
                    The following model names specified in rename_models are not found in the models:
                    {model_name_diff}
                    """
                )

    return models_list





def _number_formatter(x: float, **kwargs) -> str:
    """
    Format a number.

    Parameters
    ----------
    x: float
        The series to be formatted.
    digits: int
        The number of digits to round to.
    thousands_sep: bool, optional
        The thousands separator. Default is False.
    scientific_notation: bool, optional
        Whether to use scientific notation. Default is True.
    scientific_notation_threshold: int, optional
        The threshold for using scientific notation. Default is 10_000.
    integer: bool, optional
        Whether to format the number as an integer. Default is False.

    Returns
    -------
    formatted_x: pd.Series
        The formatted series.
    """
    digits = kwargs.get("digits", 3)
    thousands_sep = kwargs.get("thousands_sep", False)
    scientific_notation = kwargs.get("scientific_notation", True)
    scientific_notation_threshold = kwargs.get("scientific_notation_threshold", 10_000)
    integer = kwargs.get("integer", False)

    assert digits >= 0, "digits must be a positive integer"

    if integer:
        digits = 0
    x = np.round(x, digits)

    if scientific_notation and x > scientific_notation_threshold:
        return f"%.{digits}E" % x

    x_str = f"{x:,}" if thousands_sep else str(x)

    if "." not in x_str:
        x_str += ".0"  # Add a decimal point if it's an integer
    _int, _float = str(x_str).split(".")
    _float = _float.ljust(digits, "0")
    return _int if digits == 0 else f"{_int}.{_float}"



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
    Parse the coef_fmt string.

    Parameters
    ----------
    coef_fmt: str
        The coef_fmt string.
    custom_stats: dict
        A dictionary of custom statistics. Key should be lowercased (e.g., simul_intv).
        If you provide "b", "se", "t", or "p" as a key, it will overwrite the default
        values.

    Returns
    -------
    coef_fmt_elements: str
        The parsed coef_fmt string.
    coef_fmt_title: str
        The title for the coef_fmt string.
    """
    custom_elements = list(custom_stats.keys())
    if any([x in ["b", "se", "t", "p"] for x in custom_elements]):
        raise ValueError(
            "You cannot use 'b', 'se', 't', or 'p' as a key in custom_stats."
        )

    title_map = {
        "b": "Coefficient",
        "se": "Std. Error",
        "t": "t-stats",
        "p": "p-value",
    }

    allowed_elements = [
        "b",
        "se",
        "t",
        "p",
        " ",
        "\n",
        r"\(",
        r"\)",
        r"\[",
        r"\]",
        ",",
        *custom_elements,
    ]
    allowed_elements.sort(key=len, reverse=True)

    coef_fmt_elements = re.findall("|".join(allowed_elements), coef_fmt)
    coef_fmt_title = "".join([title_map.get(x, x) for x in coef_fmt_elements])

    return coef_fmt_elements, coef_fmt_title




def _select_order_coefs(
    coefs: list,
    keep: Optional[Union[list, str]] = None,
    drop: Optional[Union[list, str]] = None,
    exact_match: Optional[bool] = False,
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
