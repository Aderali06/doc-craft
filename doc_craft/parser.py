"""AST Parser and Docstring Generator module for doc-craft.

This module provides AST traversal, function signature inspection,
Google-style docstring generation, and source code modification.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import difflib
import os
from pathlib import Path
import re
from typing import List, Optional, Tuple


@dataclass
class ParamInfo:
    """Information about a function parameter."""

    name: str
    type_annotation: Optional[str] = None
    default_value: Optional[str] = None
    kind: str = "standard"  # positional_only, standard, vararg, kwonly, kwarg


@dataclass
class FunctionInfo:
    """Information extracted from an AST function definition."""

    name: str
    is_async: bool = False
    is_method: bool = False
    is_classmethod: bool = False
    is_staticmethod: bool = False
    params: List[ParamInfo] = field(default_factory=list)
    return_type: Optional[str] = None
    has_docstring: bool = False
    existing_docstring: Optional[str] = None
    raises: List[str] = field(default_factory=list)
    lineno: int = 0
    end_lineno: int = 0
    col_offset: int = 0
    body_lineno: int = 0
    body_col_offset: int = 0
    docstring_lineno_start: Optional[int] = None
    docstring_lineno_end: Optional[int] = None


@dataclass
class DocstringReport:
    """Report detailing the result of processing a function."""

    file_path: str
    function_name: str
    lineno: int
    status: str  # 'generated', 'updated', 'skipped'
    details: str = ""


class _FunctionVisitor(ast.NodeVisitor):
    """AST NodeVisitor that collects function definitions and context."""

    def __init__(self) -> None:
        self.functions: List[FunctionInfo] = []
        self._class_stack: List[ast.ClassDef] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context when visiting methods."""
        self._class_stack.append(node)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit standard synchronous function definition."""
        self._process_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit asynchronous function definition."""
        self._process_function(node, is_async=True)
        self.generic_visit(node)

    def _process_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool,
    ) -> None:
        """Extract metadata from FunctionDef or AsyncFunctionDef node."""
        is_method = len(self._class_stack) > 0
        is_classmethod = False
        is_staticmethod = False

        for decorator in node.decorator_list:
            dec_name = _get_decorator_name(decorator)
            if dec_name == "classmethod":
                is_classmethod = True
            elif dec_name == "staticmethod":
                is_staticmethod = True

        # Extract parameters
        params = _extract_parameters(node.args)

        # Extract return type
        return_type = None
        if node.returns is not None:
            return_type = ast.unparse(node.returns)

        # Check existing docstring
        has_docstring = False
        existing_docstring = None
        docstring_lineno_start = None
        docstring_lineno_end = None

        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, (ast.Constant, ast.Str))
        ):
            val = node.body[0].value
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                has_docstring = True
                existing_docstring = val.value
                docstring_lineno_start = node.body[0].lineno
                docstring_lineno_end = getattr(node.body[0], "end_lineno", node.body[0].lineno)
            elif isinstance(val, ast.Str):
                has_docstring = True
                existing_docstring = val.s
                docstring_lineno_start = node.body[0].lineno
                docstring_lineno_end = getattr(node.body[0], "end_lineno", node.body[0].lineno)

        # Extract raised exceptions within this function (not descending into inner functions)
        raises = _extract_raises(node.body)

        body_lineno = node.body[0].lineno if node.body else node.lineno
        body_col_offset = node.body[0].col_offset if node.body else node.col_offset + 4

        func_info = FunctionInfo(
            name=node.name,
            is_async=is_async,
            is_method=is_method,
            is_classmethod=is_classmethod,
            is_staticmethod=is_staticmethod,
            params=params,
            return_type=return_type,
            has_docstring=has_docstring,
            existing_docstring=existing_docstring,
            raises=raises,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            col_offset=node.col_offset,
            body_lineno=body_lineno,
            body_col_offset=body_col_offset,
            docstring_lineno_start=docstring_lineno_start,
            docstring_lineno_end=docstring_lineno_end,
        )
        self.functions.append(func_info)


def _get_decorator_name(decorator: ast.expr) -> str:
    """Extract string name from decorator expression."""
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _get_decorator_name(decorator.func)
    return ""


def _extract_parameters(args_node: ast.arguments) -> List[ParamInfo]:
    """Extract all parameters including positional, keyword, vararg, and kwarg."""
    params: List[ParamInfo] = []

    # 1. Positional-only args (Python 3.8+)
    posonly_count = len(args_node.posonlyargs)
    posonly_defaults_offset = len(args_node.posonlyargs) + len(args_node.args) - len(args_node.defaults)

    for i, arg in enumerate(args_node.posonlyargs):
        type_ann = ast.unparse(arg.annotation) if arg.annotation else None
        default_val = None
        default_idx = i - posonly_defaults_offset
        if default_idx >= 0 and default_idx < len(args_node.defaults):
            default_val = ast.unparse(args_node.defaults[default_idx])

        params.append(
            ParamInfo(
                name=arg.arg,
                type_annotation=type_ann,
                default_value=default_val,
                kind="positional_only",
            )
        )

    # 2. Regular positional / keyword args
    std_offset = len(args_node.args) - (len(args_node.defaults) - max(0, posonly_count - posonly_defaults_offset))
    # Standard mapping for defaults:
    # defaults are aligned to the right of (posonlyargs + args)
    total_pos_args = args_node.posonlyargs + args_node.args
    num_defaults = len(args_node.defaults)

    # Recompute cleanly with direct total indexing
    for i, arg in enumerate(args_node.args):
        type_ann = ast.unparse(arg.annotation) if arg.annotation else None
        total_idx = posonly_count + i
        default_idx = total_idx - (len(total_pos_args) - num_defaults)
        default_val = None
        if default_idx >= 0 and default_idx < num_defaults:
            default_val = ast.unparse(args_node.defaults[default_idx])

        params.append(
            ParamInfo(
                name=arg.arg,
                type_annotation=type_ann,
                default_value=default_val,
                kind="standard",
            )
        )

    # 3. Vararg (*args)
    if args_node.vararg:
        vararg = args_node.vararg
        type_ann = ast.unparse(vararg.annotation) if vararg.annotation else None
        params.append(
            ParamInfo(
                name=vararg.arg,
                type_annotation=type_ann,
                default_value=None,
                kind="vararg",
            )
        )

    # 4. Keyword-only args
    for i, arg in enumerate(args_node.kwonlyargs):
        type_ann = ast.unparse(arg.annotation) if arg.annotation else None
        default_val = None
        if i < len(args_node.kw_defaults) and args_node.kw_defaults[i] is not None:
            default_val = ast.unparse(args_node.kw_defaults[i])

        params.append(
            ParamInfo(
                name=arg.arg,
                type_annotation=type_ann,
                default_value=default_val,
                kind="kwonly",
            )
        )

    # 5. Kwarg (**kwargs)
    if args_node.kwarg:
        kwarg = args_node.kwarg
        type_ann = ast.unparse(kwarg.annotation) if kwarg.annotation else None
        params.append(
            ParamInfo(
                name=kwarg.arg,
                type_annotation=type_ann,
                default_value=None,
                kind="kwarg",
            )
        )

    return params


def _extract_raises(body: List[ast.stmt]) -> List[str]:
    """Scan function body statements for raised exceptions."""
    raises: List[str] = []
    seen = set()

    for stmt in body:
        for node in ast.walk(stmt):
            # Do not descend into nested function or class definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not stmt:
                continue

            if isinstance(node, ast.Raise):
                exc_name = _get_exception_name(node.exc)
                if exc_name and exc_name not in seen:
                    seen.add(exc_name)
                    raises.append(exc_name)

    return raises


def _get_exception_name(exc_node: Optional[ast.expr]) -> Optional[str]:
    """Get the string identifier of an exception in an ast.Raise node."""
    if exc_node is None:
        return None
    if isinstance(exc_node, ast.Name):
        return exc_node.id
    if isinstance(exc_node, ast.Call):
        return _get_exception_name(exc_node.func)
    if isinstance(exc_node, ast.Attribute):
        return ast.unparse(exc_node)
    return None


def extract_function_info(source_code: str) -> List[FunctionInfo]:
    """Parse Python source code and extract all function definitions with metadata.

    Args:
        source_code (str): The Python source code string.

    Returns:
        List[FunctionInfo]: List of extracted function info objects.

    Raises:
        SyntaxError: If the source code cannot be parsed as valid Python.
    """
    tree = ast.parse(source_code)
    visitor = _FunctionVisitor()
    visitor.visit(tree)
    return visitor.functions


def _humanize_name(name: str) -> str:
    """Generate a human-readable summary sentence from a function name.

    Args:
        name (str): The function name.

    Returns:
        str: Human-readable sentence summary.
    """
    if name == "__init__":
        return "Initialize the instance."
    if name == "__str__":
        return "Return string representation of the instance."
    if name == "__repr__":
        return "Return official string representation of the instance."
    if name == "__enter__":
        return "Enter runtime context and return self."
    if name == "__exit__":
        return "Exit runtime context and handle exceptions."
    if name == "__call__":
        return "Make the instance callable as a function."

    # Strip leading/trailing underscores
    clean_name = name.strip("_")
    if not clean_name:
        clean_name = name

    # Split snake_case or camelCase
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", clean_name).replace("_", " ").split()
    if not words:
        return f"Execute {name} function."

    # Capitalize first word
    words[0] = words[0].capitalize()
    sentence = " ".join(words)

    # Standard prefix verbs handling
    first_word_lower = words[0].lower()
    if first_word_lower in {"is", "has", "can", "should", "check"}:
        return f"Check if {sentence.lower().removeprefix(first_word_lower).strip()}."

    return f"{sentence}."


def _format_param_desc(param: ParamInfo) -> str:
    """Generate parameter description according to Google Style Docstrings."""
    clean_name = param.name.strip("_")
    if param.kind == "vararg":
        name_str = f"*{param.name}"
        desc = f"Variable length argument list of {clean_name}."
    elif param.kind == "kwarg":
        name_str = f"**{param.name}"
        desc = f"Arbitrary keyword arguments for {clean_name}."
    else:
        name_str = param.name
        desc = f"The {clean_name.replace('_', ' ')} value."

    if param.type_annotation:
        if param.default_value is not None:
            return f"{name_str} ({param.type_annotation}): {desc} Defaults to {param.default_value}."
        return f"{name_str} ({param.type_annotation}): {desc}"
    else:
        if param.default_value is not None:
            return f"{name_str}: {desc} Defaults to {param.default_value}."
        return f"{name_str}: {desc}"


def generate_google_docstring(info: FunctionInfo, base_indent: int = 4) -> str:
    """Generate a Google Style Docstring string from FunctionInfo.

    Args:
        info (FunctionInfo): Metadata of the function.
        base_indent (int): Number of spaces for base indentation of the docstring.

    Returns:
        str: Formatted Google Style docstring including triple quotes and proper indentation.
    """
    indent = " " * base_indent
    sub_indent = " " * (base_indent + 4)
    lines: List[str] = []

    # 1. Summary line
    summary = _humanize_name(info.name)
    lines.append(f'{indent}"""{summary}')

    # Filter parameters: Google style excludes 'self' and 'cls' from Args
    documented_params: List[ParamInfo] = []
    for param in info.params:
        if info.is_method and not info.is_staticmethod and param.name in {"self", "cls"}:
            continue
        documented_params.append(param)

    sections_added = False

    # 2. Args section
    if documented_params:
        lines.append("")
        lines.append(f"{indent}Args:")
        for param in documented_params:
            param_desc = _format_param_desc(param)
            lines.append(f"{sub_indent}{param_desc}")
        sections_added = True

    # 3. Returns section (omit if void or None unless explicitly documented)
    if info.return_type and info.return_type not in {"None", "typing.NoReturn", "NoReturn"}:
        lines.append("")
        lines.append(f"{indent}Returns:")
        lines.append(f"{sub_indent}{info.return_type}: The return value of {info.name.replace('_', ' ')}.")
        sections_added = True

    # 4. Raises section
    if info.raises:
        lines.append("")
        lines.append(f"{indent}Raises:")
        for exc in info.raises:
            lines.append(f"{sub_indent}{exc}: If an error occurs during execution.")
        sections_added = True

    # Closing quotes
    if sections_added:
        lines.append(f'{indent}"""')
    else:
        # If single summary without args/returns/raises, format cleanly
        return f'{indent}"""{summary}"""'

    return "\n".join(lines)


def process_python_source(
    source_code: str,
    overwrite: bool = False,
    file_path: str = "<source>",
) -> Tuple[str, List[DocstringReport]]:
    """Process Python source code and insert or update Google-style docstrings.

    Args:
        source_code (str): The input Python source code.
        overwrite (bool): Whether to overwrite existing docstrings. Defaults to False.
        file_path (str): File path identifier for reporting purposes.

    Returns:
        Tuple[str, List[DocstringReport]]: Modified source code and list of operation reports.
    """
    try:
        functions = extract_function_info(source_code)
    except SyntaxError as e:
        return source_code, [
            DocstringReport(
                file_path=file_path,
                function_name="",
                lineno=e.lineno or 1,
                status="skipped",
                details=f"SyntaxError: {e.msg}",
            )
        ]

    if not functions:
        return source_code, []

    # Detect line endings
    newline = "\r\n" if "\r\n" in source_code else "\n"
    lines = source_code.splitlines()
    reports: List[DocstringReport] = []

    # Sort functions in reverse order of line numbers so modifying later lines
    # doesn't invalidate line numbers of earlier functions
    sorted_functions = sorted(functions, key=lambda f: f.lineno, reverse=True)

    for func in sorted_functions:
        if func.has_docstring and not overwrite:
            reports.append(
                DocstringReport(
                    file_path=file_path,
                    function_name=func.name,
                    lineno=func.lineno,
                    status="skipped",
                    details="Existing docstring preserved (use --overwrite to replace)",
                )
            )
            continue

        # Determine indentation level
        # Use body_col_offset if available and greater than col_offset, else col_offset + 4
        if func.body_col_offset > func.col_offset:
            indent_size = func.body_col_offset
        else:
            indent_size = func.col_offset + 4

        new_docstring = generate_google_docstring(func, base_indent=indent_size)
        docstring_lines = new_docstring.split("\n")

        if func.has_docstring and overwrite:
            # Replace existing docstring lines
            start_idx = (func.docstring_lineno_start or func.body_lineno) - 1
            end_idx = func.docstring_lineno_end or func.body_lineno
            # Replace slice [start_idx : end_idx]
            lines[start_idx:end_idx] = docstring_lines
            reports.append(
                DocstringReport(
                    file_path=file_path,
                    function_name=func.name,
                    lineno=func.lineno,
                    status="updated",
                    details=f"Updated docstring for '{func.name}'",
                )
            )
        else:
            # Insert new docstring
            # Check if function is single-line (e.g., `def foo(): pass`)
            if func.body_lineno == func.lineno:
                # Need to split single line definition into multi-line
                target_line = lines[func.lineno - 1]
                colon_idx = target_line.find(":")
                if colon_idx != -1:
                    def_part = target_line[: colon_idx + 1]
                    body_part = target_line[colon_idx + 1 :].strip()
                    body_indent = " " * indent_size
                    new_block = [def_part] + docstring_lines + [f"{body_indent}{body_part}"]
                    lines[func.lineno - 1 : func.lineno] = new_block
                else:
                    lines.insert(func.lineno, "\n".join(docstring_lines))
            else:
                # Multi-line or normal function: insert before first statement in body
                insert_idx = func.body_lineno - 1
                lines[insert_idx:insert_idx] = docstring_lines

            reports.append(
                DocstringReport(
                    file_path=file_path,
                    function_name=func.name,
                    lineno=func.lineno,
                    status="generated",
                    details=f"Generated Google-style docstring for '{func.name}'",
                )
            )

    # Reconstruct modified source code preserving trailing newline if original had one
    has_trailing_newline = source_code.endswith("\n") or source_code.endswith("\r\n")
    modified_code = newline.join(lines)
    if has_trailing_newline and not modified_code.endswith(newline):
        modified_code += newline

    # Reorder reports in natural top-to-bottom line order
    reports.sort(key=lambda r: r.lineno)
    return modified_code, reports


def process_file(
    file_path: Path | str,
    in_place: bool = False,
    overwrite: bool = False,
) -> Tuple[str, List[DocstringReport]]:
    """Process a single Python file to generate/update docstrings.

    Args:
        file_path (Path | str): Path to the target Python file.
        in_place (bool): If True, writes changes directly back to the file.
        overwrite (bool): If True, replaces existing docstrings.

    Returns:
        Tuple[str, List[DocstringReport]]: The processed source code and report list.

    Raises:
        FileNotFoundError: If the file does not exist.
        UnicodeDecodeError: If the file encoding is not supported.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Target file not found: {path}")

    source_code = path.read_text(encoding="utf-8")
    modified_code, reports = process_python_source(
        source_code=source_code,
        overwrite=overwrite,
        file_path=str(path),
    )

    if in_place and modified_code != source_code:
        path.write_text(modified_code, encoding="utf-8")

    return modified_code, reports


def generate_diff(original: str, modified: str, file_path: str = "file.py") -> str:
    """Generate a unified diff between original and modified source code.

    Args:
        original (str): Original source code.
        modified (str): Modified source code.
        file_path (str): File name for diff header.

    Returns:
        str: Unified diff string.
    """
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)
