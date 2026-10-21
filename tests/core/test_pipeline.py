"""Tests for the pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from docrunr.parsers._converters import _find_tessdata_dir
from docrunr.pipeline import process_file
from PIL import Image

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


def _tessdata_ready() -> bool:
    root = _find_tessdata_dir()
    return root is not None and (root / "nld.traineddata").is_file()


_SKIP_NO_TESSDATA = pytest.mark.skipif(
    not _tessdata_ready(),
    reason="Tesseract tessdata (eng+nld) is not installed",
)


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

    def test_erb_like_html_is_processed_as_html(self, tmp_path: Path) -> None:
        f = tmp_path / "templated.html"
        f.write_text(
            "<!DOCTYPE html>\n"
            "<html><body>\n"
            "<% if user %><h1>Hello visitor</h1><% end %>\n"
            "<p>A paragraph of document content for extraction.</p>\n"
            "</body></html>\n",
            encoding="utf-8",
        )
        result = process_file(f)
        assert result.ok, result.error
        assert result.mime_type == "text/html"
        assert result.parser in ("BeautifulSoupHtmlParser", "MarkItDownHtmlParser")
        assert "Hello visitor" in result.markdown
        assert "document content" in result.markdown

    def test_image_falls_back_to_docling_when_tesseract_fails(self, tmp_path: Path) -> None:
        sample = tmp_path / "shot.png"
        Image.new("RGB", (64, 48), "white").save(sample)
        fallback = (
            "# Fallback screenshot\n\n"
            "Docling recovered this screenshot text after Tesseract failed to run.\n"
        )

        with (
            patch(
                "docrunr.parsers._converters.parse_image_with_tesseract",
                side_effect=RuntimeError("tesseract unavailable"),
            ),
            patch(
                "docrunr.parsers._converters.parse_with_docling",
                return_value=fallback,
            ),
        ):
            result = process_file(sample)

        assert result.ok, result.error
        assert result.mime_type == "image/png"
        assert result.parser == "DoclingImageParser"
        assert "Docling recovered this screenshot" in result.markdown

    @_SKIP_NO_TESSDATA
    def test_dutch_ui_screenshot_uses_tesseract(self) -> None:
        sample = SAMPLES_DIR / "image" / "ui_screenshot_nl.png"
        result = process_file(sample)
        assert result.ok, result.error
        assert result.mime_type == "image/png"
        assert result.parser == "TesseractImageParser"
        markdown = result.markdown.lower()
        assert "aanmelden" in markdown
        assert "wachtwoord" in markdown
        assert "succesvol" in markdown
        lines = [line.strip() for line in result.markdown.splitlines() if line.strip()]
        assert len(lines) >= 3

    @_SKIP_NO_TESSDATA
    def test_english_ui_screenshot_uses_tesseract(self) -> None:
        sample = SAMPLES_DIR / "image" / "ui_screenshot_en.png"
        result = process_file(sample)
        assert result.ok, result.error
        assert result.mime_type == "image/png"
        assert result.parser == "TesseractImageParser"
        markdown = result.markdown.lower()
        assert "sign in" in markdown
        assert "password" in markdown
        lines = [line.strip() for line in result.markdown.splitlines() if line.strip()]
        assert len(lines) >= 3

    @_SKIP_NO_TESSDATA
    def test_receipt_jpeg_uses_tesseract(self) -> None:
        sample = SAMPLES_DIR / "image" / "receipt_scan.jpg"
        result = process_file(sample)
        assert result.ok, result.error
        assert result.mime_type == "image/jpeg"
        assert result.parser == "TesseractImageParser"
        markdown = result.markdown.lower()
        assert "espresso" in markdown
        assert "croissant" in markdown
        lines = [line.strip() for line in result.markdown.splitlines() if line.strip()]
        assert len(lines) >= 3
