"""
Simple symbol translation for MakeTables output formats.

Just add symbols to the SYMBOLS dictionary below and they'll be automatically
translated to the appropriate format (LaTeX, HTML, DOCX, etc.).
"""

# Symbol translations: canonical_symbol -> {format: representation}
SYMBOLS = {
    # Statistical symbols
    "R²": {
        "tex": r"$R^2$",         # LaTeX math mode superscript notation
        "html": "R<sup>2</sup>", # HTML superscript tags (used by GT too)
        "docx": "R²",            # Unicode works in Word
        "plain": "R²"           # Plain text notation
    },

    # Interaction symbol
    "×": {
        "tex": r"$\times$",     # LaTeX math mode times symbol
        "html": "&times;",       # HTML entity (used by GT too)
        "docx": "×",
        "plain": "x"
    },

    # Mathematical comparison symbols
    "≤": {
        "tex": r"$\leq$",       # LaTeX math mode less than or equal
        "html": "&le;",          # HTML entity (used by GT too)
        "docx": "≤",
        "plain": "<="
    },

    "≥": {
        "tex": r"$\geq$",       # LaTeX math mode greater than or equal
        "html": "&ge;",          # HTML entity (used by GT too)
        "docx": "≥",
        "plain": ">="
    },

    # Greek letters commonly used in statistics
    "α": {
        "tex": r"$\alpha$",     # LaTeX math mode alpha
        "html": "&alpha;",       # HTML entity (used by GT too)
        "docx": "α",
        "plain": "alpha"
    },

    "β": {
        "tex": r"$\beta$",      # LaTeX math mode beta
        "html": "&beta;",        # HTML entity (used by GT too)
        "docx": "β",
        "plain": "beta"
    },

    "σ": {
        "tex": r"$\sigma$",     # LaTeX math mode sigma
        "html": "&sigma;",       # HTML entity (used by GT too)
        "docx": "σ",
        "plain": "sigma"
    },

    # Other common symbols
    "±": {
        "tex": r"$\pm$",        # LaTeX math mode plus-minus
        "html": "&plusmn;",      # HTML entity (used by GT too)
        "docx": "±",
        "plain": "+/-"
    },

    "°": {
        "tex": r"$^\circ$",     # LaTeX math mode degree symbol
        "html": "&deg;",         # HTML entity (used by GT too)
        "docx": "°",
        "plain": "deg"
    }
}


def translate_symbols(text: str, output_format: str) -> str:
    """
    Translate symbols in text to the specified output format.

    Args:
        text: Text containing symbols to translate
        output_format: Target format ('tex', 'html', 'docx', 'gt', 'plain')
                      Note: 'gt' is mapped to 'html' since GT uses HTML rendering

    Returns:
        Text with symbols translated to the target format

    Example:
        >>> translate_symbols("Age×Income with R²", "tex")
        "Age\\times Income with R²"
        >>> translate_symbols("α ≤ 0.05", "html")
        "&alpha; &le; 0.05"
    """
    if not isinstance(text, str):
        return text

    # Map 'gt' to 'html' since GT (Great Tables) uses HTML rendering
    format_key = "html" if output_format == "gt" else output_format

    result = text
    for symbol, translations in SYMBOLS.items():
        if symbol in result:
            target_symbol = translations.get(format_key, symbol)
            result = result.replace(symbol, target_symbol)

    return result
