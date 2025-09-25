import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any
from great_tables import GT
from .tabout import TabOut

# Try to import pyfixest result classes for type-based dispatch
try:
    from pyfixest.estimation.feols_ import Feols
    from pyfixest.estimation.fepois_ import Fepois
    from pyfixest.estimation.feiv_ import Feiv
    from pyfixest.estimation.FixestMulti_ import FixestMulti
    PYFIXEST_TYPES = tuple(t for t in (Feols, Fepois, Feiv) if t is not None)
    PYFIXEST_MULTI = FixestMulti
except Exception:
    PYFIXEST_TYPES = tuple()
    PYFIXEST_MULTI = tuple()

class RTable(TabOut):
    """
    RTable extends TabOut to generate regression tables.

    Parameters
    ----------
    models : list
        List of fitted model result objects (e.g., statsmodels, pyfixest).
    model_names : list[str], optional
        Names for model columns. Defaults to 'Model 1', 'Model 2', ...
    digits : int, optional
        Rounding digits for estimates and stats. Default 3.
    show_se : bool, optional
        Include standard errors in coefficient cell string. Default True.
    show_t : bool, optional
        Include t values in coefficient cell string. Default False.
    show_p : bool, optional
        Include p values in coefficient cell string. Default True.
    order : list[str], optional
        Optional ordering of coefficient names in the 'coefs' section.
    labels : dict[str, str], optional
        Optional mapping from coefficient names to display labels.
    stats_order : list[str], optional
        Optional ordering for 'stats' rows. Default ['N','R2','Adj. R2','AIC','BIC'].
    notes : str, optional
        Notes displayed under the table.
    caption : str, optional
        Table caption.
    tab_label : str, optional
        LaTeX/Docx table label.

    Other keyword arguments are forwarded to TabOut.
    """
    def __init__(
        self,
        models: List[Any],
        model_names: Optional[List[str]] = None,
        *,
        digits: int = 3,
        show_se: bool = True,
        show_t: bool = False,
        show_p: bool = True,
        order: Optional[List[str]] = None,
        labels: Optional[Dict[str, str]] = None,
        stats_order: Optional[List[str]] = None,
        notes: str = "",
        caption: Optional[str] = None,
        tab_label: Optional[str] = None,
        **kwargs,
    ):
        # Normalize list (expand FixestMulti if present)
        models = self._normalize_models(models)
        assert isinstance(models, list) and len(models) > 0, "models must be a non-empty list."

        self.models = models
        self.model_names = model_names or [f"Model {i+1}" for i in range(len(models))]
        self.digits = digits
        self.show_se = show_se
        self.show_t = show_t
        self.show_p = show_p
        self.order = order
        self.labels = labels or {}
        self.stats_order = stats_order or ["N", "R2", "Adj. R2", "AIC", "BIC"]

        # Extract pieces (dispatch to package-specific extractors)
        coeffs_per_model = [self._extract_coeffs(m) for m in models]
        stats_per_model = [self._extract_stats(m) for m in models]

        # Build final DataFrame with MultiIndex rows
        df = self._build_multiindex_dataframe(
            coeffs_per_model, stats_per_model, self.model_names
        )

        super().__init__(
            df,
            notes=notes,
            caption=caption,
            tab_label=tab_label,
            **kwargs,
        )


    # ---------- Package-specific extractors ---------------------------------

    def _extract_coeffs_pyfixest(self, model: Any) -> pd.DataFrame:
        """
        Extract coefficients from pyfixest results.
        Prefers model.coeftable (DataFrame or callable). Falls back to generic.
        """
        # coeftable can be a DataFrame or a callable returning one
        ct = getattr(model, "coeftable", None)
        if callable(ct):
            try:
                ct = ct()
            except Exception:
                ct = None

        if isinstance(ct, pd.DataFrame) and len(ct) > 0:
            cols_lower = {c.lower(): c for c in ct.columns}
            def pick(*cands):
                for c in cands:
                    if c in cols_lower:
                        return cols_lower[c]
                return None

            est_col = pick("estimate", "coef", "coefficient", "beta", "est")
            se_col = pick("std. error", "std_error", "se", "std err", "stderr")
            # pyfixest may use t or z depending on estimator; include both
            t_col = pick("t value", "t", "t_stat", "tvalue", "z value", "z", "z_stat", "zvalue")
            p_col = pick("pr(>|t|)", "pr(>|z|)", "p>|t|", "p>|z|", "pvalue", "p", "p>t", "p>z")

            idx = ct.index
            out = pd.DataFrame(index=idx)
            if est_col: out["beta"] = pd.to_numeric(ct[est_col], errors="coerce")
            if se_col: out["se"] = pd.to_numeric(ct[se_col], errors="coerce")
            if t_col: out["t"] = pd.to_numeric(ct[t_col], errors="coerce")
            if p_col: out["p"] = pd.to_numeric(ct[p_col], errors="coerce")
            return out

        # Fallback to generic strategy
        return self._extract_coeffs_generic(model)

    def _extract_stats_pyfixest(self, model: Any) -> Dict[str, Any]:
        """
        Extract model-level stats from pyfixest results (best-effort).
        """
        stats: Dict[str, Any] = {}

        # N
        n = getattr(model, "nobs", None)
        if n is None:
            n = getattr(model, "N", None)
        if n is not None:
            try:
                stats["N"] = int(n)
            except Exception:
                pass

        # R2 variants (pyfixest often has r2, r2_within, r2_between, r2_overall)
        for key, label in [
            ("r2", "R2"),
            ("r2_adj", "Adj. R2"),
            ("rsquared", "R2"),          # compatibility
            ("rsquared_adj", "Adj. R2"), # compatibility
            ("r2_within", "R2 (within)"),
            ("r2_between", "R2 (between)"),
            ("r2_overall", "R2 (overall)"),
        ]:
            val = getattr(model, key, None)
            if val is not None:
                try:
                    stats[label] = float(val)
                except Exception:
                    pass

        # Information criteria (if present)
        for key, label in [("aic", "AIC"), ("bic", "BIC")]:
            val = getattr(model, key, None)
            if val is not None:
                try:
                    stats[label] = float(val)
                except Exception:
                    pass

        return stats

    # ---------- Public extraction (dispatch) ---------------------------------

    def _extract_coeffs(self, model: Any) -> pd.DataFrame:
        if self._is_pyfixest(model):
            return self._extract_coeffs_pyfixest(model)
        return self._extract_coeffs_generic(model)

    def _extract_stats(self, model: Any) -> Dict[str, Any]:
        if self._is_pyfixest(model):
            return self._extract_stats_pyfixest(model)
        return self._extract_stats_generic(model)

    # ---- Assembly (unchanged) ----------------------------------------------

    def _build_multiindex_dataframe(
        self,
        coeffs_per_model: List[pd.DataFrame],
        stats_per_model: List[Dict[str, Any]],
        model_names: List[str],
    ) -> pd.DataFrame:
        """
        Build a MultiIndex row DataFrame:
        - First row level: 'coefs' and 'stats'
        - Second row level: coefficient names under 'coefs', statistic names under 'stats'
        Columns are model_names. Cells are formatted strings for coefficients and numbers for stats.
        """
        # Union of all coefficient names
        all_coefs = set()
        for coef_df in coeffs_per_model:
            all_coefs.update(list(coef_df.index))

        # Apply ordering if provided; otherwise sorted
        if self.order:
            ordered = [c for c in self.order if c in all_coefs]
            rest = [c for c in sorted(all_coefs) if c not in set(ordered)]
            coef_order = ordered + rest
        else:
            coef_order = sorted(all_coefs)

        # Build 'coefs' block: format each cell using configured display
        coef_rows = []
        for coef in coef_order:
            label = self.labels.get(coef, coef)
            row_vals = []
            for coef_df in coeffs_per_model:
                if coef in coef_df.index:
                    beta = coef_df.at[coef, "beta"] if "beta" in coef_df.columns else np.nan
                    se = coef_df.at[coef, "se"] if "se" in coef_df.columns else np.nan
                    t = coef_df.at[coef, "t"] if "t" in coef_df.columns else np.nan
                    p = coef_df.at[coef, "p"] if "p" in coef_df.columns else np.nan
                    cell = self._format_coef_cell(beta, se, t, p)
                else:
                    cell = ""
                row_vals.append(cell)
            coef_rows.append((("coefs", label), row_vals))

        # Build 'stats' block
        stat_keys = []
        for s in self.stats_order:
            # include only if at least one model provides it
            if any(s in d for d in stats_per_model):
                stat_keys.append(s)

        stats_rows = []
        for stat in stat_keys:
            row_vals = []
            for d in stats_per_model:
                val = d.get(stat, "")
                if isinstance(val, (int, np.integer)):
                    row_vals.append(f"{val:d}")
                elif isinstance(val, (float, np.floating)):
                    row_vals.append(self._fmt(val))
                else:
                    row_vals.append("" if val is None else str(val))
            stats_rows.append((("stats", stat), row_vals))

        # Assemble into DataFrame
        row_tuples = [idx for idx, _ in coef_rows] + [idx for idx, _ in stats_rows]
        index = pd.MultiIndex.from_tuples(row_tuples, names=["section", "name"])
        data = [vals for _, vals in coef_rows] + [vals for _, vals in stats_rows]
        df = pd.DataFrame(data, index=index, columns=model_names)
        return df

    # ---- Formatting (unchanged) --------------------------------------------

    def _fmt(self, x: float) -> str:
        return f"{x:.{self.digits}f}"

    def _format_coef_cell(
        self,
        beta: Optional[float],
        se: Optional[float],
        t: Optional[float],
        p: Optional[float],
    ) -> str:
        """
        Format a coefficient cell string like:
        0.123 (0.045) [t=2.72, p=0.006]
        With parts controlled by show_se/show_t/show_p.
        """
        if beta is None or (isinstance(beta, float) and np.isnan(beta)):
            return ""
        parts = [self._fmt(float(beta))]
        if self.show_se and se is not None and not (isinstance(se, float) and np.isnan(se)):
            parts.append(f"({self._fmt(float(se))})")
        trail = []
        if self.show_t and t is not None and not (isinstance(t, float) and np.isnan(t)):
            trail.append(f"t={self._fmt(float(t))}")
        if self.show_p and p is not None and not (isinstance(p, float) and np.isnan(p)):
            trail.append(f"p={self._fmt(float(p))}")
        if trail:
            parts.append("[" + ", ".join(trail) + "]")
        return " ".join(parts)
