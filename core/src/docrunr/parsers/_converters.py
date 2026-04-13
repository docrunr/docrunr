"""Cached converter instances and shared parse helpers.

Avoids re-initializing heavy ML models per file and centralizes the
convert-then-validate logic that every Docling / MarkItDown parser needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_docling_converter: Any = None
_markitdown_converter: Any = None


def get_docling_converter() -> Any:
    global _docling_converter  # noqa: PLW0603
    if _docling_converter is None:
        from docling.document_converter import DocumentConverter

        _docling_converter = DocumentConverter()
    return _docling_converter


def get_markitdown_converter() -> Any:
    global _markitdown_converter  # noqa: PLW0603
    if _markitdown_converter is None:
        from markitdown import MarkItDown

        _markitdown_converter = MarkItDown()
    return _markitdown_converter


def parse_with_docling(path: Path) -> str:
    """Convert a file via Docling and return Markdown. Raises on empty output."""
    converter = get_docling_converter()
    result = converter.convert(str(path))
    md: str = result.document.export_to_markdown()
    if not md or not md.strip():
        raise ValueError("Docling returned empty content")
    return md


def parse_with_markitdown(path: Path) -> str:
    """Convert a file via MarkItDown and return text. Raises on empty output."""
    converter = get_markitdown_converter()
    result = converter.convert(str(path))
    text: str = result.text_content
    if not text or not text.strip():
        raise ValueError("MarkItDown returned empty content")
    return text


def parse_with_kreuzberg(path: Path, mime_type: str | None = None) -> str:
    """Convert via Kreuzberg, requesting markdown output when supported."""
    from kreuzberg import ExtractionConfig, extract_file_sync

    try:
        config = ExtractionConfig(output_format="markdown")
    except TypeError:
        # Backward compatibility with older Kreuzberg releases.
        config = ExtractionConfig()
    result = extract_file_sync(str(path), mime_type, config=config)
    text: str = result.content
    if not text or not text.strip():
        raise ValueError("Kreuzberg returned empty content")
    return text
