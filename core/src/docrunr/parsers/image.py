"""Image parser — OCR via Docling."""

from __future__ import annotations

from pathlib import Path

from .base import BaseParser
from .registry import register_parser

_IMAGE_MIMES = [
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
]


@register_parser(mime_types=_IMAGE_MIMES, priority=10)
class DoclingImageParser(BaseParser):
    """Image OCR via Docling."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_docling

        return parse_with_docling(path)
