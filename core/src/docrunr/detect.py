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
_TEXTUAL_MIMES = {
    "text/html",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
}


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

_KNOWN_DOC_MIMES = frozenset(_EXT_TO_MIME.values()) | frozenset(_MAGIKA_LABEL_TO_MIME.values())
# Trust Magika over a .html/.htm suffix only for binary/document types (PDF, Office, images, mail).
_HTML_TRUST_MAGIKA_MIMES = _KNOWN_DOC_MIMES - _TEXTUAL_MIMES


def _prefer_html_extension(detected_mime: str, ext: str, ext_mime: str | None) -> bool:
    """Magika often mislabels HTML as txt, erb/ruby, php, or other source types."""
    return (
        ext in _HTML_EXTENSIONS
        and ext_mime == "text/html"
        and detected_mime != "text/html"
        and detected_mime not in _HTML_TRUST_MAGIKA_MIMES
    )


def _resolve_detected_mime(
    detected_mime: str, ext: str, ext_mime: str | None, *, path_name: str
) -> str:
    if _prefer_html_extension(detected_mime, ext, ext_mime):
        log.debug(
            "Preferring extension MIME for HTML: %s magika=%s ext=%s",
            path_name,
            detected_mime,
            ext,
        )
        return ext_mime or detected_mime
    if ext_mime and detected_mime not in _KNOWN_DOC_MIMES:
        log.debug(
            "Magika MIME %s is not a known type for %s; using extension %s",
            detected_mime,
            path_name,
            ext_mime,
        )
        return ext_mime
    return detected_mime


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
            chosen = _resolve_detected_mime(mime, ext, ext_mime, path_name=path.name)
            log.debug("Magika detected %s as %s (label=%s)", path.name, chosen, label)
            return chosen
        if result.output.mime_type and result.output.mime_type != "application/octet-stream":
            raw_mime = str(result.output.mime_type)
            chosen = _resolve_detected_mime(raw_mime, ext, ext_mime, path_name=path.name)
            log.debug("Magika MIME fallback: %s → %s", path.name, chosen)
            return chosen
    except Exception:
        log.debug("Magika detection failed for %s, falling back to extension", path.name)

    if ext_mime:
        log.debug("Extension fallback: %s → %s", path.name, ext_mime)
    return ext_mime
