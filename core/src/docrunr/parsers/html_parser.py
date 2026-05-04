"""HTML parser — BeautifulSoup + MarkItDown."""

from __future__ import annotations

from pathlib import Path

from .base import BaseParser
from .registry import register_parser

HTML_MIME = "text/html"


@register_parser(mime_types=[HTML_MIME], priority=10)
class BeautifulSoupHtmlParser(BaseParser):
    """HTML extraction via BeautifulSoup — strips tags, preserves structure."""

    def parse(self, path: Path) -> str:
        from bs4 import BeautifulSoup

        html = path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        parts: list[str] = []
        for el in soup.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dt", "dd"]
        ):
            tag_name = el.name
            text = el.get_text(separator=" ", strip=True)
            if not text:
                continue
            if tag_name.startswith("h"):
                level = int(tag_name[1])
                parts.append(f"{'#' * level} {text}")
            elif tag_name == "li":
                parts.append(f"- {text}")
            elif tag_name == "dt":
                parts.append(f"**{text}**")
            else:
                parts.append(text)

        result = "\n\n".join(parts)

        if not result.strip():
            raise ValueError("BeautifulSoup extracted no content")
        return result


@register_parser(mime_types=[HTML_MIME], priority=20)
class MarkItDownHtmlParser(BaseParser):
    """HTML fallback via MarkItDown."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_markitdown

        return parse_with_markitdown(path)
