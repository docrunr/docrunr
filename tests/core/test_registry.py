"""Tests for parser registry."""

from __future__ import annotations

from docrunr.parsers.registry import get_parsers, supported_mime_types


class TestRegistry:
    def test_pdf_has_parsers(self) -> None:
        parsers = get_parsers("application/pdf")
        assert len(parsers) >= 1

    def test_html_has_parsers(self) -> None:
        parsers = get_parsers("text/html")
        assert len(parsers) >= 1

    def test_unknown_mime_empty(self) -> None:
        parsers = get_parsers("application/x-unknown-thing")
        assert parsers == []

    def test_supported_types_not_empty(self) -> None:
        types = supported_mime_types()
        assert len(types) > 5
        assert "application/pdf" in types
        assert "text/html" in types
        assert "text/plain" in types

    def test_legacy_office_prefers_kreuzberg(self) -> None:
        parsers = get_parsers("application/msword")
        names = [p.__class__.__name__ for p in parsers]
        assert names[0] == "KreuzbergOfficeParser"
        assert "MarkItDownOfficeParser" in names
        assert "DoclingOfficeParser" in names

    def test_odf_spreadsheet_prefers_kreuzberg(self) -> None:
        parsers = get_parsers("application/vnd.oasis.opendocument.spreadsheet")
        names = [p.__class__.__name__ for p in parsers]
        assert names[0] == "KreuzbergOfficeParser"

    def test_legacy_ppt_has_parsers(self) -> None:
        parsers = get_parsers("application/vnd.ms-powerpoint")
        assert len(parsers) >= 1
