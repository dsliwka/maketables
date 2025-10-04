"""
Statistical Model Extractor System for MakeTables

This module provides a unified interface for extracting statistical information
from various Python statistical modeling packages (statsmodels, pyfixest, linearmodels).
The extractor system uses a Protocol-based design for type safety and extensibility.
"""

from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from .importdta import get_var_labels

# Optional imports for built-ins
try:
    from pyfixest.estimation.feiv_ import Feiv
    from pyfixest.estimation.feols_ import Feols
    from pyfixest.estimation.fepois_ import Fepois
except Exception:
    Feols = Fepois = Feiv = ()  # type: ignore

try:
    from linearmodels.iv import IV2SLSResults, IVGMMResults
    from linearmodels.panel import PanelOLSResults, RandomEffectsResults
except Exception:
    PanelOLSResults = RandomEffectsResults = IV2SLSResults = IVGMMResults = ()  # type: ignore


@runtime_checkable
class ModelExtractor(Protocol):
    """
    Protocol defining the interface for statistical model extractors.

    This protocol ensures that all extractor implementations provide a consistent
    interface for extracting coefficients, statistics, and metadata from statistical models.
    The @runtime_checkable decorator allows isinstance() checks at runtime.
    """

    def can_handle(self, model: Any) -> bool:
        "Check if this extractor can handle the given model type."
        ...

    def coef_table(self, model: Any) -> pd.DataFrame:
        """
        Extract coefficient table with columns: Estimate, Std. Error, Pr(>|t|), and t value.

        Returns
        -------
            DataFrame with coefficient estimates, standard errors, p-values, and t-statistics.
        """
        ...

    def depvar(self, model: Any) -> str:
        """Extract the dependent variable name from the model."""
        ...

    def fixef_string(self, model: Any) -> str | None:
        """
        Extract fixed effects specification as a string.

        Returns
        -------
            String describing fixed effects (e.g., "entity+time") or None if no fixed effects.
        """
        ...

    def stat(self, model: Any, key: str) -> Any:
        """
        Extract a specific statistic from the model.

        Args:
            model: Statistical model object
            key: Statistic key (e.g., "N", "r2", "adj_r2", "fvalue")

        Returns
        -------
            The requested statistic value or None if not available.
        """
        ...

    def vcov_info(self, model: Any) -> dict[str, Any]:
        """
        Extract variance-covariance matrix information.

        Returns
        -------
            Dictionary with vcov_type and clustervar information.
        """
        ...

    def var_labels(self, model: Any) -> dict[str, str] | None:
        """
        Extract variable labels from the model's data. Note: this allows to access maketables'
        variable labeling system if the model retains a reference to the original DataFrame and
        checks whether the DataFrame has variable labels (attribute `var_labels`).

        Returns
        -------
            Dictionary mapping variable names to descriptive labels, or None if unavailable.
        """
        ...

    def supported_stats(self, model: Any) -> set[str]:
        """
        Get the set of statistics this extractor can provide for the given model.

        Returns
        -------
            Set of statistic keys that are available for this model.
        """
        ...


_EXTRACTOR_REGISTRY: list[ModelExtractor] = []


def register_extractor(extractor: ModelExtractor) -> None:
    """
    Register a model extractor in the global registry.

    Args:
        extractor: ModelExtractor instance to register.
    """
    _EXTRACTOR_REGISTRY.append(extractor)


def clear_extractors() -> None:
    "Clear all registered extractors from the registry."
    _EXTRACTOR_REGISTRY.clear()


def get_extractor(model: Any) -> ModelExtractor:
    """
    Find and return the appropriate extractor for a given model.

    Iterates through registered extractors and returns the first one that
    can handle the given model type.

    Args:
        model: Statistical model object to find an extractor for.

    Returns
    -------
        ModelExtractor instance that can handle the model.

    Raises
    ------
        TypeError: If no registered extractor can handle the model type.
    """
    for ex in _EXTRACTOR_REGISTRY:
        try:
            if ex.can_handle(model):
                return ex
        except Exception:
            continue
    raise TypeError(f"No extractor available for model type: {type(model).__name__}")


# ---------- small helpers ----------


def _follow(obj: Any, chain: list[str]) -> Any:
    """
    Follow a chain of attribute names to extract nested values.

    Args:
        obj: Starting object to traverse from.
        chain: List of attribute names to follow sequentially.

    Returns
    -------
        The final nested attribute value, or None if any attribute in the chain doesn't exist.

    Example:
        _follow(model, ["model", "endog", "name"]) returns model.model.endog.name
    """
    cur = obj
    for a in chain:
        if hasattr(cur, a):
            cur = getattr(cur, a)
        else:
            return None
    return cur


def _get_attr(model: Any, spec: Any) -> Any:
    """
    Resolve a STAT_MAP specification against a model object.

    This function provides a unified way to extract attributes from statistical models
    using different specification formats:

    Args:
        model: Statistical model object to extract from.
        spec: Specification for how to extract the value, can be:
            - str: Direct attribute name ("attr") -> tries model.attr, then model.model.attr
            - tuple/list: Nested attribute path ("a","b","c") -> model.a.b.c via _follow()
            - callable: Function to compute value -> spec(model)

    Returns
    -------
        The extracted value, or None if the specification cannot be resolved.

    Examples
    --------
        _get_attr(model, "nobs")  # Returns model.nobs or model.model.nobs
        _get_attr(model, ("model", "endog", "name"))  # Returns model.model.endog.name
        _get_attr(model, lambda m: m.s2 ** 0.5)  # Returns computed RMSE
    """
    if isinstance(spec, str):
        return getattr(model, spec, getattr(getattr(model, "model", None), spec, None))
    if isinstance(spec, (list, tuple)):
        return _follow(model, list(spec))
    if callable(spec):
        try:
            return spec(model)
        except Exception:
            return None
    return None


# ---------- Built-in extractors ----------


class PyFixestExtractor:
    """
    Extractor for pyfixest models (Feols, Fepois, Feiv).

    Handles models from the pyfixest package, providing access to
    coefficients, statistics, and metadata. Supports clustered standard errors
    and fixed effects specifications.
    """

    def can_handle(self, model: Any) -> bool:
        """Check if model is a pyfixest model type."""
        try:
            return isinstance(model, (Feols, Fepois, Feiv))
        except Exception:
            return False

    def coef_table(self, model: Any) -> pd.DataFrame:
        """
        Extract coefficient table from pyfixest model using tidy() method.

        Standardizes column names and ensures required columns are present.

        Returns
        -------
            DataFrame with columns: Estimate, Std. Error, Pr(>|t|), and t value.
        """
        df = model.tidy()
        if "Estimate" not in df.columns or "Std. Error" not in df.columns:
            raise ValueError(
                "PyFixestExtractor: tidy() must contain 'Estimate' and 'Std. Error'."
            )
        if "Pr(>|t|)" not in df.columns:
            raise ValueError("PyFixestExtractor: tidy() must contain 'Pr(>|t|)'.")
        keep = ["Estimate", "Std. Error", "Pr(>|t|)"]
        if "t value" in df.columns:
            keep.insert(2, "t value")
        return df[keep]

    def depvar(self, model: Any) -> str:
        """Extract dependent variable name from pyfixest model."""
        return getattr(model, "_depvar", "y")

    def fixef_string(self, model: Any) -> str | None:
        """Extract fixed effects specification string from pyfixest model."""
        return getattr(model, "_fixef", None)

    # Build a clean map of unified stat keys -> pyfixest attributes/callables
    STAT_MAP: dict[str, Any] = {
        "N": "_N",
        "se_type": lambda m: (
            "by: " + "+".join(getattr(m, "_clustervar", []))
            if getattr(m, "_vcov_type", None) == "CRV"
            and getattr(m, "_clustervar", None)
            else getattr(m, "_vcov_type", None)
        ),
        "r2": "_r2",
        "adj_r2": "_r2_adj",
        "r2_within": "_r2_within",
        "adj_r2_within": "_adj_r2_within",
        "rmse": "_rmse",
        "fvalue": "_F_stat",
        "fstat_1st": "_f_stat_1st_stage",
        # pyfixest may return a sequence; take the first element
        "deviance": lambda m: (
            (getattr(m, "deviance", None)[0])
            if isinstance(
                getattr(m, "deviance", None), (list, tuple, np.ndarray, pd.Series)
            )
            else getattr(m, "deviance", None)
        ),
    }

    def stat(self, model: Any, key: str) -> Any:
        """
        Extract a statistic from the pyfixest model using STAT_MAP.

        Args:
            model: Pyfixest model object.
            key: Statistic key (e.g., "N", "r2", "se_type").

        Returns
        -------
            The requested statistic value, with special handling for sample size (N).
        """
        spec = self.STAT_MAP.get(key)
        if spec is None:
            return None
        val = _get_attr(model, spec)
        if key == "N" and val is not None:
            try:
                return int(val)
            except Exception:
                return val
        return val

    def vcov_info(self, model: Any) -> dict[str, Any]:
        "Extract variance-covariance matrix type and clustering information."
        return {
            "vcov_type": getattr(model, "_vcov_type", None),
            "clustervar": getattr(model, "_clustervar", None),
        }

    def var_labels(self, model: Any) -> dict[str, str] | None:
        "Extract variable labels from the model's data DataFrame when available."
        df = getattr(model, "_data", None)
        if isinstance(df, pd.DataFrame):
            try:
                return get_var_labels(df, include_defaults=True)
            except Exception:
                return None
        return None

    def supported_stats(self, model: Any) -> set[str]:
        "Return set of statistics available for the given pyfixest model."
        return {
            k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None
        }


class StatsmodelsExtractor:
    """
    Extractor for statsmodels regression results.

    Handles most statsmodels result objects that have the standard interface
    with params, bse (standard errors), and pvalues attributes. Supports
    various regression types including OLS, GLM, and others.
    """

    def can_handle(self, model: Any) -> bool:
        "Check if model has the standard statsmodels result interface."
        return all(hasattr(model, a) for a in ("params", "bse", "pvalues"))

    def coef_table(self, model: Any) -> pd.DataFrame:
        """
        Extract coefficient table from statsmodels result.

        Constructs standardized DataFrame from params, bse, pvalues, and
        optionally tvalues attributes of the statsmodels result.

        Returns
        -------
            DataFrame with columns: Estimate, Std. Error, Pr(>|t|), and optionally t value.
        """
        params = pd.Series(model.params)
        params.index.name = "Coefficient"
        se = pd.Series(getattr(model, "bse", np.nan), index=params.index)
        pvalues = pd.Series(getattr(model, "pvalues", np.nan), index=params.index)
        tvalues = getattr(model, "tvalues", None)

        df = pd.DataFrame(
            {
                "Estimate": pd.to_numeric(params, errors="coerce"),
                "Std. Error": pd.to_numeric(se, errors="coerce"),
                "Pr(>|t|)": pd.to_numeric(pvalues, errors="coerce"),
            },
            index=params.index,
        )
        if tvalues is not None:
            df["t value"] = pd.to_numeric(
                pd.Series(tvalues, index=params.index), errors="coerce"
            )
            df = df[["Estimate", "Std. Error", "t value", "Pr(>|t|)"]]
        return df

    def depvar(self, model: Any) -> str:
        """
        Extract dependent variable name from statsmodels result.

        Tries multiple common locations for the dependent variable name
        in statsmodels results objects.

        Returns
        -------
            Dependent variable name or "y" if not found.
        """
        for chain in [
            ("model", "endog_names"),
            ("endog_names",),
            ("model", "endog", "name"),
        ]:
            obj = model
            ok = True
            for a in chain:
                if hasattr(obj, a):
                    obj = getattr(obj, a)
                else:
                    ok = False
                    break
            if ok and isinstance(obj, str):
                return obj
        return "y"

    def fixef_string(self, model: Any) -> str | None:
        "Statsmodels doesn't typically have fixed effects notation."
        return None

    # Unified stat keys -> statsmodels attributes/callables
    STAT_MAP: dict[str, Any] = {
        "N": "nobs",
        "se_type": "cov_type",
        "r2": "rsquared",
        "adj_r2": "rsquared_adj",
        "pseudo_r2": "prsquared",
        "ll": "llf",
        "llnull": "llnull",
        "aic": "aic",
        "bic": "bic",
        "df_model": "df_model",
        "df_resid": "df_resid",
        "deviance": "deviance",
        "null_deviance": "null_deviance",
        "fvalue": "fvalue",
        "f_pvalue": "f_pvalue",
    }

    def stat(self, model: Any, key: str) -> Any:
        "Extract statistics."
        spec = self.STAT_MAP.get(key)
        if spec is None:
            return None
        val = _get_attr(model, spec)
        if key == "N" and val is not None:
            try:
                return int(val)
            except Exception:
                return val
        return val

    def vcov_info(self, model: Any) -> dict[str, Any]:
        return {"vcov_type": getattr(model, "cov_type", None), "clustervar": None}

    def var_labels(self, model: Any) -> dict[str, str] | None:
        # Try common statsmodels formula-api locations for the original DataFrame
        candidates = [
            ("model", "model", "data", "frame"),
            ("model", "data", "frame"),
        ]
        for chain in candidates:
            df = _follow(model, list(chain))
            if isinstance(df, pd.DataFrame):
                try:
                    return get_var_labels(df, include_defaults=True)
                except Exception:
                    return None
        return None

    def supported_stats(self, model: Any) -> set[str]:
        return {
            k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None
        }


class LinearmodelsExtractor:
    def can_handle(self, model: Any) -> bool:
        "Check if model is a linearmodels model."
        mod = type(model).__module__ or ""
        if mod.startswith("linearmodels."):
            # Core results interface in linearmodels
            return (
                hasattr(model, "params")
                and hasattr(model, "pvalues")
                and hasattr(model, "std_errors")
            )
        # Fallback: attribute-based detection (avoid grabbing statsmodels)
        return False

    def coef_table(self, model: Any) -> pd.DataFrame:
        "Extract coefficient table from linearmodels model."
        params = pd.Series(model.params)
        se = pd.Series(getattr(model, "std_errors", np.nan), index=params.index)
        pvalues = pd.Series(getattr(model, "pvalues", np.nan), index=params.index)
        tstats = getattr(model, "tstats", None)

        df = pd.DataFrame(
            {
                "Estimate": pd.to_numeric(params, errors="coerce"),
                "Std. Error": pd.to_numeric(se, errors="coerce"),
                "Pr(>|t|)": pd.to_numeric(pvalues, errors="coerce"),
            },
            index=params.index,
        )
        if tstats is not None:
            df["t value"] = pd.to_numeric(
                pd.Series(tstats, index=params.index), errors="coerce"
            )
            df = df[["Estimate", "Std. Error", "t value", "Pr(>|t|)"]]
        return df

    def depvar(self, model: Any) -> str:
        "Extract dependent variable name from linearmodels model."
        # Try common locations
        for chain in [
            ("model", "formula"),  # 'y ~ x1 + x2'
            ("model", "dependent", "name"),
            ("model", "dependent", "var_name"),
            ("model", "dependent", "pandas", "name"),
        ]:
            val = _follow(model, list(chain))
            if isinstance(val, str):
                if chain[-1] == "formula" and "~" in val:
                    return val.split("~", 1)[0].strip()
                return val
        return "y"

    def fixef_string(self, model: Any) -> str | None:
        "Extract fixed effects specification string from linearmodels model."
        mdl = getattr(model, "model", None)
        if mdl is None:
            return None
        parts = []
        if getattr(mdl, "entity_effects", False):
            parts.append("entity")
        if getattr(mdl, "time_effects", False):
            parts.append("time")
        other = getattr(mdl, "other_effects", None)
        if other:
            parts.append("other")
        return "+".join(parts) if parts else None

    # Unified stat keys -> linearmodels attributes/callables
    STAT_MAP: dict[str, Any] = {
        # Sizes / DoF
        "N": "nobs",
        "df_model": "df_model",
        "df_resid": "df_resid",
        # VCOV type
        "se_type": "cov_type",
        # R-squared family
        "r2": "rsquared",
        "adj_r2": "rsquared_adj",
        "r2_within": "rsquared_within",
        "r2_between": "rsquared_between",
        "r2_overall": "rsquared_overall",
        # Information criteria / likelihood (if exposed)
        "aic": "aic",
        "bic": "bic",
        "ll": "loglik",
        # F-stat (when available)
        "fvalue": lambda m: getattr(getattr(m, "f_statistic", None), "stat", None),
        "f_pvalue": lambda m: getattr(getattr(m, "f_statistic", None), "pval", None),
        # Error scale / RMSE
        "rmse": lambda m: (
            getattr(m, "root_mean_squared_error", None)
            if hasattr(m, "root_mean_squared_error")
            else (float(m.s2) ** 0.5 if hasattr(m, "s2") and m.s2 is not None else None)
        ),
        # IV diagnostics (if present on IV results)
        "j_stat": lambda m: getattr(getattr(m, "j_statistic", None), "stat", None),
        "j_pvalue": lambda m: getattr(getattr(m, "j_statistic", None), "pval", None),
        "first_stage_f": lambda m: (
            # take the first-stage F from the first endogenous if available
            (
                lambda fs: getattr(next(iter(fs.values())), "f_statistic", None).stat
                if isinstance(fs, dict) and fs
                else None
            )(getattr(m, "first_stage", None))
        ),
    }

    def stat(self, model: Any, key: str) -> Any:
        "Extract statistics."
        spec = self.STAT_MAP.get(key)
        if spec is None:
            return None
        val = _get_attr(model, spec)
        if key == "N" and val is not None:
            try:
                return int(val)
            except Exception:
                return val
        return val

    def vcov_info(self, model: Any) -> dict[str, Any]:
        "Extract variance-covariance matrix type and clustering information."
        return {"vcov_type": getattr(model, "cov_type", None), "clustervar": None}

    def var_labels(self, model: Any) -> dict[str, str] | None:
        # Try to locate original DataFrame
        candidates = [
            ("model", "data", "frame"),
            ("model", "dataframe"),
        ]
        for chain in candidates:
            df = _follow(model, list(chain))
            if isinstance(df, pd.DataFrame):
                try:
                    return get_var_labels(df, include_defaults=True)
                except Exception:
                    return None
        return None

    def supported_stats(self, model: Any) -> set[str]:
        return {
            k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None
        }


# Register built-ins
clear_extractors()
register_extractor(PyFixestExtractor())
register_extractor(LinearmodelsExtractor())
register_extractor(StatsmodelsExtractor())
