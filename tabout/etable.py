import math
import re
import warnings
from collections import Counter
from collections.abc import ValuesView
from typing import Optional, Union

import numpy as np
import pandas as pd
from tabulate import tabulate

from pyfixest.estimation.feiv_ import Feiv
from pyfixest.estimation.feols_ import Feols
from pyfixest.estimation.fepois_ import Fepois
from pyfixest.estimation.FixestMulti_ import FixestMulti
from pyfixest.report.utils import _relabel_expvar
from pyfixest.utils.dev_utils import _select_order_coefs

from .tabout import TabOut

ModelInputType = Union[
    FixestMulti, Feols, Fepois, Feiv, list[Union[Feols, Fepois, Feiv]]
]

class ETable(TabOut):
    """
    ETable extends TabOut to generate regression tables from pyfixest models.
    It builds the table once in __init__ and then uses TabOut's output methods.

    Parameters
    ----------
    models : list[Feols|Fepois|Feiv] | FixestMulti | single model
        Models to summarize.
    signif_code : list[float], optional
        Significance thresholds [0.001, 0.01, 0.05] (None for no stars).
    coef_fmt : str, optional
        Format string using tokens 'b','se','t','p' and newline '\\n', e.g. "b \\n (se)".
    model_stats : list[str], optional
        Model stats to show (attribute names without leading '_'), e.g. ["N","r2","adj_r2"].
    model_stats_labels : dict[str,str], optional
        Mapping of stat name -> display label.
    custom_stats : dict[str, list[list]], optional
        Custom per-coefficient statistics per model used in coef_fmt.
    custom_model_stats : dict[str, list], optional
        Extra bottom-panel model stats, keyed by row-label with values per model.
    keep, drop : list|str, optional
        Regex or exact-matching patterns to keep/drop coefficient rows.
    exact_match : bool, optional
        Use exact matching for keep/drop.
    labels : dict, optional
        Variable label mapping for relabeling coefficients (also applied to interactions).
    cat_template : str, optional
        Template for categorical variable relabels, e.g. "{variable}::{value}".
    show_fe : bool, optional
        Whether to show fixed-effects markers.
    show_se_type : bool, optional
        Whether to show standard error type in model stats when model_stats not provided.
    felabels : dict, optional
        Optional relabels for FE names.
    notes : str, optional
        Table notes. If empty, a generic note is generated.
    model_heads : list[str], optional
        Optional column headers per model.
    head_order : str, optional
        One of "dh","hd","d","h","". Controls depvar/headline order in top header.
    caption, tab_label : str, optional
        Table caption and label.
    digits : int, optional
        Rounding digits used in number formatting helpers.

    Usage
    -----
    et = ETable(models, caption="My table")
    et.make(type="gt")      # display in notebook (HTML)
    et.save(type="tex", file_name="...")  # TeX
    et.save(type="docx", file_name="...") # Word
    """

    def __init__(
        self,
        models: ModelInputType,
        *,
        signif_code: Optional[list] = None,
        coef_fmt: str = "b \n (se)",
        model_stats: Optional[list[str]] = None,
        model_stats_labels: Optional[dict[str, str]] = None,
        custom_stats: Optional[dict] = None,
        custom_model_stats: Optional[dict] = None,
        keep: Optional[Union[list, str]] = None,
        drop: Optional[Union[list, str]] = None,
        exact_match: Optional[bool] = False,
        labels: Optional[dict] = None,
        cat_template: Optional[str] = None,
        show_fe: Optional[bool] = True,
        show_se_type: Optional[bool] = True,
        felabels: Optional[dict] = None,
        notes: str = "",
        model_heads: Optional[list] = None,
        head_order: Optional[str] = "dh",
        caption: Optional[str] = None,
        tab_label: Optional[str] = None,
        digits: int = 3,
        **kwargs,
    ):
        # 1) Copy of validations/defaults from function etable (minus `type`)
        if signif_code is None:
            signif_code = [0.001, 0.01, 0.05]
        assert isinstance(signif_code, list) and len(signif_code) == 3, (
            "signif_code must be a list of length 3"
        )
        if signif_code:
            assert all([0 < i < 1 for i in signif_code]), (
                "All values of signif_code must be between 0 and 1"
            )
            assert signif_code[0] < signif_code[1] < signif_code[2], (
                "signif_code must be in increasing order"
            )

        cat_template = "" if cat_template is None else cat_template
        models = _post_processing_input_checks(models)

        labels = {} if labels is None else labels
        custom_stats = {} if custom_stats is None else custom_stats
        keep = [] if keep is None else keep
        drop = [] if drop is None else drop

        if custom_stats:
            assert isinstance(custom_stats, dict), "custom_stats must be a dict"
            for key in custom_stats:
                assert isinstance(custom_stats[key], list), "custom_stats values must be a list"
                assert len(custom_stats[key]) == len(models), (
                    f"custom_stats {key} must have the same number as models"
                )

        if model_heads is not None:
            assert len(model_heads) == len(models), (
                "model_heads must have the same length as models"
            )

        assert head_order in ["dh", "hd", "d", "h", ""], "head_order must be one of 'd','h','dh','hd',''"

        # 2) Collect basic model info
        dep_var_list: list[str] = []
        fixef_list: list[str] = []

        # For output-agnostic build we use literal newline; TabOut will convert for tex/html
        lbcode = "\n"

        for model in models:
            dep_var_list.append(model._depvar)
            if model._fixef is not None and model._fixef != "0":
                fixef_list += model._fixef.split("+")

        if show_fe:
            fixef_list = [x for x in fixef_list if x]
            fixef_list = list(set(fixef_list))
            n_fixef = len(fixef_list)
        else:
            fixef_list = []
            n_fixef = 0

        # Default model stats if not provided (legacy emulation)
        if model_stats is None:
            any_within = any(
                hasattr(m, "_r2_within")
                and not math.isnan(getattr(m, "_r2_within", float("nan")))
                for m in models
            )
            model_stats = ["N"]
            if show_se_type:
                model_stats.append("se_type")
            model_stats += ["r2", "r2_within" if any_within else "adj_r2"]

        model_stats = list(model_stats)
        assert all(isinstance(s, str) for s in model_stats), "model_stats entries must be strings"
        assert len(model_stats) == len(set(model_stats)), "model_stats contains duplicate entries"

        # 3) Build bottom model stats
        def _default_label_plain(stat: str) -> str:
            mapping = {
                "N": "Observations",
                "se_type": "S.E. type",
                "r2": "R2",
                "adj_r2": "Adj. R2",
                "r2_within": "R2 Within",
            }
            return mapping.get(stat, stat)

        model_stats_rows: dict[str, list[str]] = {}
        for stat in model_stats:
            values = [_extract(m, stat, digits=digits) for m in models]
            label = _default_label_plain(stat)
            if model_stats_labels and stat in model_stats_labels:
                label = model_stats_labels[stat]
            model_stats_rows[label] = values

        if custom_model_stats is not None and len(custom_model_stats) > 0:
            custom_df = pd.DataFrame.from_dict(custom_model_stats, orient="index")
        else:
            custom_df = pd.DataFrame()

        builtin_df = pd.DataFrame.from_dict(model_stats_rows, orient="index") if model_stats_rows else pd.DataFrame()

        if not custom_df.empty and not builtin_df.empty:
            model_stats_df = pd.concat([custom_df, builtin_df], axis=0)
        elif not custom_df.empty:
            model_stats_df = custom_df
        else:
            model_stats_df = builtin_df

        if model_stats_df.shape[1] == 0:
            model_stats_df = pd.DataFrame(
                index=pd.Index([], name=None), columns=None
            )

        # 4) FE markers
        if show_fe and fixef_list:
            fe_rows = {}
            for fixef in fixef_list:
                row = []
                for model in models:
                    has = (
                        model._fixef is not None
                        and fixef in model._fixef.split("+")
                        and not model._use_mundlak
                    )
                    row.append("x" if has else "-")
                fe_rows[fixef] = row
            fe_df = pd.DataFrame.from_dict(fe_rows, orient="index")
        else:
            fe_df = pd.DataFrame()
            show_fe = False

        # 5) Coefficients block construction (same as function, but output-agnostic)
        coef_fmt_elements, coef_fmt_title = _parse_coef_fmt(coef_fmt, custom_stats)
        etable_list = []
        for i, model in enumerate(models):
            model_tidy_df = model.tidy()
            model_tidy_df.reset_index(inplace=True)
            model_tidy_df["stars"] = (
                np.where(
                    model_tidy_df["Pr(>|t|)"] < signif_code[0],
                    "***",
                    np.where(
                        model_tidy_df["Pr(>|t|)"] < signif_code[1],
                        "**",
                        np.where(model_tidy_df["Pr(>|t|)"] < signif_code[2], "*", ""),
                    ),
                )
                if signif_code
                else ""
            )
            model_tidy_df[coef_fmt_title] = ""
            for element in coef_fmt_elements:
                if element == "b":
                    model_tidy_df[coef_fmt_title] += (
                        model_tidy_df["Estimate"].apply(_number_formatter, digits=digits)
                        + model_tidy_df["stars"]
                    )
                elif element == "se":
                    model_tidy_df[coef_fmt_title] += model_tidy_df["Std. Error"].apply(
                        _number_formatter, digits=digits
                    )
                elif element == "t":
                    model_tidy_df[coef_fmt_title] += model_tidy_df["t value"].apply(
                        _number_formatter, digits=digits
                    )
                elif element == "p":
                    model_tidy_df[coef_fmt_title] += model_tidy_df["Pr(>|t|)"].apply(
                        _number_formatter, digits=digits
                    )
                elif element in custom_stats:
                    assert len(custom_stats[element][i]) == len(model_tidy_df["Estimate"]), (
                        f"custom_stats {element} has unequal length to the number of coefficients in model_tidy_df {i}"
                    )
                    model_tidy_df[coef_fmt_title] += pd.Series(
                        custom_stats[element][i]
                    ).apply(_number_formatter, digits=digits)
                elif element == "\n":
                    model_tidy_df[coef_fmt_title] += lbcode
                else:
                    model_tidy_df[coef_fmt_title] += element
            model_tidy_df[coef_fmt_title] = pd.Categorical(model_tidy_df[coef_fmt_title])
            model_tidy_df = model_tidy_df[["Coefficient", coef_fmt_title]]
            model_tidy_df = pd.melt(
                model_tidy_df,
                id_vars=["Coefficient"],
                var_name="Metric",
                value_name=f"est{i + 1}",
            )
            model_tidy_df = model_tidy_df.drop("Metric", axis=1).set_index("Coefficient")
            etable_list.append(model_tidy_df)

        res = pd.concat(etable_list, axis=1)

        # 6) Keep/drop and relabels
        if keep or drop:
            idxs = _select_order_coefs(res.index.tolist(), keep, drop, exact_match)
        else:
            idxs = res.index
        res = res.loc[idxs, :].reset_index()

        # Clean NA vs categorical
        for column in res.columns:
            if (
                isinstance(res[column].dtype, pd.CategoricalDtype)
                and "" not in res[column].cat.categories
            ):
                res[column] = res[column].cat.add_categories([""])
            res[column] = res[column].fillna("")

        res.rename(columns={"Coefficient": "index"}, inplace=True)
        res.set_index("index", inplace=True)

        # Move intercept to bottom
        if "Intercept" in res.index:
            intercept_row = res.loc["Intercept"]
            res = res.drop("Intercept")
            res = pd.concat([res, pd.DataFrame([intercept_row])])

        # Relabel variables (depvar and coefficients)
        if (labels != {}) or (cat_template != ""):
            dep_var_list = [labels.get(k, k) for k in dep_var_list]
            res_index = res.index.to_series()
            res_index = res_index.apply(
                lambda x: _relabel_expvar(x, labels or {}, " x ", cat_template)
            )
            res.set_index(res_index, inplace=True)

        # Relabel FE names
        if show_fe:
            if felabels is None:
                felabels = dict()
            if labels is None:
                labels = dict()
            fe_index = fe_df.index.to_series()
            fe_index = fe_index.apply(lambda x: felabels.get(x, labels.get(x, x)))
            fe_df.set_index(fe_index, inplace=True)

        # Align stats/fes columns to match res
        model_stats_df = model_stats_df.copy()
        if model_stats_df.shape[1] == 0:
            model_stats_df = pd.DataFrame(
                index=pd.Index([], name=res.index.name), columns=res.columns
            )
        else:
            model_stats_df.columns = res.columns
        if show_fe and not fe_df.empty:
            fe_df.columns = res.columns

        # Top header MultiIndex columns
        id_dep = dep_var_list
        id_head = [""] * len(models) if model_heads is None else model_heads
        id_num = [f"({s})" for s in range(1, len(models) + 1)]
        if head_order == "":
            res_all = pd.concat([res, fe_df, model_stats_df], keys=["coef", "fe", "stats"])
            res_all.columns = pd.Index(id_num)
        else:
            # Drop "h" from head_order if no model_heads provided
            if model_heads is None and "h" in head_order:
                head_order = head_order.replace("h", "")
            res_all = pd.concat([res, fe_df, model_stats_df], keys=["coef", "fe", "stats"])
            cindex = [{"h": id_head, "d": id_dep}[c] for c in head_order] + [id_num]
            res_all.columns = pd.MultiIndex.from_arrays(cindex)

        # Notes
        if notes == "":
            notes = (
                f"Significance levels: * p < {signif_code[2]}, ** p < {signif_code[1]}, *** p < {signif_code[0]}. "
                + f"Format of coefficient cell:\n{coef_fmt_title}"
            )

        # Show row groups? For regression tables typically False here
        rgroup_display = False

        # 7) Initialize TabOut with the assembled DataFrame
        super().__init__(
            res_all,
            notes=notes,
            caption=caption,
            tab_label=tab_label,
            rgroup_display=rgroup_display,
            **kwargs,
        )


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


def _tabulate_etable_md(df, n_coef, n_fixef, n_models, n_model_stats):
    """
    Format and tabulate a DataFrame.

    Parameters
    ----------
    - df (pandas.DataFrame): The DataFrame to be formatted and tabulated.
    - n_coef (int): The number of coefficients.
    - n_fixef (int): The number of fixed effects.
    - n_models (int): The number of models.
    - n_model_stats (int): The number of rows with model statistics.

    Returns
    -------
    - formatted_table (str): The formatted table as a string.
    """
    # Format the DataFrame for tabulate
    table = tabulate(
        df,
        headers="keys",
        showindex=False,
        colalign=["left"] + n_models * ["right"],
    )

    # Split the table into header and body
    header, body = table.split("\n", 1)

    # Add separating line after the third row
    body_lines = body.split("\n")
    body_lines.insert(2, "-" * len(body_lines[0]))
    if n_fixef > 0:
        body_lines.insert(-n_model_stats - n_fixef, "-" * len(body_lines[0]))
    body_lines.insert(-n_model_stats, "-" * len(body_lines[0]))
    body_lines.append("-" * len(body_lines[0]))

    # Join the lines back together
    formatted_table = "\n".join([header, "\n".join(body_lines)])

    # Print the formatted table
    return formatted_table


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


def _extract(model, key: str, **kwargs):
    """
    Extract the value of a model statistics from a model.

    Parameters
    ----------
    model: Any
        The model from which to extract the value.
    key: str
        The name of the statistic to extract. The method adds _ to the key and calls getattr on the model.

    Returns
    -------
    value: Any
        The extracted and formatted value.
    """
    if key == "se_type":
        if getattr(model, "_vcov_type", "") == "CRV":
            return "by: " + "+".join(getattr(model, "_clustervar", []))
        return getattr(model, "_vcov_type", None)
    attr_name = f"_{key}"
    val = getattr(model, attr_name, None)
    if val is None:
        return "-"
    if isinstance(val, (int, np.integer)):
        return _number_formatter(float(val), integer=True, **kwargs)
    if isinstance(val, (float, np.floating)):
        if math.isnan(val):
            return "-"
        return _number_formatter(float(val), **kwargs)
    if isinstance(val, bool):
        return str(val)
    return str(val)


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
    data: pd.Series, digits: int = 2, newline: bool = True, type=str
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

    Returns
    -------
    _format_mean_std : str
        The mean and standard deviation of the pandas Series formated as a string.

    """
    mean = data.mean()
    std = data.std()
    if newline:
        if type == "gt":
            return f"{mean:.{digits}f}<br>({std:.{digits}f})"
        elif type == "tex":
            return f"{mean:.{digits}f}\\\\({std:.{digits}f})"
    return f"{mean:.{digits}f} ({std:.{digits}f})"

