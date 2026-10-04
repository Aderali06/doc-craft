"""CLI integration tests using Typer CliRunner."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typer.testing import CliRunner

from doc_craft.main import app

runner = CliRunner()


def test_cli_version() -> None:
    """Test the --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "doc-craft" in result.stdout
    assert "0.1.0" in result.stdout


def test_cli_preview_command() -> None:
    """Test preview command on a sample file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "math_ops.py"
        sample.write_text("def subtract(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8")

        result = runner.invoke(app, ["preview", str(sample)])
        assert result.exit_code == 0
        assert "Diff Preview" in result.stdout or "subtract" in result.stdout


def test_cli_generate_dry_run() -> None:
    """Test generate command in dry-run mode (without --in-place)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "user_service.py"
        sample.write_text("def find_user(id: int) -> str:\n    return 'Alice'\n", encoding="utf-8")

        result = runner.invoke(app, ["generate", str(sample)])
        assert result.exit_code == 0
        assert "PREVIEW MODE" in result.stdout
        assert "find_user" in result.stdout

        # Content on disk should be unchanged in dry-run
        assert '"""' not in sample.read_text(encoding="utf-8")


def test_cli_generate_in_place() -> None:
    """Test generate command with --in-place."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "helper.py"
        sample.write_text("def helper(val: str) -> None:\n    print(val)\n", encoding="utf-8")

        result = runner.invoke(app, ["generate", str(sample), "--in-place"])
        assert result.exit_code == 0
        assert "IN-PLACE WRITE" in result.stdout

        updated = sample.read_text(encoding="utf-8")
        assert '"""Helper.' in updated


def test_cli_check_mode_failure() -> None:
    """Test check mode returns exit code 1 when docstrings are missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "need_doc.py"
        sample.write_text("def task():\n    pass\n", encoding="utf-8")

        result = runner.invoke(app, ["generate", str(sample), "--check"])
        assert result.exit_code == 1
        assert "Check failed" in result.stdout or "Check failed" in result.stderr


def test_cli_check_mode_success() -> None:
    """Test check mode passes when all functions have docstrings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sample = Path(tmpdir) / "has_doc.py"
        sample.write_text('def task():\n    """Task description."""\n    pass\n', encoding="utf-8")

        result = runner.invoke(app, ["generate", str(sample), "--check"])
        assert result.exit_code == 0
