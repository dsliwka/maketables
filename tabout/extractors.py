from typing import Any, Dict, List, Protocol, runtime_checkable
import numpy as np
import pandas as pd
from typing import Optional
from .importdta import get_var_labels

# Optional imports for built-ins
try:
    from pyfixest.estimation.feiv_ import Feiv
    from pyfixest.estimation.feols_ import Feols
    from pyfixest.estimation.fepois_ import Fepois
except Exception:
    Feols = Fepois = Feiv = tuple()  # type: ignore


@runtime_checkable
class ModelExtractor(Protocol):
    def can_handle(self, model: Any) -> bool: ...
    def coef_table(self, model: Any) -> pd.DataFrame: ...
    def depvar(self, model: Any) -> str: ...
    def fixef_string(self, model: Any) -> str | None: ...
    def stat(self, model: Any, key: str) -> Any: ...
    def vcov_info(self, model: Any) -> Dict[str, Any]: ...
    def var_labels(self, model: Any) -> Optional[Dict[str, str]]: ...
    def supported_stats(self, model: Any) -> set[str]: ...


_EXTRACTOR_REGISTRY: List[ModelExtractor] = []


def register_extractor(extractor: ModelExtractor) -> None:
    _EXTRACTOR_REGISTRY.append(extractor)


def clear_extractors() -> None:
    _EXTRACTOR_REGISTRY.clear()


def get_extractor(model: Any) -> ModelExtractor:
    for ex in _EXTRACTOR_REGISTRY:
        try:
            if ex.can_handle(model):
                return ex
        except Exception:
            continue
    raise TypeError(f"No extractor available for model type: {type(model).__name__}")


# ---------- small helpers ----------

def _follow(obj: Any, chain: List[str]) -> Any:
    cur = obj
    for a in chain:
        if hasattr(cur, a):
            cur = getattr(cur, a)
        else:
            return None
    return cur


def _get_attr(model: Any, spec: Any) -> Any:
    """
    Resolve a STAT_MAP spec against a model:
    - "attr" -> model.attr or model.model.attr
    - ("a","b","c") or ["a","b","c"] -> nested attributes
    - callable(model) -> computed value
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
    def can_handle(self, model: Any) -> bool:
        try:
            return isinstance(model, (Feols, Fepois, Feiv))
        except Exception:
            return False

    def coef_table(self, model: Any) -> pd.DataFrame:
        df = model.tidy()
        if "Estimate" not in df.columns or "Std. Error" not in df.columns:
            raise ValueError("PyFixestExtractor: tidy() must contain 'Estimate' and 'Std. Error'.")
        if "t value" not in df.columns and "z value" in df.columns:
            df = df.rename(columns={"z value": "t value"})
        if "Pr(>|t|)" not in df.columns:
            if "Pr(>|z|)" in df.columns:
                df = df.rename(columns={"Pr(>|z|)": "Pr(>|t|)"})
            else:
                raise ValueError("PyFixestExtractor: tidy() must contain 'Pr(>|t|)' (or 'Pr(>|z|)').")
        keep = ["Estimate", "Std. Error", "Pr(>|t|)"]
        if "t value" in df.columns:
            keep.insert(2, "t value")
        return df[keep]

    def depvar(self, model: Any) -> str:
        return getattr(model, "_depvar", "y")

    def fixef_string(self, model: Any) -> str | None:
        return getattr(model, "_fixef", None)

    # Build a clean map of unified stat keys -> pyfixest attributes/callables
    STAT_MAP: Dict[str, Any] = {
        "N": "_N",
        "se_type": lambda m: ("by: " + "+".join(getattr(m, "_clustervar", []))
                              if getattr(m, "_vcov_type", None) == "CRV" and getattr(m, "_clustervar", None)
                              else getattr(m, "_vcov_type", None)),
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
            if isinstance(getattr(m, "deviance", None), (list, tuple, np.ndarray, pd.Series))
            else getattr(m, "deviance", None)
        ),
    }

    def stat(self, model: Any, key: str) -> Any:
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

    def vcov_info(self, model: Any) -> Dict[str, Any]:
        return {
            "vcov_type": getattr(model, "_vcov_type", None),
            "clustervar": getattr(model, "_clustervar", None),
        }

    def var_labels(self, model: Any) -> Optional[Dict[str, str]]:
        df = getattr(model, "_data", None)
        if isinstance(df, pd.DataFrame):
            try:
                return get_var_labels(df, include_defaults=True)
            except Exception:
                return None
        return None

    def supported_stats(self, model: Any) -> set[str]:
        return {k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None}


class StatsmodelsExtractor:
    def can_handle(self, model: Any) -> bool:
        return all(hasattr(model, a) for a in ("params", "bse", "pvalues"))

    def coef_table(self, model: Any) -> pd.DataFrame:
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
            df["t value"] = pd.to_numeric(pd.Series(tvalues, index=params.index), errors="coerce")
            df = df[["Estimate", "Std. Error", "t value", "Pr(>|t|)"]]
        return df

    def depvar(self, model: Any) -> str:
        for chain in [("model", "endog_names"), ("endog_names",), ("model", "endog", "name")]:
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
        return None

    # Unified stat keys -> statsmodels attributes/callables
    STAT_MAP: Dict[str, Any] = {
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

    def vcov_info(self, model: Any) -> Dict[str, Any]:
        return {"vcov_type": getattr(model, "cov_type", None), "clustervar": None}

    def var_labels(self, model: Any) -> Optional[Dict[str, str]]:
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
        return {k for k, spec in self.STAT_MAP.items() if _get_attr(model, spec) is not None}


# Register built-ins
clear_extractors()
register_extractor(PyFixestExtractor())
register_extractor(StatsmodelsExtractor())