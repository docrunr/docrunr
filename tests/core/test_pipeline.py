"""Tests for the pipeline."""

from __future__ import annotations

from pathlib import Path

from docrunr.pipeline import process_file


class TestProcessFile:
    def test_nonexistent_file(self) -> None:
        result = process_file(Path("/nonexistent/file.pdf"))
        assert result.ok is False
        assert "not found" in (result.error or "").lower()

    def test_plain_text(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("# Hello World\n\nThis is a test document with some content.\n")
        result = process_file(f)
        assert result.ok
        assert "Hello World" in result.markdown
        assert len(result.chunks) >= 1
        assert result.content_hash.startswith("sha256:")
        assert result.total_tokens > 0
        assert result.mime_type in ("text/plain", "text/markdown")
        assert result.size_bytes > 0
        assert result.parser == "PlainTextParser"
        assert result.duration_seconds >= 0

    def test_markdown_passthrough(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nParagraph one.\n\n## Section\n\nParagraph two.\n")
        result = process_file(f)
        assert result.ok
        assert "Title" in result.markdown
        assert len(result.chunks) >= 1

    def test_csv_to_table(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("Name,Age,City\nAlice,30,Amsterdam\nBob,25,Berlin\n")
        result = process_file(f)
        assert result.ok
        assert "|" in result.markdown

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xyz123"
        f.write_bytes(b"\x00\x01\x02binary data")
        result = process_file(f)
        assert result.ok is False

    def test_html_sample_uses_html_parser_and_emits_markdown(self) -> None:
        sample = Path("tests/samples/html/government_page.html")
        result = process_file(sample)
        assert result.ok
        assert result.mime_type == "text/html"
        assert result.parser in ("BeautifulSoupHtmlParser", "MarkItDownHtmlParser")
        assert "<html" not in result.markdown.lower()
        assert "# Minuut want papier liggen dansen doen." in result.markdown
        assert "## Wat u moet weten" in result.markdown
        assert "Vraag: Begrijpen kost vertrekken." in result.markdown
        assert "Wolk kasteel vogel instrument." in result.markdown
