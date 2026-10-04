"""Command Line Interface for doc-craft using Typer and Rich.

Provides automated scanning, docstring generation, in-place editing,
diff previews, and CI check modes for Python projects.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from doc_craft import __version__
from doc_craft.parser import (
    DocstringReport,
    generate_diff,
    process_file,
)

app = typer.Typer(
    name="doc-craft",
    help="doc-craft: Automated Google-style Python Docstring Generator using AST.",
    add_completion=False,
)
console = Console()
error_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold cyan]doc-craft[/bold cyan] version [bold green]{__version__}[/bold green]")
        raise typer.Exit()


def _find_python_files(path: Path, excludes: List[str]) -> List[Path]:
    """Find all Python files in the given path, respecting exclude patterns."""
    if path.is_file():
        return [path] if path.suffix == ".py" else []

    py_files: List[Path] = []
    default_excludes = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", "build", "dist"}
    all_excludes = default_excludes.union(set(excludes))

    for root, dirs, files in os.walk(path):
        # Prune excluded directories in-place
        dirs[:] = [d for d in dirs if d not in all_excludes and not any(e in d for e in excludes if e)]

        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                py_files.append(file_path)

    return sorted(py_files)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show application version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """doc-craft root command callback."""
    if ctx.invoked_subcommand is None:
        # If no subcommand is invoked, show help
        pass


@app.command("generate")
def generate(
    path: Path = typer.Argument(
        Path("."),
        help="Target Python file or directory to process.",
        exists=True,
        readable=True,
    ),
    in_place: bool = typer.Option(
        False,
        "--in-place",
        "-i",
        help="Write generated docstrings directly into the source files.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "-w",
        help="Overwrite existing docstrings instead of skipping them.",
    ),
    diff: bool = typer.Option(
        False,
        "--diff",
        "-d",
        help="Display unified diff preview of changes.",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        "-c",
        help="Check mode: Return exit code 1 if any file needs docstring additions (ideal for CI).",
    ),
    exclude: str = typer.Option(
        "",
        "--exclude",
        "-e",
        help="Comma-separated directories or patterns to exclude.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress informational messages, only output errors.",
    ),
) -> None:
    """Scan Python files and generate Google-style docstrings automatically."""
    exclude_list = [e.strip() for e in exclude.split(",") if e.strip()]
    py_files = _find_python_files(path, exclude_list)

    if not py_files:
        if not quiet:
            console.print("[yellow]No Python files found matching the criteria.[/yellow]")
        return

    total_files = len(py_files)
    total_generated = 0
    total_updated = 0
    total_skipped = 0
    modified_files_count = 0

    all_reports: List[DocstringReport] = []

    for file_path in py_files:
        try:
            original_code = file_path.read_text(encoding="utf-8")
            modified_code, reports = process_file(
                file_path=file_path,
                in_place=in_place and not check,
                overwrite=overwrite,
            )
            all_reports.extend(reports)

            is_modified = original_code != modified_code
            if is_modified:
                modified_files_count += 1

            if diff and is_modified and not quiet:
                diff_text = generate_diff(original_code, modified_code, file_path=str(file_path))
                console.print(Panel(
                    Syntax(diff_text, "diff", theme="monokai", line_numbers=False),
                    title=f"[bold cyan]{file_path}[/bold cyan]",
                    border_style="cyan",
                ))

            for rep in reports:
                if rep.status == "generated":
                    total_generated += 1
                elif rep.status == "updated":
                    total_updated += 1
                elif rep.status == "skipped":
                    total_skipped += 1

        except Exception as err:
            error_console.print(f"[bold red]Error processing {file_path}:[/bold red] {err}")

    if not quiet:
        # Results table
        table = Table(title="[bold green]doc-craft Execution Summary[/bold green]", border_style="dim")
        table.add_column("File", style="cyan")
        table.add_column("Function", style="white")
        table.add_column("Line", justify="right", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Details", style="dim")

        for rep in all_reports:
            status_style = {
                "generated": "[bold green]GENERATED[/bold green]",
                "updated": "[bold yellow]UPDATED[/bold yellow]",
                "skipped": "[bold blue]SKIPPED[/bold blue]",
            }.get(rep.status, rep.status)

            table.add_row(
                Path(rep.file_path).name,
                rep.function_name,
                str(rep.lineno),
                status_style,
                rep.details,
            )

        if all_reports:
            console.print(table)
            console.print()

        mode_desc = "[bold red]CHECK MODE[/bold red]" if check else ("[bold green]IN-PLACE WRITE[/bold green]" if in_place else "[bold yellow]PREVIEW MODE (dry-run)[/bold yellow]")
        summary_panel = Panel(
            f"Mode: {mode_desc}\n"
            f"Files scanned: [bold cyan]{total_files}[/bold cyan]\n"
            f"Files with changes: [bold magenta]{modified_files_count}[/bold magenta]\n"
            f"Docstrings generated: [bold green]{total_generated}[/bold green]\n"
            f"Docstrings updated: [bold yellow]{total_updated}[/bold yellow]\n"
            f"Functions skipped: [bold blue]{total_skipped}[/bold blue]",
            title="[bold]Summary[/bold]",
            border_style="green" if modified_files_count == 0 or in_place else "yellow",
        )
        console.print(summary_panel)

    if check and modified_files_count > 0:
        if not quiet:
            error_console.print(
                f"[bold red]Check failed:[/bold red] {modified_files_count} file(s) require docstrings. "
                f"Run with [bold cyan]doc-craft generate {path} --in-place[/bold cyan] to apply changes."
            )
        raise typer.Exit(code=1)


@app.command("preview")
def preview(
    path: Path = typer.Argument(
        ...,
        help="Target Python file to preview docstring generation.",
        exists=True,
        readable=True,
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        "-w",
        help="Overwrite existing docstrings in preview.",
    ),
) -> None:
    """Preview the generated docstrings and diff for a single file directly."""
    if not path.is_file():
        error_console.print(f"[bold red]Error:[/bold red] '{path}' is not a file. Preview requires a single file.")
        raise typer.Exit(code=1)

    original_code = path.read_text(encoding="utf-8")
    modified_code, reports = process_file(file_path=path, in_place=False, overwrite=overwrite)

    if original_code == modified_code:
        console.print(f"[green]All functions in '{path.name}' already have docstrings. No changes needed.[/green]")
        return

    diff_text = generate_diff(original_code, modified_code, file_path=str(path))
    console.print(Panel(
        Syntax(diff_text, "diff", theme="monokai", line_numbers=False),
        title=f"[bold green]Diff Preview: {path.name}[/bold green]",
        border_style="green",
    ))


if __name__ == "__main__":
    app()
