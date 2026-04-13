"""Office document parsers — DOCX, DOC, PPTX/PPT, XLSX, XLS, ODF."""

from __future__ import annotations

from pathlib import Path

from .base import BaseParser
from .registry import register_parser

_OFFICE_MIMES = [
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/msword",  # doc
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",  # ppt
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",  # xls
    "application/vnd.oasis.opendocument.text",  # odt
    "application/vnd.oasis.opendocument.spreadsheet",  # ods
    "application/vnd.oasis.opendocument.presentation",  # odp
]

_KREUZBERG_MIMES = [
    "application/msword",  # doc
    "application/vnd.ms-excel",  # xls
    "application/vnd.ms-powerpoint",  # ppt
    "application/vnd.oasis.opendocument.text",  # odt
    "application/vnd.oasis.opendocument.spreadsheet",  # ods
    "application/vnd.oasis.opendocument.presentation",  # odp
]


@register_parser(mime_types=_KREUZBERG_MIMES, priority=5)
class KreuzbergOfficeParser(BaseParser):
    """Targeted Office extraction via Kreuzberg (legacy + ODT)."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_kreuzberg

        return parse_with_kreuzberg(path)


@register_parser(mime_types=_OFFICE_MIMES, priority=20)
class DoclingOfficeParser(BaseParser):
    """Office extraction via Docling (fallback)."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_docling

        return parse_with_docling(path)


@register_parser(mime_types=_OFFICE_MIMES, priority=10)
class MarkItDownOfficeParser(BaseParser):
    """Office extraction via MarkItDown (primary for non-targeted Office types)."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_markitdown

        return parse_with_markitdown(path)
