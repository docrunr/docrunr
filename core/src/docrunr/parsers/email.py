"""Email parser — .eml and .msg files."""

from __future__ import annotations

import email
from email import policy
from email.message import EmailMessage
from pathlib import Path

from .base import BaseParser
from .registry import register_parser


@register_parser(mime_types=["message/rfc822"], priority=10)
class EmlParser(BaseParser):
    """Parse .eml files using Python's email module."""

    def parse(self, path: Path) -> str:
        raw = path.read_bytes()
        msg = email.message_from_bytes(raw, policy=policy.default)

        parts: list[str] = []

        subject = msg.get("Subject", "")
        from_addr = msg.get("From", "")
        to_addr = msg.get("To", "")
        date = msg.get("Date", "")

        if subject:
            parts.append(f"# {subject}")
        meta: list[str] = []
        if from_addr:
            meta.append(f"**From:** {from_addr}")
        if to_addr:
            meta.append(f"**To:** {to_addr}")
        if date:
            meta.append(f"**Date:** {date}")
        if meta:
            parts.append("\n".join(meta))

        body = self._get_body(msg)
        if body:
            parts.append(body)

        result = "\n\n".join(parts)
        if not result.strip():
            raise ValueError("Email has no extractable content")
        return result

    def _get_body(self, msg: EmailMessage) -> str:
        if msg.is_multipart():
            text_parts: list[str] = []
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_content()
                    if isinstance(payload, str) and payload.strip():
                        text_parts.append(payload.strip())
            return "\n\n".join(text_parts)
        else:
            payload = msg.get_content()
            if isinstance(payload, str):
                return payload.strip()
            return ""


@register_parser(mime_types=["application/vnd.ms-outlook"], priority=10)
class MsgParser(BaseParser):
    """Parse .msg files via MarkItDown."""

    def parse(self, path: Path) -> str:
        from ._converters import parse_with_markitdown

        return parse_with_markitdown(path)
