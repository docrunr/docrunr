"""PDF parsers — Docling (layout-aware), pypdfium2 (fast), MarkItDown (fallback)."""

from __future__ import annotations

from pathlib import Path

from .base import BaseParser
from .registry import register_parser

PDF_MIME = "application/pdf"


@register_parser(mime_types=[PDF_MIME], priority=10)
class DoclingPdfParser(BaseParser):
    """Layout-aware PDF extraction via Docling."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_docling

        return parse_with_docling(path)


@register_parser(mime_types=[PDF_MIME], priority=20)
class PypdfiumParser(BaseParser):
    """Fast PDF text extraction via pypdfium2."""

    def parse(self, path: Path) -> str:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        pages: list[str] = []
        for page in pdf:
            text = page.get_textpage().get_text_range()
            if text.strip():
                pages.append(text.strip())
        pdf.close()
        if not pages:
            raise ValueError("pypdfium2 extracted no text")
        return "\n\n".join(pages)


@register_parser(mime_types=[PDF_MIME], priority=30)
class MarkItDownPdfParser(BaseParser):
    """PDF fallback via MarkItDown."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_markitdown

        return parse_with_markitdown(path)
