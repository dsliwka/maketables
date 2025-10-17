"""
PyStata Integration for MakeTables.

This module provides integration with PyStata (Stata's Python API) for users
who want to run Stata commands through Python and extract results into MakeTables.

PyStata allows running Stata from Python and accessing Stata's results.
This extractor enables seamless integration with MakeTables' table generation system.

Example Usage:
    import pystata
    import maketables as mt
    from maketables.pystata_extractor import StataResultWrapper
    
    # Configure and start Stata
    pystata.config.init('stata-mp')  # or 'stata-se', 'stata-be'
    
    # Load data and run regression in Stata
    pystata.stata.run('''
        sysuse auto, clear
        regress mpg weight length foreign
        ''')
    
    # Wrap the Stata result for MakeTables
    result = StataResultWrapper.from_current()
    
    # Create table using MakeTables
    table = mt.ETable([result], caption="Stata Regression Results")
"""

from typing import Any

import numpy as np
import pandas as pd

from .extractors import register_extractor

# Optional import for PyStata
try:
    import pystata
    PYSTATA_AVAILABLE = True
except ImportError:
    PYSTATA_AVAILABLE = False


class StataResultWrapper:
    """
    Wrapper class for Stata regression results accessed through PyStata.
    
    This class wraps Stata estimation results and provides a standardized interface
    that works with MakeTables' extractor system. It stores coefficient information,
    statistics, and metadata extracted from Stata's e() results.
    """

    def __init__(self,
                 coefficients: pd.DataFrame,
                 stats: dict[str, Any],
                 depvar: str,
                 cmd: str = "",
                 fixed_effects: str | None = None):
        """
        Initialize Stata result wrapper.
        
        Parameters
        ----------
        coefficients : pd.DataFrame
            Coefficient table with columns: Estimate, Std. Error, t value, Pr(>|t|)
        stats : dict
            Dictionary of model statistics (N, r2, adj_r2, etc.)
        depvar : str
            Name of dependent variable
        cmd : str, optional
            Stata command used for estimation
        fixed_effects : str, optional
            Fixed effects specification if applicable
        """
        self.coefficients = coefficients
        self.stats = stats
        self.depvar_name = depvar
        self.cmd = cmd
        self.fixed_effects = fixed_effects
        self._var_labels = {}

    @classmethod
    def from_current(cls, formulaic_names: bool = True, use_var_labels: bool = True) -> 'StataResultWrapper':
        """
        Create wrapper from current Stata estimation results.
        
        Extracts results from Stata's e() system after running an estimation command.
        
        Parameters
        ----------
        formulaic_names : bool, default True
            Whether to convert Stata coefficient names to formulaic/patsy style.
            If True: '2.price_cat' -> 'C(price_cat)[T.2]'
            If False: keep original Stata names like '2.price_cat'
        use_var_labels : bool, default True
            Whether to replace categorical variable numbers with their value labels.
            If True: '2.price_cat' with label "High" -> 'C(price_cat)[T.High]' or '2.price_cat (High)'
            If False: keep numeric codes like '2.price_cat'
            
        Returns
        -------
        StataResultWrapper
            Wrapper containing the current Stata estimation results
            
        Raises
        ------
        RuntimeError
            If PyStata is not available or no estimation results found
        """
        if not PYSTATA_AVAILABLE:
            raise RuntimeError("PyStata is not available. Install with: pip install pystata")

        try:
            # Extract coefficient information
            coefficients = cls._extract_coefficients(formulaic_names=formulaic_names, use_var_labels=use_var_labels)

            # Extract model statistics
            stats = cls._extract_statistics()

            # Get dependent variable name
            depvar = cls._extract_depvar()

            # Get command used
            cmd = cls._extract_command()

            # Extract fixed effects info if available
            fixed_effects = cls._extract_fixed_effects()

            # Create wrapper instance
            wrapper = cls(coefficients, stats, depvar, cmd, fixed_effects)

            # Always extract variable labels (fast operation, graceful fallback)
            wrapper._var_labels = cls._extract_var_labels()
            
            # Extract value labels for categorical variables if requested
            wrapper._value_labels = cls._extract_value_labels() if use_var_labels else {}

            return wrapper

        except Exception as e:
            raise RuntimeError(f"Failed to extract Stata results: {e}")

    @staticmethod
    def _convert_stata_to_formulaic(stata_name: str, value_labels: dict[str, dict[int, str]] = None) -> str:
        """
        Convert Stata coefficient naming to formulaic/patsy-style expressions.
        
        Converts Stata's factor variable and interaction syntax to Python-style:
        - '2.price_cat' -> 'C(price_cat)[T.2]' or 'C(price_cat)[T.High]' (with labels)
        - '1.foreign' -> 'C(foreign)[T.1]' or 'C(foreign)[T.Domestic]' (with labels)
        - '1.foreign#c.weight' -> 'C(foreign)[T.1]:weight' or 'C(foreign)[T.Domestic]:weight' (with labels)
        - 'weight' -> 'weight' (unchanged for continuous vars)
        - '_cons' -> 'Intercept' (standard rename)
        
        Parameters
        ----------
        stata_name : str
            Stata coefficient name (e.g., '2.price_cat', '1.foreign#c.weight')
        value_labels : dict[str, dict[int, str]], optional
            Dictionary mapping variable names to their value label mappings.
            Each inner dict maps numeric codes to text labels.
            
        Returns
        -------
        str
            Formulaic/patsy-style expression
        """
        import re
        
        # Handle intercept first
        if stata_name == '_cons':
            return 'Intercept'
            
        # Initialize value_labels if None
        if value_labels is None:
            value_labels = {}
        
        def get_label_or_level(var: str, level: str) -> str:
            """Get value label for variable/level or return level if no label exists."""
            try:
                level_int = int(level)
                if var in value_labels and level_int in value_labels[var]:
                    return value_labels[var][level_int]
                return level
            except (ValueError, KeyError):
                return level
            
        # Handle interaction terms: split on '#'
        if '#' in stata_name:
            parts = stata_name.split('#')
            converted_parts = []
            
            for part in parts:
                # Remove 'c.' prefix for continuous variables in interactions
                if part.startswith('c.'):
                    converted_parts.append(part[2:])  # Remove 'c.' prefix
                # Convert factor variable parts
                elif re.match(r'\d+\.', part):
                    level, var = part.split('.', 1)
                    label = get_label_or_level(var, level)
                    converted_parts.append(f'C({var})[T.{label}]')
                else:
                    # Regular variable name
                    converted_parts.append(part)
            
            return ':'.join(converted_parts)
        
        # Handle single factor variables: '2.price_cat' -> 'C(price_cat)[T.2]' or 'C(price_cat)[T.High]'
        if re.match(r'\d+\.', stata_name):
            level, var = stata_name.split('.', 1)
            label = get_label_or_level(var, level)
            return f'C({var})[T.{label}]'
        
        # Handle continuous variables prefixed with 'c.'
        if stata_name.startswith('c.'):
            return stata_name[2:]  # Remove 'c.' prefix
            
        # Regular variable names (unchanged)
        return stata_name

    @staticmethod
    def _extract_coefficients(formulaic_names: bool = True, use_var_labels: bool = True) -> pd.DataFrame:
        """Extract coefficient table from Stata's e(b) and e(V) matrices using sfi API."""
        try:
            from sfi import Matrix
            
            # Extract coefficient values using sfi.Matrix (more robust)
            b_matrix = Matrix.get("e(b)")
            if b_matrix is None or len(b_matrix) == 0:
                raise ValueError("No coefficient matrix found")
            
            # Flatten coefficient matrix to get coefficient values
            coef_vals = np.array(b_matrix[0]) if len(b_matrix) == 1 else np.array(b_matrix).flatten()

            # Try to extract complete coefficient table directly from Stata's r(table)
            # This contains coefficients, standard errors, t-stats, p-values, etc.
            try:
                r_table = Matrix.get("r(table)")
                if r_table is not None and len(r_table) >= 4:
                    table_array = np.array(r_table)
                    # r(table) structure: [coeffs, std_errors, t_stats, p_values, ...]
                    std_errors = table_array[1, :]   # Row 1: standard errors
                    t_stats = table_array[2, :]      # Row 2: t-statistics (from Stata)
                    p_values = table_array[3, :]     # Row 3: p-values (from Stata)
                else:
                    raise ValueError("r(table) not available, falling back to manual calculation")
            except Exception:
                # Fallback: calculate from variance-covariance matrix
                vcov_matrix = Matrix.get("e(V)")
                if vcov_matrix is not None and len(vcov_matrix) > 0:
                    vcov_array = np.array(vcov_matrix)
                    std_errors = np.sqrt(np.diag(vcov_array))
                    # Calculate t-statistics manually
                    t_stats = coef_vals / std_errors
                    # Use normal approximation for p-values (Stata default for large samples)
                    from scipy.stats import norm
                    p_values = 2 * (1 - norm.cdf(np.abs(t_stats)))
                else:
                    std_errors = t_stats = p_values = None

            # Create DataFrame
            data = {"Estimate": coef_vals}

            if std_errors is not None:
                data["Std. Error"] = std_errors

            if t_stats is not None:
                data["t value"] = t_stats

            if p_values is not None:
                data["Pr(>|t|)"] = p_values

            # Extract coefficient names using sfi.Matrix to get colnames from e(b)
            # This works for all estimation commands (regress, xtreg, logit, etc.)
            try:
                from sfi import Matrix
                # Get coefficient matrix colnames - this is the robust Stata way
                coef_names = Matrix.getColNames("e(b)")
                if coef_names and len(coef_names) == len(coef_vals):
                    # Filter out base categories (reference levels) that end with 'b.'
                    # These are Stata's base categories that are always zero and not displayed
                    filtered_indices = []
                    filtered_coef_vals = []
                    filtered_std_errors = []
                    filtered_t_stats = []
                    filtered_p_values = []
                    
                    for i, name in enumerate(coef_names):
                        # Skip base categories: coefficients that match Stata's base category pattern
                        # Base categories have pattern: digit + 'b' + '.' (e.g., '1b.price_cat', '0b.foreign')
                        import re
                        if re.search(r'\d+b\.', name):
                            # Filtered out: base category (reference level)
                            continue
                        
                        # Convert coefficient names based on user preference
                        if formulaic_names:
                            # Extract value labels if requested
                            value_labels = StataResultWrapper._extract_value_labels() if use_var_labels else {}
                            display_name = StataResultWrapper._convert_stata_to_formulaic(name, value_labels)
                        else:
                            # Keep original Stata names, just rename _cons to Intercept
                            display_name = "Intercept" if name == "_cons" else name
                        filtered_indices.append(display_name)
                        filtered_coef_vals.append(coef_vals[i])
                        
                        if std_errors is not None:
                            filtered_std_errors.append(std_errors[i])
                        if t_stats is not None:
                            filtered_t_stats.append(t_stats[i])
                        if p_values is not None:
                            filtered_p_values.append(p_values[i])
                    
                    # Update arrays with filtered data
                    coef_vals = np.array(filtered_coef_vals)
                    if std_errors is not None:
                        std_errors = np.array(filtered_std_errors)
                    if t_stats is not None:
                        t_stats = np.array(filtered_t_stats)
                    if p_values is not None:
                        p_values = np.array(filtered_p_values)
                    index = filtered_indices
                else:
                    # Fallback to generic names if colnames extraction fails
                    index = [f"coef{i+1}" for i in range(len(coef_vals))]
            except Exception:
                # Final fallback if sfi.Matrix is not available
                index = [f"coef{i+1}" for i in range(len(coef_vals))]

            # Rebuild data dictionary with filtered arrays
            data = {"Estimate": coef_vals}
            
            if std_errors is not None and len(std_errors) > 0:
                data["Std. Error"] = std_errors

            if t_stats is not None and len(t_stats) > 0:
                data["t value"] = t_stats

            if p_values is not None and len(p_values) > 0:
                data["Pr(>|t|)"] = p_values

            df = pd.DataFrame(data, index=index)
            df.index.name = "Coefficient"

            return df

        except Exception:
            # Fallback: create minimal table with available info
            return pd.DataFrame({
                "Estimate": [np.nan],
                "Std. Error": [np.nan],
                "t value": [np.nan],
                "Pr(>|t|)": [np.nan]
            }, index=["coef"])

    @staticmethod
    def _extract_statistics() -> dict[str, Any]:
        """Extract model statistics from Stata's e() scalars using sfi API."""
        stats = {}

        try:
            from sfi import Scalar
            
            # Map common statistics - use sfi.Scalar for robust access
            stat_mapping = {
                'N': 'e(N)',
                'r2': 'e(r2)',
                'r2_a': 'e(r2_a)',  # Adjusted R-squared
                'rmse': 'e(rmse)',
                'mss': 'e(mss)',    # Model sum of squares
                'rss': 'e(rss)',    # Residual sum of squares
                'F': 'e(F)',        # F-statistic
                'df_m': 'e(df_m)',  # Model degrees of freedom
                'df_r': 'e(df_r)',  # Residual degrees of freedom
                'll': 'e(ll)',      # Log-likelihood
                'aic': 'e(aic)',
                'bic': 'e(bic)',
                'chi2': 'e(chi2)',   # Chi-squared statistic
                # Panel data specific statistics
                'r2_w': 'e(r2_w)',   # Within R-squared (fixed effects)
                'r2_b': 'e(r2_b)',   # Between R-squared
                'r2_o': 'e(r2_o)',   # Overall R-squared
                'N_g': 'e(N_g)',     # Number of groups
                'g_min': 'e(g_min)', # Min observations per group
                'g_max': 'e(g_max)', # Max observations per group
                'g_avg': 'e(g_avg)'  # Average observations per group
            }

            # Extract available statistics using sfi.Scalar
            for key, stata_key in stat_mapping.items():
                try:
                    value = Scalar.getValue(stata_key)
                    if value is not None and not (isinstance(value, float) and np.isnan(value)):
                        stats[key] = value
                except Exception:
                    # If specific scalar doesn't exist, continue to next
                    continue
            
            # Additional panel data statistics that might have alternative names
            panel_alternatives = {
                'r2_within': ['e(r2_w)', 'e(r2within)'],
                'r2_between': ['e(r2_b)', 'e(r2between)'],
                'r2_overall': ['e(r2_o)', 'e(r2overall)'],
            }
            
            for key, alternatives in panel_alternatives.items():
                if key not in stats:  # Only if not already extracted
                    for alt_key in alternatives:
                        try:
                            value = Scalar.getValue(alt_key)
                            if value is not None and not (isinstance(value, float) and np.isnan(value)):
                                stats[key] = value
                                break
                        except Exception:
                            continue

        except Exception:
            pass

        return stats

    @staticmethod
    def _extract_depvar() -> str:
        """Extract dependent variable name from Stata using sfi API."""
        try:
            from sfi import Macro
            # Use sfi.Macro for robust access to e(depvar)
            depvar = Macro.getGlobal("e(depvar)")
            return depvar if depvar else "y"
        except Exception:
            return "y"

    @staticmethod
    def _extract_command() -> str:
        """Extract the Stata command used for estimation using sfi API."""
        try:
            from sfi import Macro
            # Use sfi.Macro for robust access to e(cmd)
            return Macro.getGlobal("e(cmd)")
        except Exception:
            return ""

    @staticmethod
    def _extract_fixed_effects() -> str | None:
        """Extract fixed effects information if available using sfi API."""
        try:
            from sfi import Macro
            
            # Check common fixed effects indicators using sfi.Macro
            absorb = Macro.getGlobal("e(absorb)")
            if absorb:
                return absorb

            # Check for other FE indicators (reghdfe, etc.)
            fe_vars = Macro.getGlobal("e(fe)")
            if fe_vars:
                return fe_vars
            
            # For xtreg and other panel commands, extract the panel ID variable
            cmd = Macro.getGlobal("e(cmd)")
            if cmd and "xtreg" in cmd.lower():
                # For xtreg, if we have panel data statistics, it's likely a fixed effects model
                # Check for presence of within R-squared as indicator of FE model
                try:
                    from sfi import Scalar
                    r2_w = Scalar.getValue("e(r2_w)")
                    if r2_w is not None:
                        # This is a fixed effects model, get the panel variable
                        panel_var = Macro.getGlobal("e(ivar)")
                        if panel_var:
                            return f"{panel_var}"
                except Exception:
                    pass
                
                # Alternative: always extract panel var for xtreg since it implies panel structure
                panel_var = Macro.getGlobal("e(ivar)")
                if panel_var:
                    return f"{panel_var}"
                    
                # Fallback: try to get from e(panelvar) or other xtreg-specific globals
                alt_panel = Macro.getGlobal("e(panelvar)")
                if alt_panel:
                    return f"{alt_panel}"
            
            # Check for other panel/longitudinal commands
            if cmd:
                if any(x in cmd.lower() for x in ["xtlogit", "xtprobit", "xtpoisson"]):
                    panel_var = Macro.getGlobal("e(ivar)")
                    if panel_var:
                        return f"{panel_var}"

            return None
        except Exception:
            return None

    @staticmethod
    def _extract_var_labels() -> dict[str, str]:
        """
        Extract variable labels using sfi.Data API.
        
        Uses the Stata Function Interface (sfi.Data) to directly access
        Stata's internal data structures for variable labels.
        
        Returns
        -------
        dict[str, str]
            Dictionary mapping variable names to their labels.
            Returns empty dict if no labels available or if extraction fails.
        """
        try:
            from sfi import Data
            nvars = Data.getVarCount()
            labels = {}
            for i in range(nvars):
                name = Data.getVarName(i)
                label = Data.getVarLabel(i)
                if label:  # Only store non-empty labels
                    labels[name] = label
            return labels
        except Exception:
            return {}

    @staticmethod
    def _extract_value_labels() -> dict[str, dict[int, str]]:
        """
        Extract value labels for categorical variables using sfi.Data API.
        
        Uses the Stata Function Interface (sfi.Data) to extract value labels
        which map numeric codes to text descriptions for categorical variables.
        
        Returns
        -------
        dict[str, dict[int, str]]
            Nested dictionary mapping variable names to their value label mappings.
            Each inner dict maps numeric codes to text labels.
            Returns empty dict if no value labels available or if extraction fails.
        """
        try:
            from sfi import Data
            nvars = Data.getVarCount()
            nobs = Data.getObsTotal()
            value_labels = {}
            
            for i in range(nvars):
                name = Data.getVarName(i)
                
                # Skip string variables - they don't have value labels
                if Data.isVarTypeString(name):
                    continue
                    
                # Build mapping of numeric to labeled values using getFormattedValue
                var_labels = {}
                seen_values = set()
                
                for obs in range(nobs):
                    try:
                        numeric_val = Data.getAt(name, obs)
                        
                        # Skip missing values and already processed values
                        if str(numeric_val) == 'nan' or numeric_val in seen_values:
                            continue
                            
                        # Get formatted value with labels
                        formatted_val = Data.getFormattedValue(name, obs, True)  # True = use value labels
                        
                        # If formatted differs from numeric, we have a value label
                        if (str(formatted_val) != str(numeric_val) and
                            str(formatted_val) != str(int(numeric_val))):
                            # Strip whitespace to ensure clean labels
                            clean_label = str(formatted_val).strip()
                            var_labels[int(numeric_val)] = clean_label
                            
                        seen_values.add(numeric_val)
                        
                    except Exception:
                        continue
                
                if var_labels:
                    value_labels[name] = var_labels
                    
            return value_labels
        except Exception:
            return {}


class PyStataExtractor:
    """
    Extractor for StataResultWrapper objects.
    
    This extractor handles StataResultWrapper objects created from PyStata
    estimation results, providing a bridge between Stata and MakeTables.
    """

    def can_handle(self, model: Any) -> bool:
        """Check if model is a StataResultWrapper."""
        return isinstance(model, StataResultWrapper)

    def coef_table(self, model: StataResultWrapper) -> pd.DataFrame:
        """Extract coefficient table from Stata result wrapper."""
        return model.coefficients.copy()

    def depvar(self, model: StataResultWrapper) -> str:
        """Extract dependent variable name."""
        return model.depvar_name

    def fixef_string(self, model: StataResultWrapper) -> str | None:
        """Extract fixed effects specification."""
        return model.fixed_effects

    def stat(self, model: StataResultWrapper, key: str) -> Any:
        """Extract specific statistic from Stata results."""
        # Map common statistic keys to Stata equivalents
        key_mapping = {
            'nobs': 'N',
            'r_squared': 'r2',
            'adj_r_squared': 'r2_a',
            'f_pvalue': None,  # Would need to calculate from F and df
            'pseudo_r2': 'r2'  # For models where this applies
        }

        stata_key = key_mapping.get(key, key)
        if stata_key is None:
            return None

        return model.stats.get(stata_key)

    def vcov_info(self, model: StataResultWrapper) -> dict[str, Any]:
        """Extract variance-covariance information."""
        # Basic implementation - could be enhanced based on Stata command used
        vcov_type = "standard"

        # Try to detect clustered/robust standard errors from command
        if hasattr(model, 'cmd') and model.cmd:
            if 'cluster' in model.cmd.lower():
                vcov_type = "clustered"
            elif any(word in model.cmd.lower() for word in ['robust', 'vce(robust)']):
                vcov_type = "robust"

        return {
            'vcov_type': vcov_type,
            'clustervar': None  # Could extract from e(clustvar) if available
        }

    def var_labels(self, model: StataResultWrapper) -> dict[str, str] | None:
        """Extract variable labels from Stata result."""
        return model._var_labels if model._var_labels else None

    def supported_stats(self, model: StataResultWrapper) -> set[str]:
        """Return set of statistics available for the Stata model."""
        available_stats = set(model.stats.keys())

        # Add mapped statistics
        mapped_stats = set()
        if 'N' in available_stats:
            mapped_stats.add('nobs')
        if 'r2' in available_stats:
            mapped_stats.update(['r_squared', 'pseudo_r2'])
        if 'r2_a' in available_stats:
            mapped_stats.add('adj_r_squared')

        return available_stats | mapped_stats


# Convenience functions for users
def rstata(stata_code: str,
           auto_extract: bool = True,
           quietly: bool = False,
           formulaic_names: bool = True,
           use_var_labels: bool = True) -> StataResultWrapper | None:
    """
    Run Stata regression code and optionally extract results.
    
    Parameters
    ----------
    stata_code : str
        Stata code to execute (should include estimation command)
    auto_extract : bool, default True
        Whether to automatically extract results into wrapper
    quietly : bool, default False
        Whether to suppress Stata's printed output during execution
    formulaic_names : bool, default True
        Whether to convert Stata coefficient names to formulaic/patsy style.
        If True: '2.price_cat' -> 'C(price_cat)[T.2]'
        If False: keep original Stata names like '2.price_cat'
    use_var_labels : bool, default True
        Whether to replace categorical variable numbers with their value labels.
        If True: '2.price_cat' with label "High" -> 'C(price_cat)[T.High]' or '2.price_cat (High)'
        If False: keep numeric codes like '2.price_cat'
        
    Returns
    -------
    StataResultWrapper or None
        Wrapped results if auto_extract=True and estimation was successful
        Variable labels are always extracted when available.
        
    Example
    -------
    >>> result = mt.rstata('''
    ...     sysuse auto, clear
    ...     regress mpg weight length foreign
    ... ''', quietly=True)
    >>> table = mt.ETable([result], caption="Stata Results")
    """
    if not PYSTATA_AVAILABLE:
        raise RuntimeError("PyStata is not available. Install with: pip install pystata")

    try:
        # Run the Stata code
        pystata.stata.run(stata_code, quietly=quietly)

        if auto_extract:
            return StataResultWrapper.from_current(formulaic_names=formulaic_names, use_var_labels=use_var_labels)
        else:
            return None

    except Exception as e:
        raise RuntimeError(f"Failed to run Stata regression: {e}")


def extract_current_stata_results(formulaic_names: bool = True, use_var_labels: bool = True) -> StataResultWrapper:
    """
    Extract current Stata estimation results.
    
    Convenience function to extract the most recent estimation results
    from Stata into a MakeTables-compatible wrapper.
    
    Parameters
    ----------
    formulaic_names : bool, default True
        Whether to convert Stata coefficient names to formulaic/patsy style.
    use_var_labels : bool, default True
        Whether to replace categorical variable numbers with their value labels.
    
    Returns
    -------
    StataResultWrapper
        Wrapped Stata estimation results
    """
    return StataResultWrapper.from_current(formulaic_names=formulaic_names, use_var_labels=use_var_labels)


# Register the PyStata extractor if PyStata is available
if PYSTATA_AVAILABLE:
    register_extractor(PyStataExtractor())
