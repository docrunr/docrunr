"""File type detection using Magika."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_EXT_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".eml": "message/rfc822",
    ".msg": "application/vnd.ms-outlook",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
}

_magika_instance: Any = None
_HTML_EXTENSIONS = {".html", ".htm"}


def _get_magika() -> Any:
    global _magika_instance  # noqa: PLW0603
    if _magika_instance is None:
        from magika import Magika

        _magika_instance = Magika()
    return _magika_instance


_MAGIKA_LABEL_TO_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "html": "text/html",
    "txt": "text/plain",
    "markdown": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
    "xml": "application/xml",
    "email": "message/rfc822",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
}


def detect_mime(path: Path) -> str | None:
    """Detect MIME type of a file. Returns None if unrecognized."""
    ext = path.suffix.lower()
    ext_mime = _EXT_TO_MIME.get(ext)

    try:
        magika = _get_magika()
        result = magika.identify_path(path)
        label = result.output.label
        mime = _MAGIKA_LABEL_TO_MIME.get(label)
        if mime:
            if mime == "text/plain" and ext in _HTML_EXTENSIONS and ext_mime == "text/html":
                log.debug(
                    "Preferring extension MIME for HTML: %s label=%s ext=%s",
                    path.name,
                    label,
                    ext,
                )
                return ext_mime
            log.debug("Magika detected %s as %s (label=%s)", path.name, mime, label)
            return mime
        if result.output.mime_type and result.output.mime_type != "application/octet-stream":
            raw_mime = str(result.output.mime_type)
            if raw_mime == "text/plain" and ext in _HTML_EXTENSIONS and ext_mime == "text/html":
                log.debug(
                    "Preferring extension MIME for HTML: %s mime=%s ext=%s",
                    path.name,
                    raw_mime,
                    ext,
                )
                return ext_mime
            log.debug("Magika MIME fallback: %s → %s", path.name, result.output.mime_type)
            return raw_mime
    except Exception:
        log.debug("Magika detection failed for %s, falling back to extension", path.name)

    if ext_mime:
        log.debug("Extension fallback: %s → %s", path.name, ext_mime)
    return ext_mime
