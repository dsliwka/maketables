from typing import Any, Dict, List, Protocol, runtime_checkable

import numpy as np
import pandas as pd

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

        # Map z to t if needed (e.g., Poisson)
        if "t value" not in df.columns and "z value" in df.columns:
            df = df.rename(columns={"z value": "t value"})
        # Map p-value column if needed
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

    def stat(self, model: Any, key: str) -> Any:
        if key == "se_type":
            vcov_type = getattr(model, "_vcov_type", None)
            cl = getattr(model, "_clustervar", None)
            if vcov_type == "CRV" and cl:
                return "by: " + "+".join(cl)
            return vcov_type
        mapping = {
            "N": "_N",
            "r2": "_r2",
            "adj_r2": "_r2_adj",
            "r2_within": "_r2_within",
        }
        return getattr(model, mapping.get(key, ""), None)

    def vcov_info(self, model: Any) -> Dict[str, Any]:
        return {
            "vcov_type": getattr(model, "_vcov_type", None),
            "clustervar": getattr(model, "_clustervar", None),
        }


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

    def stat(self, model: Any, key: str) -> Any:
        if key == "se_type":
            return getattr(model, "cov_type", None)
        mapping = {"N": "nobs", 
                   "r2": "rsquared", 
                   "adj_r2": "rsquared_adj", 
                   "aic": "aic", 
                   "bic": "bic",
                   "f_pvalue": "f_pvalue",
                   "fvalue": "fvalue"}
        attr = mapping.get(key)
        value = getattr(model, attr, None) if attr else None
        # For N, convert to int if possible
        if key == "N" and value is not None:
            try:
                value = int(value)
            except Exception:
                pass
        return value

    def vcov_info(self, model: Any) -> Dict[str, Any]:
        return {"vcov_type": getattr(model, "cov_type", None), "clustervar": None}


# Register built-ins
register_extractor(PyFixestExtractor())
register_extractor(StatsmodelsExtractor())