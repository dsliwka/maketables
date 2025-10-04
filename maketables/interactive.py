"""
Interactive regression dashboard for PyFixest models.

This module provides an interactive Jupyter widget-based dashboard for exploring
regression specifications with PyFixest models and displaying results with MakeTables.
"""

import warnings

import numpy as np
import pandas as pd
from IPython.display import clear_output, display

try:
    import ipywidgets as widgets
except ImportError:
    raise ImportError("ipywidgets is required for interactive functionality. Install with: pip install ipywidgets")

try:
    import pyfixest as pf
except ImportError:
    raise ImportError("pyfixest is required. Install with: pip install pyfixest")

from . import DTable, ETable


def _parse_formula(formula: str) -> tuple[str, list[str], list[str]]:
    """
    Parse a PyFixest formula to extract dependent variable, independent variables, and fixed effects.

    Parameters
    ----------
    formula : str
        PyFixest formula string (e.g., "y ~ x1 + x2 | fe1 + fe2")

    Returns
    -------
    tuple
        (dependent_var, independent_vars, fixed_effects)
    """
    # Split on ~ to separate LHS and RHS
    parts = formula.split('~')
    if len(parts) != 2:
        raise ValueError("Formula must contain exactly one '~' separator")

    depvar = parts[0].strip()
    rhs = parts[1].strip()

    # Split RHS on | to separate covariates and fixed effects
    if '|' in rhs:
        covar_part, fe_part = rhs.split('|', 1)
        fixed_effects = [var.strip() for var in fe_part.split('+')]
    else:
        covar_part = rhs
        fixed_effects = []

    # Parse independent variables
    indep_vars = [var.strip() for var in covar_part.split('+')]

    return depvar, indep_vars, fixed_effects


def _construct_formula(depvar: str, indepvars: list[str], fixed_effects: list[str]) -> str:
    """Construct PyFixest formula from components."""
    if not indepvars:
        raise ValueError("At least one independent variable must be specified")

    rhs = " + ".join(indepvars)

    if fixed_effects and 'None' not in fixed_effects:
        rhs += " | " + " + ".join(fixed_effects)

    return f"{depvar} ~ {rhs}"


class InteractiveFeols:
    """
    Interactive regression dashboard for PyFixest feols models.

    This class creates a Jupyter widget-based interface for dynamically selecting
    variables, fixed effects, and clustering options for regression analysis.
    """

    def __init__(self, data: pd.DataFrame, initial_formula: str, vcov: str = 'iid', show_code: bool = False, title: str | None = None):
        """
        Initialize the interactive regression dashboard.

        Parameters
        ----------
        data : pd.DataFrame
            The dataset to use for regression analysis
        initial_formula : str
            Initial PyFixest formula (e.g., "price ~ mpg + weight | foreign")
        vcov : str, optional
            Initial variance-covariance estimator, by default 'iid'
        show_code : bool, optional
            Whether to display the Python code section. Default is False.
        title : str, optional
            Custom title for the dashboard. If None, no title is displayed.
        """
        self.data = data
        self.initial_formula = initial_formula
        self.initial_vcov = vcov
        self.show_code = show_code
        self.title = title

        # Parse initial formula
        try:
            self.initial_depvar, self.initial_indepvars, self.initial_fixef = _parse_formula(initial_formula)
        except Exception as e:
            raise ValueError(f"Error parsing initial formula: {e}")

        # Identify variable types
        self.numeric_vars = data.select_dtypes(include=[np.number]).columns.tolist()
        self.categorical_vars = data.select_dtypes(exclude=[np.number]).columns.tolist()
        self.all_vars = list(data.columns)

        # Initialize widgets
        self._create_widgets()
        self._setup_output_area()

        # Suppress warnings for cleaner output
        warnings.filterwarnings('ignore')

    def _create_widgets(self):
        """Create all the interactive widgets."""
        # Dependent variable widget
        self.depvar_widget = widgets.Dropdown(
            options=self.numeric_vars,
            value=self.initial_depvar if self.initial_depvar in self.numeric_vars else self.numeric_vars[0],
            description='',
            style={'description_width': 'initial'},
            layout={'width': '225px', 'height': '35px', 'background_color': '#f5f5f5'}
        )

        # Independent variables widget
        self.indepvars_widget = widgets.SelectMultiple(
            options=self.all_vars,
            value=self.initial_indepvars,
            description='',
            style={'description_width': 'initial'},
            layout={'width': '150px', 'height': '150px', 'background_color': '#f5f5f5'}
        )

        # Fixed effects widget
        fe_options = ['None'] + self.categorical_vars + [var for var in self.numeric_vars if self.data[var].nunique() < 20]
        initial_fe = self.initial_fixef if self.initial_fixef else ['None']

        self.fixef_widget = widgets.SelectMultiple(
            options=fe_options,
            value=initial_fe,
            description='Fixed Effects:',
            style={'description_width': '70px'},
            layout={'width': '225px', 'height': '70px', 'background_color': '#f5f5f5'}
        )

        # Clustering widget
        cluster_options = ['None'] + self.categorical_vars + [var for var in self.numeric_vars if self.data[var].nunique() < 50]

        self.cluster_widget = widgets.Dropdown(
            options=cluster_options,
            value='None',
            description='Cluster:',
            style={'description_width': '70px'},
            layout={'width': '225px', 'height': '35px', 'background_color': '#f5f5f5'}
        )

        # VCOV type widget
        self.vcov_widget = widgets.Dropdown(
            options=['iid', 'hetero', 'HC1', 'HC2', 'HC3'],
            value=self.initial_vcov if self.initial_vcov in ['iid', 'hetero', 'HC1', 'HC2', 'HC3'] else 'iid',
            description='SE Type:',
            style={'description_width': '70px'},
            layout={'width': '225px', 'height': '35px', 'background_color': '#f5f5f5'}
        )

        # Code display widget (similar to InteractiveDTable)
        self.code_widget = widgets.Textarea(
            value="",
            description='Python Code:',
            style={'description_width': 'initial'},
            layout={'width': '600px', 'height': '120px'},
            disabled=False  # Allow users to select/copy the code
        )

    def _setup_output_area(self):
        """Set up the output area and result update function."""
        self.output_area = widgets.Output()

        def update_results(change=None):
            """Update regression results when widget values change."""
            with self.output_area:
                clear_output(wait=True)

                # Get current widget values
                depvar = self.depvar_widget.value
                indepvars = list(self.indepvars_widget.value)
                fixed_effects = list(self.fixef_widget.value)
                cluster_var = self.cluster_widget.value
                vcov_type = self.vcov_widget.value

                if not indepvars:
                    print("⚠️ Please select at least one independent variable.")
                    return

                try:
                    # Clear previous output
                    self.output_area.clear_output(wait=True)

                    with self.output_area:
                        # Construct formula
                        formula = _construct_formula(depvar, indepvars, fixed_effects)

                        # Determine vcov specification
                        if cluster_var and cluster_var != 'None':
                            vcov = {'CRV1': cluster_var}
                        else:
                            vcov = vcov_type

                        # Estimate model
                        model = pf.feols(formula, data=self.data, vcov=vcov)

                        # Generate Python code for the current model configuration (only if show_code is enabled)
                        if self.show_code:
                            self._generate_code(formula, vcov, cluster_var)

                        # Display results using MakeTables without zebra striping
                        print()  # Add empty line before table
                        table = ETable(model).make(type="gt")
                        display(table)
                except Exception as e:
                    print(f"❌ Error: {e!s}")

        # Store the update function
        self._update_results = update_results

        # Connect widgets to update function
        self.depvar_widget.observe(update_results, names='value')
        self.indepvars_widget.observe(update_results, names='value')
        self.fixef_widget.observe(update_results, names='value')
        self.cluster_widget.observe(update_results, names='value')
        self.vcov_widget.observe(update_results, names='value')

    def _generate_code(self, formula, vcov, cluster_var):
        """Generate Python code for the current regression configuration."""
        # Build the code string
        code_lines = ["import pyfixest as pf", "import maketables as mt", "", "# Estimate regression model"]

        # Start the pf.feols call
        code_lines.append("model = pf.feols(")
        code_lines.append(f"    fml='{formula}',")
        code_lines.append("    data=df,  # Your DataFrame")

        # VCOV specification
        if cluster_var and cluster_var != 'None':
            code_lines.append(f"    vcov={{'CRV1': '{cluster_var}'}}")
        else:
            code_lines.append(f"    vcov='{vcov}'")

        code_lines.append(")")
        code_lines.append("")
        code_lines.append("# Display results with MakeTables")
        code_lines.append("table = mt.ETable(model)")
        code_lines.append("table.make()")

        # Update the code widget
        self.code_widget.value = "\n".join(code_lines)

    def display(self):
        """Display the interactive regression dashboard."""
        # Create the main dashboard components
        dashboard_components = []

        # Add title if provided
        if self.title:
            dashboard_components.append(widgets.HTML(f"<h3>{self.title}</h3>"))

        dashboard_components.extend([
            # Variable and model specification selection with headers
            widgets.HBox([
                # Variables section
                widgets.VBox([
                    widgets.HTML("<h4>Variables</h4>"),
                    self.indepvars_widget
                ], layout={'margin': '0 15px 0 0'}),

                # Dependent Variable section
                widgets.VBox([
                    widgets.HTML("<h4>Dependent Variable</h4>"),
                    self.depvar_widget
                ], layout={'margin': '0 15px 0 0'}),

                # Model Specification section (stacked vertically)
                widgets.VBox([
                    widgets.HTML("<h4>Model Specification</h4>"),
                    self.fixef_widget,
                    widgets.HTML("<br>", layout={'margin': '2px 0'}),
                    self.cluster_widget,
                    self.vcov_widget
                ], layout={'margin': '0 15px 0 0'})
            ]),

            # Results area
            self.output_area
        ])

        # Conditionally add Python Code section
        if self.show_code:
            dashboard_components.extend([
                widgets.HTML("<p>Copy this code to reproduce the regression in your analysis:</p>"),
                self.code_widget
            ])

        # Create the dashboard layout
        dashboard = widgets.VBox(dashboard_components)

        # Display the dashboard
        display(dashboard)

        # Trigger initial update
        self._update_results()


def interactive_regression(data: pd.DataFrame, formula: str, vcov: str = 'iid', show_code: bool = False, title: str | None = None) -> InteractiveFeols:
    """
    Create and display an interactive regression dashboard.

    This function provides a convenient interface for creating interactive regression
    analysis dashboards in Jupyter notebooks. Users can dynamically modify model
    specifications and see results updated in real-time using MakeTables.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to use for regression analysis
    formula : str
        Initial PyFixest formula specification (e.g., "price ~ mpg + weight | foreign")
    vcov : str, optional
        Initial variance-covariance estimator ('iid', 'hetero', 'HC1', 'HC2', 'HC3'),
        by default 'iid'
    show_code : bool, optional
        Whether to display the Python code output section. Default is False.
    title : str, optional
        Custom title for the dashboard. If None, no title is displayed.

    Returns
    -------
    InteractiveFeols
        The interactive regression dashboard object

    Examples
    --------
    >>> import pandas as pd
    >>> import maketables as mt
    >>>
    >>> # Load data
    >>> df = mt.import_dta("auto.dta")
    >>>
    >>> # Create interactive dashboard
    >>> dashboard = mt.interactive_regression(df, "price ~ mpg + weight")
    >>>
    >>> # The dashboard is automatically displayed and ready for interaction

    Notes
    -----
    - Requires ipywidgets and pyfixest to be installed
    - Best used in Jupyter notebooks with widget support
    - Results are displayed using MakeTables for publication-ready formatting
    - Supports real-time updates as you modify variable selections
    """
    dashboard = InteractiveFeols(data, formula, vcov, show_code, title)
    dashboard.display()
    return dashboard


class InteractiveDTable:
    """
    Interactive descriptive statistics dashboard for exploring data with DTable.

    This class creates a Jupyter widget-based interface for dynamically selecting
    variables, statistics, and grouping options for descriptive statistics analysis.
    """

    def __init__(self, data: pd.DataFrame, initial_vars: list[str] | None = None, show_code: bool = False, title: str | None = None):
        """
        Initialize the interactive descriptive statistics dashboard.

        Parameters
        ----------
        data : pd.DataFrame
            The dataset to use for descriptive statistics analysis
        initial_vars : list[str], optional
            Initial variables to include in the table. If None, selects first few numeric variables.
        show_code : bool, optional
            Whether to display the Python code section. Default is False.
        title : str, optional
            Custom title for the dashboard. If None, no title is displayed.
        """
        self.data = data
        self.show_code = show_code
        self.title = title

        # Identify variable types
        self.numeric_vars = data.select_dtypes(include=[np.number]).columns.tolist()
        self.categorical_vars = data.select_dtypes(exclude=[np.number]).columns.tolist()
        self.all_vars = list(data.columns)

        # Set initial variables
        if initial_vars is None:
            self.initial_vars = self.numeric_vars[:min(5, len(self.numeric_vars))]
        else:
            self.initial_vars = initial_vars

        # Initialize widgets
        self._create_widgets()
        self._setup_output_area()

        # Suppress warnings for cleaner output
        warnings.filterwarnings('ignore')

    def _create_widgets(self):
        """Create all the interactive widgets."""
        # Variables selection widget - only show numerical variables for descriptive statistics
        self.vars_widget = widgets.SelectMultiple(
            options=self.numeric_vars,
            value=self.initial_vars,
            description='',
            style={'description_width': 'initial'},
            layout={'width': '150px', 'height': '150px', 'background_color': '#f5f5f5'}
        )

        # Statistics selection widget
        available_stats = ['count', 'mean', 'std', 'min', 'max', 'median', 'var', 'sum', 'mean_std', 'mean_newline_std']
        self.stats_widget = widgets.SelectMultiple(
            options=available_stats,
            value=['count', 'mean', 'std'],
            description='',
            style={'description_width': 'initial'},
            layout={'width': '150px', 'height': '150px', 'background_color': '#f5f5f5'}
        )

        # Group by columns widget
        bycol_options = ['None'] + self.categorical_vars + [var for var in self.numeric_vars if self.data[var].nunique() < 10]
        self.bycol_widget = widgets.SelectMultiple(
            options=bycol_options,
            value=['None'],
            description='Columns:',
            style={'description_width': '70px'},
            layout={'width': '225px', 'height': '70px', 'background_color': '#f5f5f5'}
        )

        # Group by rows widget
        byrow_options = ['None'] + self.categorical_vars + [var for var in self.numeric_vars if self.data[var].nunique() < 20]
        self.byrow_widget = widgets.Dropdown(
            options=byrow_options,
            value='None',
            description='Rows:',
            style={'description_width': '70px'},
            layout={'width': '225px', 'height': '35px', 'background_color': '#f5f5f5'}
        )

        # Digits precision widget
        self.digits_widget = widgets.BoundedIntText(
            value=2,
            min=1,
            max=6,
            step=1,
            description='Decimal places:',
            style={'description_width': '100px'},
            layout={'width': '180px', 'margin': '2px 0px 2px 0px', 'background_color': '#f5f5f5'}
        )

        # Hide stats widget
        self.hide_stats_widget = widgets.Checkbox(
            value=False,
            description='Hide statistic names',
            style={'description_width': 'initial'},
            layout={'width': '180px', 'margin': '2px 0px 2px 0px', 'background_color': '#f5f5f5'}
        )

        # Counts row below widget
        self.counts_row_below_widget = widgets.Checkbox(
            value=False,
            description='Show counts in separate row',
            style={'description_width': 'initial'},
            layout={'width': '180px', 'margin': '2px 0px 2px 0px', 'background_color': '#f5f5f5'}
        )

        # Code display widget
        self.code_widget = widgets.Textarea(
            value="",
            description='Python Code:',
            style={'description_width': 'initial'},
            layout={'width': '600px', 'height': '120px'},
            disabled=False  # Allow users to select/copy the code
        )

    def _setup_output_area(self):
        """Set up the output area and result update function."""
        self.output_area = widgets.Output()

        def update_results(change=None):
            """Update descriptive statistics when widget values change."""
            with self.output_area:
                clear_output(wait=True)

                # Get current widget values
                vars_selected = list(self.vars_widget.value)
                stats_selected = list(self.stats_widget.value)
                bycol_selected = list(self.bycol_widget.value)
                byrow_selected = self.byrow_widget.value
                digits = self.digits_widget.value
                hide_stats = self.hide_stats_widget.value
                counts_row_below = self.counts_row_below_widget.value

                if not vars_selected:
                    print("⚠️ Please select at least one variable.")
                    return

                if not stats_selected:
                    print("⚠️ Please select at least one statistic.")
                    return

                try:
                    # Process grouping variables
                    bycol = None if 'None' in bycol_selected else [var for var in bycol_selected if var != 'None']
                    byrow = None if byrow_selected == 'None' else byrow_selected

                    # Create DTable with better formatting for small numbers
                    # Use format_spec to control display precision more intelligently
                    format_spec = {
                        "mean": f".{digits}f",
                        "std": f".{digits}f",
                        "median": f".{digits}f",
                        "min": f".{digits}f",
                        "max": f".{digits}f",
                        "var": f".{max(digits + 1, 3)}f",  # Variance needs more precision
                        "sum": f",.{digits}f"
                    }

                    table = DTable(
                        df=self.data,
                        vars=vars_selected,
                        stats=stats_selected,
                        bycol=bycol,
                        byrow=byrow,
                        format_spec=format_spec,
                        hide_stats=hide_stats,
                        counts_row_below=counts_row_below
                    )

                    # Generate Python code for the DTable call (only if show_code is enabled)
                    if self.show_code:
                        self._generate_code(vars_selected, stats_selected, bycol, byrow, digits, hide_stats, counts_row_below)

                    # Display results
                    print()  # Add empty line before table
                    table_output = table.make(type="gt")
                    display(table_output)

                except Exception as e:
                    print(f"❌ Error: {e!s}")

        # Store the update function
        self._update_results = update_results

        # Connect widgets to update function
        self.vars_widget.observe(update_results, names='value')
        self.stats_widget.observe(update_results, names='value')
        self.bycol_widget.observe(update_results, names='value')
        self.byrow_widget.observe(update_results, names='value')
        self.digits_widget.observe(update_results, names='value')
        self.hide_stats_widget.observe(update_results, names='value')
        self.counts_row_below_widget.observe(update_results, names='value')

    def _generate_code(self, vars_selected, stats_selected, bycol, byrow, digits, hide_stats, counts_row_below):
        """Generate Python code for the current DTable configuration."""
        # Build the code string
        code_lines = ["import maketables as mt", "", "# Create descriptive statistics table"]

        # Start the DTable call
        code_lines.append("table = mt.DTable(")
        code_lines.append("    df=df,  # Your DataFrame")

        # Variables
        vars_str = "[" + ", ".join([f"'{var}'" for var in vars_selected]) + "]"
        code_lines.append(f"    vars={vars_str},")

        # Statistics
        stats_str = "[" + ", ".join([f"'{stat}'" for stat in stats_selected]) + "]"
        code_lines.append(f"    stats={stats_str},")

        # Grouping options
        if bycol:
            bycol_str = "[" + ", ".join([f"'{var}'" for var in bycol]) + "]"
            code_lines.append(f"    bycol={bycol_str},")

        if byrow:
            code_lines.append(f"    byrow='{byrow}',")

        # Format specification
        if digits != 2:  # Only show if different from default
            format_spec_lines = [
                "    format_spec={",
                f"        'mean': '.{digits}f',",
                f"        'std': '.{digits}f',",
                f"        'median': '.{digits}f',",
                f"        'min': '.{digits}f',",
                f"        'max': '.{digits}f',",
                f"        'var': '.{max(digits + 1, 3)}f',",
                f"        'sum': ',.{digits}f'",
                "    },"
            ]
            code_lines.extend(format_spec_lines)

        # Hide stats option
        if hide_stats:
            code_lines.append("    hide_stats=True,")

        # Counts row below option
        if counts_row_below:
            code_lines.append("    counts_row_below=True,")

        code_lines.append(")")
        code_lines.append("")
        code_lines.append("# Display the table")
        code_lines.append("table.make()")

        # Update the code widget
        self.code_widget.value = "\n".join(code_lines)

    def display(self):
        """Display the interactive descriptive statistics dashboard."""
        # Create the main dashboard components
        dashboard_components = []

        # Add title if provided
        if self.title:
            dashboard_components.append(widgets.HTML(f"<h3>{self.title}</h3>"))

        dashboard_components.extend([
            # Variable and statistics selection with headers
            widgets.HBox([
                # Variables section
                widgets.VBox([
                    widgets.HTML("<h4>Variables</h4>"),
                    self.vars_widget
                ], layout={'margin': '0 15px 0 0'}),

                # Statistics section
                widgets.VBox([
                    widgets.HTML("<h4>Statistics</h4>"),
                    self.stats_widget
                ], layout={'margin': '0 15px 0 0'}),

                # Group by section (stacked vertically)
                widgets.VBox([
                    widgets.HTML("<h4>Group by</h4>"),
                    self.bycol_widget,
                    widgets.HTML("<br>", layout={'margin': '2px 0'}),
                    self.byrow_widget
                ], layout={'margin': '0 15px 0 0'}),

                # Formatting section
                widgets.VBox([
                    widgets.HTML("<h4>Formatting</h4>"),
                    self.digits_widget,
                    self.hide_stats_widget,
                    self.counts_row_below_widget
                ], layout={'margin': '0 0 0 0', 'align_items': 'flex-start'})
            ]),

            # Results area
            self.output_area
        ])

        # Conditionally add Python Code section
        if self.show_code:
            dashboard_components.extend([
                widgets.HTML("<p>Copy this code to reproduce the table in your analysis:</p>"),
                self.code_widget
            ])

        # Create the dashboard layout
        dashboard = widgets.VBox(dashboard_components)

        # Display the dashboard
        display(dashboard)

        # Trigger initial update
        self._update_results()


def interactive_dtable(data: pd.DataFrame, vars: list[str] | None = None, show_code: bool = False, title: str | None = None) -> InteractiveDTable:
    """
    Create and display an interactive descriptive statistics dashboard.

    This function provides a convenient interface for creating interactive descriptive
    statistics dashboards in Jupyter notebooks. Users can dynamically select variables,
    statistics, and grouping options to explore their data.

    Parameters
    ----------
    data : pd.DataFrame
        The dataset to analyze
    vars : list[str], optional
        Initial variables to include. If None, selects first few numeric variables.
    show_code : bool, optional
        Whether to display the Python code output section. Default is False.
    title : str, optional
        Custom title for the dashboard. If None, no title is displayed.

    Returns
    -------
    InteractiveDTable
        The interactive descriptive statistics dashboard object

    Examples
    --------
    >>> import pandas as pd
    >>> import maketables as mt
    >>>
    >>> # Load data
    >>> df = mt.import_dta("auto.dta")
    >>>
    >>> # Create interactive descriptive statistics dashboard
    >>> dashboard = mt.interactive_dtable(df)
    >>>
    >>> # Or specify initial variables
    >>> dashboard = mt.interactive_dtable(df, vars=['price', 'mpg', 'weight'])

    Notes
    -----
    - Requires ipywidgets to be installed
    - Best used in Jupyter notebooks with widget support
    - Results are displayed using MakeTables DTable for publication-ready formatting
    - Supports real-time updates as you modify selections
    - Automatically detects numeric vs categorical variables
    """
    dashboard = InteractiveDTable(data, vars, show_code, title)
    dashboard.display()
    return dashboard
