"""Unit tests for doc-craft AST parser and docstring generator."""

from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import pytest

from doc_craft.parser import (
    FunctionInfo,
    ParamInfo,
    extract_function_info,
    generate_google_docstring,
    process_file,
    process_python_source,
)


def test_extract_simple_function() -> None:
    """Test extracting basic function with arguments and return type."""
    code = """
def calculate_area(width: float, height: float) -> float:
    return width * height
"""
    functions = extract_function_info(code)
    assert len(functions) == 1
    func = functions[0]

    assert func.name == "calculate_area"
    assert not func.is_async
    assert not func.is_method
    assert func.return_type == "float"
    assert len(func.params) == 2
    assert func.params[0].name == "width"
    assert func.params[0].type_annotation == "float"
    assert func.params[0].default_value is None
    assert func.params[1].name == "height"
    assert func.params[1].type_annotation == "float"


def test_extract_function_with_defaults_and_varargs() -> None:
    """Test extracting parameters with default values, *args, and **kwargs."""
    code = """
def process_data(
    item_id: int,
    format_type: str = "json",
    *tags: str,
    timeout: int = 30,
    **options: str,
) -> dict:
    return {"status": "ok"}
"""
    functions = extract_function_info(code)
    assert len(functions) == 1
    func = functions[0]

    param_names = [p.name for p in func.params]
    assert param_names == ["item_id", "format_type", "tags", "timeout", "options"]

    # Check defaults and kinds
    assert func.params[0].kind == "standard"
    assert func.params[1].default_value == "'json'" or func.params[1].default_value == '"json"'
    assert func.params[2].kind == "vararg"
    assert func.params[3].kind == "kwonly"
    assert func.params[3].default_value == "30"
    assert func.params[4].kind == "kwarg"


def test_extract_async_function() -> None:
    """Test extracting asynchronous function definition."""
    code = """
async def fetch_user(user_id: int) -> dict:
    return await api.get(user_id)
"""
    functions = extract_function_info(code)
    assert len(functions) == 1
    assert functions[0].is_async is True
    assert functions[0].name == "fetch_user"


def test_extract_class_methods_and_self_cls_omission() -> None:
    """Test that methods inside a class identify as methods and omit self/cls in Args."""
    code = """
class DataProcessor:
    def __init__(self, name: str, retries: int = 3):
        self.name = name
        self.retries = retries

    def execute(self, payload: dict) -> bool:
        return True

    @classmethod
    def from_config(cls, path: str) -> "DataProcessor":
        return cls("custom")

    @staticmethod
    def is_valid(data: str) -> bool:
        return len(data) > 0
"""
    functions = extract_function_info(code)
    assert len(functions) == 4

    init_func, exec_func, class_method, static_method = functions

    assert init_func.is_method is True
    assert exec_func.is_method is True
    assert class_method.is_classmethod is True
    assert static_method.is_staticmethod is True

    # Test Google docstring generation for class methods
    init_doc = generate_google_docstring(init_func, base_indent=8)
    assert "self" not in init_doc  # self omitted from Args
    assert "name (str):" in init_doc
    assert "retries (int):" in init_doc
    assert "Defaults to 3." in init_doc

    cls_doc = generate_google_docstring(class_method, base_indent=8)
    assert "cls" not in cls_doc  # cls omitted from Args
    assert "path (str):" in cls_doc

    static_doc = generate_google_docstring(static_method, base_indent=8)
    assert "data (str):" in static_doc


def test_extract_raises_exceptions() -> None:
    """Test detecting raised exceptions in function body."""
    code = """
def parse_int(value: str) -> int:
    if not value.isdigit():
        raise ValueError("Invalid integer string")
    if int(value) < 0:
        raise custom.NegativeNumberError("Negative not allowed")
    return int(value)
"""
    functions = extract_function_info(code)
    assert len(functions) == 1
    func = functions[0]

    assert "ValueError" in func.raises
    assert "custom.NegativeNumberError" in func.raises

    doc = generate_google_docstring(func, base_indent=4)
    assert "Raises:" in doc
    assert "ValueError: If an error occurs during execution." in doc
    assert "custom.NegativeNumberError: If an error occurs during execution." in doc


def test_generate_google_docstring_format() -> None:
    """Test complete Google Style Docstring layout."""
    info = FunctionInfo(
        name="authenticate_user",
        is_async=False,
        is_method=False,
        params=[
            ParamInfo(name="username", type_annotation="str"),
            ParamInfo(name="password", type_annotation="str"),
            ParamInfo(name="remember_me", type_annotation="bool", default_value="False"),
        ],
        return_type="Optional[UserSession]",
        raises=["AuthenticationError"],
    )

    docstring = generate_google_docstring(info, base_indent=4)
    expected_parts = [
        '    """Authenticate user.',
        "",
        "    Args:",
        "        username (str): The username value.",
        "        password (str): The password value.",
        "        remember_me (bool): The remember me value. Defaults to False.",
        "",
        "    Returns:",
        "        Optional[UserSession]: The return value of authenticate user.",
        "",
        "    Raises:",
        "        AuthenticationError: If an error occurs during execution.",
        '    """',
    ]
    expected_docstring = "\n".join(expected_parts)
    assert docstring == expected_docstring


def test_process_python_source_insertion() -> None:
    """Test inserting docstrings into source code without docstrings."""
    code = """def add_numbers(a: int, b: int) -> int:
    return a + b
"""
    modified, reports = process_python_source(code)
    assert len(reports) == 1
    assert reports[0].status == "generated"
    assert '"""Add numbers.' in modified
    assert "Args:" in modified
    assert "a (int):" in modified
    assert "Returns:" in modified
    assert "int: The return value of add numbers." in modified
    assert "return a + b" in modified

    # Verify AST can still parse the modified code
    ast.parse(modified)


def test_process_python_source_skip_existing() -> None:
    """Test that existing docstrings are preserved when overwrite=False."""
    code = '''def greet(name: str) -> str:
    """My custom greeting docstring."""
    return f"Hello {name}"
'''
    modified, reports = process_python_source(code, overwrite=False)
    assert len(reports) == 1
    assert reports[0].status == "skipped"
    assert "My custom greeting docstring." in modified
    assert modified.strip() == code.strip()


def test_process_python_source_overwrite() -> None:
    """Test that existing docstrings are updated when overwrite=True."""
    code = '''def greet(name: str) -> str:
    """Old docstring."""
    return f"Hello {name}"
'''
    modified, reports = process_python_source(code, overwrite=True)
    assert len(reports) == 1
    assert reports[0].status == "updated"
    assert "Old docstring." not in modified
    assert "Args:" in modified
    assert "name (str):" in modified
    assert "Returns:" in modified


def test_process_file_in_place() -> None:
    """Test process_file with in_place=True writing to temporary file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "sample.py"
        test_file.write_text("def multiply(x: int, y: int) -> int:\n    return x * y\n", encoding="utf-8")

        modified, reports = process_file(test_file, in_place=True)
        assert len(reports) == 1
        assert reports[0].status == "generated"

        content_on_disk = test_file.read_text(encoding="utf-8")
        assert '"""Multiply.' in content_on_disk
        assert "x (int):" in content_on_disk
        assert "return x * y" in content_on_disk
