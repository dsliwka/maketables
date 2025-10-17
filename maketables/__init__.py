from .btable import BTable
from .dtable import DTable
from .etable import ETable
from .extractors import ModelExtractor, clear_extractors, register_extractor
from .importdta import export_dta, get_var_labels, import_dta, set_var_labels
from .mtable import MTable

__all__ = [
    "MTable",
    "BTable",
    "DTable",
    "ETable",
    "register_extractor",
    "clear_extractors",
    "ModelExtractor",
    "import_dta",
    "export_dta",
    "get_var_labels",
    "set_var_labels",
]

# Conditionally import PyStata integration if available
try:
    from .pystata_extractor import (
        StataResultWrapper,
        rstata,
        extract_current_stata_results,
        PYSTATA_AVAILABLE
    )
except ImportError:
    # PyStata not available, these functions won't be accessible
    PYSTATA_AVAILABLE = False
