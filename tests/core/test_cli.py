"""Tests for the CLI."""

from __future__ import annotations

from pathlib import Path

from docrunr.cli import app
from typer.testing import CliRunner

runner = CliRunner()


class TestCli:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "docrunr" in result.output.lower() or "document" in result.output.lower()

    def test_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("# Hello\n\nWorld.\n")
        out = tmp_path / "out"

        result = runner.invoke(app, [str(f), "--out", str(out)])
        assert result.exit_code == 0
        assert (out / "test.md").exists()
        assert (out / "test.json").exists()

    def test_directory(self, tmp_path: Path) -> None:
        for name in ["a.txt", "b.txt"]:
            (tmp_path / name).write_text(f"# {name}\n\nContent.\n")
        out = tmp_path / "out"

        result = runner.invoke(app, [str(tmp_path), "--out", str(out)])
        assert result.exit_code == 0
        assert (out / "a.md").exists()
        assert (out / "b.md").exists()

    def test_report_flag(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("# Hello\n\nWorld.\n")
        out = tmp_path / "out"

        result = runner.invoke(app, [str(f), "--out", str(out), "--report"])
        assert result.exit_code == 0
        assert (out / "_report.json").exists()

    def test_verbose(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("# Hello\n\nWorld.\n")
        out = tmp_path / "out"

        result = runner.invoke(app, [str(f), "--out", str(out), "--verbose"])
        assert result.exit_code == 0
        assert "chunks" in result.output.lower() or "tokens" in result.output.lower()

    def test_nonexistent_path(self) -> None:
        result = runner.invoke(app, ["/nonexistent/path"])
        assert result.exit_code != 0
