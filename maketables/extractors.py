"""
Statistical Model Extractor System for MakeTables

This module provides a unified interface for extracting statistical information
from various Python statistical modeling packages (statsmodels, pyfixest, linearmodels).
The extractor system uses a Protocol-based design for type safety and extensibility.
"""

from typing import Any, ClassVar, Protocol, runtime_checkable

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
    from duckreg.estimators import DuckRegression
except Exception:
    DuckRegression = ()  # type: ignore

try:
    # Import linearmodels result classes (not model classes!)
    from linearmodels.panel.results import PanelResults
    from linearmodels.iv.results import IVResults
    HAS_LINEARMODELS = True
    # All panel results inherit from PanelResults
    # All IV results inherit from IVResults (including AbsorbingLS)
    PanelOLSResults = RandomEffectsResults = PanelResults
    IV2SLSResults = IVGMMResults = IVResults
except Exception:
    HAS_LINEARMODELS = False
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
        """Check if this extractor can handle the given model type."""
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
    """Clear all registered extractors from the registry."""
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
    
    # Build helpful error message
    model_type = type(model).__name__
    model_module = type(model).__module__
    
    error_msg = (
        f"No extractor available for model type: {model_type} from {model_module}\n\n"
        f"Registered extractors ({len(_EXTRACTOR_REGISTRY)}):\n"
    )
    
    for i, extractor in enumerate(_EXTRACTOR_REGISTRY, 1):
        extractor_name = type(extractor).__name__
        error_msg += f"  {i}. {extractor_name}\n"
    
    error_msg += (
        "\nTo add support for additional model types, implement the ModelExtractor protocol "
        "and use register_extractor()."
    )
    
    raise TypeError(error_msg)


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
        # If pyfixest types are empty tuples, it means pyfixest is not available
        if Feols == ():
            return False
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
        fixef = getattr(model, "_fixef", None)
        if fixef is None:
            return None
        # Ensure we return a string (pyfixest might store it in various formats)
        if isinstance(fixef, str):
            return fixef
        # If it's a list or other iterable, join with +
        if isinstance(fixef, (list, tuple)):
            return "+".join(str(f) for f in fixef)
        # Otherwise convert to string
        return str(fixef)

    # Build a clean map of unified stat keys -> pyfixest attributes/callables
    STAT_MAP: ClassVar[dict[str, Any]] = {
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
        "f_statistic": "_f_stat_1st_stage",
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
        """Extract variance-covariance matrix type and clustering information."""
        return {
            "vcov_type": getattr(model, "_vcov_type", None),
            "clustervar": getattr(model, "_clustervar", None),
        }

    def var_labels(self, model: Any) -> dict[str, str] | None:
        """Extract variable labels from the model's data DataFrame when available."""
        df = getattr(model, "_data", None)
        if isinstance(df, pd.DataFrame):
            try:
                return get_var_labels(df, include_defaults=True)
            except Exception:
                return None
        return None

    def supported_stats(self, model: Any) -> set[str]:
        """Return set of statistics available for the given pyfixest model."""
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
        """Check if model has the standard statsmodels result interface."""
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
        """Statsmodels doesn't typically have fixed effects notation."""
        return None

    # Unified stat keys -> statsmodels attributes/callables
    STAT_MAP: ClassVar[dict[str, Any]] = {
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
        """Extract a specific statistic from a statsmodels fitted model."""
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
        """Extract variance-covariance information from a statsmodels fitted model."""
        return {"vcov_type": getattr(model, "cov_type", None), "clustervar": None}

    def var_labels(self, model: Any) -> dict[str, str] | None:
        """Extract variable labels from a statsmodels fitted model."""
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
        """Return set of statistics available for the given statsmodels model."""
        return {
            k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None
        }


class LinearmodelsExtractor:
    """Extractor for linearmodels regression results."""

    def can_handle(self, model: Any) -> bool:
        """Check if this extractor can handle the given model."""
        # If linearmodels types are empty tuples, linearmodels is not available
        if PanelOLSResults == ():
            return False
        
        # Check module first (fast check)
        mod = type(model).__module__ or ""
        if not mod.startswith("linearmodels."):
            return False
        
        # Check if it's a linearmodels result type
        # Need to handle both PanelResults and IVResults (AbsorbingLS is IVResults)
        if isinstance(model, (PanelOLSResults, IV2SLSResults)):
            return True
        
        # Fallback: check for required attributes
        return (
            hasattr(model, "params")
            and hasattr(model, "pvalues")
            and (hasattr(model, "std_errors") or hasattr(model, "std_error"))
        )

    def coef_table(self, model: Any) -> pd.DataFrame:
        """Extract coefficient table from a linearmodels fitted model."""
        params = pd.Series(model.params)
        
        # Handle both std_errors (panel) and std_error (IV/AbsorbingLS)
        se_attr = "std_errors" if hasattr(model, "std_errors") else "std_error"
        se = pd.Series(getattr(model, se_attr, np.nan), index=params.index)
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
        """Extract dependent variable name from a linearmodels fitted model."""
        # Try common locations
        for chain in [
            ("model", "formula"),  # 'y ~ x1 + x2'
            ("model", "dependent", "name"),
            ("model", "dependent", "var_name"),
            ("model", "dependent", "pandas", "name"),
            ("model", "dependent", "vars", 0),  # AbsorbingLS stores vars as list
        ]:
            val = _follow(model, list(chain))
            if isinstance(val, str):
                if chain[-1] == "formula" and "~" in val:
                    return val.split("~", 1)[0].strip()
                return val
        
        # For AbsorbingLS, try to get column name from dependent DataFrame
        mdl = getattr(model, "model", None)
        if mdl is not None:
            dep = getattr(mdl, "dependent", None)
            if dep is not None:
                if hasattr(dep, "cols"):
                    # dep.cols contains the column names
                    cols = dep.cols
                    if isinstance(cols, list) and len(cols) > 0:
                        return cols[0]
                elif hasattr(dep, "dataframe") and hasattr(dep.dataframe, "columns"):
                    return dep.dataframe.columns[0]
        
        return "y"

    def fixef_string(self, model: Any) -> str | None:
        """
        Extract fixed effects string from a linearmodels fitted model.
        
        For PanelOLS: Returns actual index names (e.g., "nr+year")
        For AbsorbingLS: Returns absorbed variable names (e.g., "firm_id+year")
        """
        mdl = getattr(model, "model", None)
        if mdl is None:
            return None
        
        # Check if this is an AbsorbingLS model
        model_type = type(mdl).__name__
        if model_type == "AbsorbingLS":
            # For AbsorbingLS, the absorb parameter is stored as _absorb
            absorb_data = getattr(mdl, "_absorb", None)
            if absorb_data is not None:
                # absorb_data is the DataFrame that was passed as absorb parameter
                if hasattr(absorb_data, "columns"):
                    return "+".join(absorb_data.columns.tolist())
                # Fallback: if it's a Categorical object with pandas attribute
                if hasattr(absorb_data, "pandas") and hasattr(absorb_data.pandas, "columns"):
                    return "+".join(absorb_data.pandas.columns.tolist())
            return None
        
        # For PanelOLS/RandomEffects models
        has_entity = getattr(mdl, "entity_effects", False)
        has_time = getattr(mdl, "time_effects", False)
        has_other = getattr(mdl, "other_effects", None)
        
        if not (has_entity or has_time or has_other):
            return None
        
        # Try to extract actual variable names from panel structure
        entity_name = "entity"
        time_name = "time"

        dependent = getattr(mdl, "dependent", None)
        if dependent is not None and hasattr(dependent, "dataframe"):
            idx = dependent.dataframe.index
            if hasattr(idx, "names") and len(idx.names) >= 2:
                # Ensure we get strings, not integers or other types
                entity_name = str(idx.names[0]) if idx.names[0] is not None else "entity"
                time_name = str(idx.names[1]) if idx.names[1] is not None else "time"
        
        # Build fixed effects string
        parts = []
        if has_entity:
            parts.append(entity_name)
        if has_time:
            parts.append(time_name)
        if has_other:
            parts.append("other")
        
        return "+".join(parts) if parts else None

    # Unified stat keys -> linearmodels attributes/callables
    STAT_MAP: ClassVar[dict[str, Any]] = {
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
        # IV diagnostics: TODO
       
    }

    def stat(self, model: Any, key: str) -> Any:
        """Extract a specific statistic from a linearmodels fitted model."""
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
        """Extract variance-covariance information from a linearmodels fitted model."""
        return {"vcov_type": getattr(model, "cov_type", None), "clustervar": None}

    def var_labels(self, model: Any) -> dict[str, str] | None:
        """Extract variable labels from a linearmodels fitted model."""
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
        """Return set of statistics available for the given linearmodels model."""
        return {
            k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None
        }


class DuckRegExtractor:
    """
    Extractor for duckreg models (DuckRegression).

    Handles models from the duckreg package. Note that duckreg only provides
    point_estimate and standard_error attributes, so p-values and t-statistics
    need to be computed from these.
    """

    def can_handle(self, model: Any) -> bool:
        """Check if model is a DuckRegression model type."""
        # If DuckRegression type is empty tuple, duckreg is not available
        if DuckRegression == ():
            return False
        try:
            return isinstance(model, DuckRegression)
        except Exception:
            return False

    def coef_table(self, model: Any) -> pd.DataFrame:
        """
        Extract coefficient table from duckreg model.

        Since duckreg only provides point_estimate and standard_error,
        we compute t-statistics and p-values assuming normal distribution.

        Returns
        -------
            DataFrame with columns: Estimate, Std. Error, t value, and Pr(>|t|).
        """
        from scipy import stats

        # Get point estimates and standard errors
        point_estimate = getattr(model, "point_estimate", None)
        vcov = getattr(model, "vcov", None)
        standard_error = np.sqrt(np.diag(vcov))

        if point_estimate is None or standard_error is None:
            raise ValueError(
                "DuckRegExtractor: model must have 'point_estimate' and 'standard_error' attributes."
            )

        # Get variable names from the model
        covars = getattr(model, "covars", [])
        fevars = getattr(model, "fevars", [])
        var_names = covars + fevars if covars else None

        # Convert to pandas Series if needed, using proper variable names
        if not isinstance(point_estimate, pd.Series):
            if var_names is not None:
                # DuckRegression prepends intercept to coefficients, so add it to var_names
                var_names_with_intercept = ["_cons"] + list(var_names)
                point_estimate = pd.Series(point_estimate, index=var_names_with_intercept)
            else:
                point_estimate = pd.Series(point_estimate)

        # Ensure index names are strings
        if point_estimate.index.dtype != 'object':
            point_estimate.index = point_estimate.index.astype(str)

        if not isinstance(standard_error, pd.Series):
            standard_error = pd.Series(standard_error, index=point_estimate.index)

        # Compute t-statistics
        t_values = point_estimate / standard_error

        # Compute p-values (two-tailed test)
        p_values = 2 * (1 - stats.norm.cdf(np.abs(t_values)))

        df = pd.DataFrame(
            {
                "Estimate": pd.to_numeric(point_estimate, errors="coerce"),
                "Std. Error": pd.to_numeric(standard_error, errors="coerce"),
                "t value": pd.to_numeric(t_values, errors="coerce"),
                "Pr(>|t|)": pd.to_numeric(p_values, errors="coerce"),
            },
            index=point_estimate.index,
        )

        return df[["Estimate", "Std. Error", "t value", "Pr(>|t|)"]]

    def depvar(self, model: Any) -> str:
        """Extract dependent variable name from duckreg model."""
        # DuckRegression stores outcome variable in outcome_var attribute
        outcome_var = getattr(model, "outcome_var", None)
        if isinstance(outcome_var, str):
            return outcome_var
        return "y"

    def fixef_string(self, model: Any) -> str | None:
        """
        Extract fixed effects specification from duckreg model.

        DuckRegression uses fevars (fixed effect variables) specified in the formula.
        """
        return None

    # Unified stat keys -> duckreg attributes/callables
    # Note: DuckRegression does not provide model statistics like N, r2, etc.
    STAT_MAP: ClassVar[dict[str, Any]] = {}

    def stat(self, model: Any, key: str) -> Any:
        """
        Extract a statistic from the duckreg model using STAT_MAP.

        Args:
            model: DuckRegression model object.
            key: Statistic key (e.g., "N", "r2").

        Returns
        -------
            The requested statistic value or None if not available.
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
        """
        Extract variance-covariance matrix information from duckreg model.

        DuckRegression uses cluster_col for clustering and n_bootstraps for bootstrap SE.
        """
        cluster_col = getattr(model, "cluster_col", None)
        n_bootstraps = getattr(model, "n_bootstraps", None)

        # Determine vcov_type based on available information
        vcov_type = None
        if n_bootstraps and n_bootstraps > 0:
            vcov_type = "iid bootstrap"
        if cluster_col:
            vcov_type = "cluster bootstrap" if vcov_type is None else f"{vcov_type}+clustered"

        return {
            "vcov_type": vcov_type,
            "clustervar": cluster_col,
        }

    def var_labels(self, model: Any) -> dict[str, str] | None:
        """Extract variable labels from the duckreg model's data if available."""
        # Try to get the original data DataFrame
        df = getattr(model, "data", None)
        if df is None:
            df = getattr(model, "_data", None)

        if isinstance(df, pd.DataFrame):
            try:
                return get_var_labels(df, include_defaults=True)
            except Exception:
                return None
        return None

    def supported_stats(self, model: Any) -> set[str]:
        """Return set of statistics available for the given duckreg model."""
        return {
            k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None
        }


# Register built-ins
clear_extractors()
register_extractor(PyFixestExtractor())
register_extractor(LinearmodelsExtractor())
register_extractor(DuckRegExtractor())
register_extractor(StatsmodelsExtractor())
