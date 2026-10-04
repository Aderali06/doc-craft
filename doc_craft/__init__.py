"""doc-craft: Automated Python function docstring generator using AST and Google Style format."""

__version__ = "0.1.0"
__author__ = "DocCraft Team"
__license__ = "MIT"

from doc_craft.parser import (
    DocstringReport,
    FunctionInfo,
    ParamInfo,
    extract_function_info,
    generate_google_docstring,
    process_file,
    process_python_source,
)

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "DocstringReport",
    "FunctionInfo",
    "ParamInfo",
    "extract_function_info",
    "generate_google_docstring",
    "process_file",
    "process_python_source",
]
