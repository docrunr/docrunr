"""Text-based parsers — plain text, Markdown, CSV, JSON, XML."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from xml.etree import ElementTree

from .base import BaseParser
from .registry import register_parser


@register_parser(
    mime_types=["text/plain", "text/markdown", "text/x-rst"],
    priority=10,
)
class PlainTextParser(BaseParser):
    """Direct file read for plain text and Markdown."""

    def parse(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise ValueError("File is empty")
        return text


@register_parser(mime_types=["text/csv"], priority=10)
class CsvParser(BaseParser):
    """Convert CSV to a Markdown table."""

    def parse(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV is empty")

        header = rows[0]
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        for row in rows[1:]:
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[: len(header)]) + " |")

        return "\n".join(lines)


@register_parser(mime_types=["application/json"], priority=10)
class JsonParser(BaseParser):
    """Render JSON as a fenced code block."""

    def parse(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return f"```json\n{formatted}\n```"


@register_parser(mime_types=["application/xml"], priority=10)
class XmlParser(BaseParser):
    """Extract text content from XML."""

    def parse(self, path: Path) -> str:
        tree = ElementTree.parse(path)  # noqa: S314
        root = tree.getroot()
        parts: list[str] = []
        self._walk(root, parts)
        if not parts:
            raise ValueError("XML contains no text")
        return "\n\n".join(parts)

    def _walk(self, el: ElementTree.Element, parts: list[str], depth: int = 0) -> None:
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        text = (el.text or "").strip()
        if text:
            if depth <= 1:
                parts.append(f"**{tag}:** {text}")
            else:
                parts.append(text)
        for child in el:
            self._walk(child, parts, depth + 1)
