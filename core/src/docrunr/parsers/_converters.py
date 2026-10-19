"""Cached converter instances and shared parse helpers.

Avoids re-initializing heavy ML models per file and centralizes the
convert-then-validate logic that every Docling / MarkItDown parser needs.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

_docling_converter: Any = None
_markitdown_converter: Any = None

_TESSDATA_CANDIDATES = (
    Path("/usr/share/tesseract-ocr/5/tessdata"),
    Path("/usr/share/tesseract-ocr/4.00/tessdata"),
    Path("/opt/homebrew/share/tessdata"),
    Path("/opt/homebrew/opt/tesseract/share/tessdata"),
    Path("/usr/local/share/tessdata"),
)
_OCR_MIN_LONG_SIDE = 1000
_OCR_MIN_HEIGHT = 300
_OCR_MAX_LONG_SIDE = 2000
_OCR_UPSCALE = 2.0


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


def _ensure_tessdata_prefix() -> str | None:
    """Point Kreuzberg's bundled libtesseract at system traineddata when unset."""
    existing = os.environ.get("TESSDATA_PREFIX")
    if existing:
        return existing
    for candidate in _TESSDATA_CANDIDATES:
        if candidate.is_dir() and (candidate / "eng.traineddata").is_file():
            resolved = str(candidate)
            os.environ["TESSDATA_PREFIX"] = resolved
            return resolved
    return None


def _select_tesseract_language(prefix: str | None) -> str:
    """Use eng+nld when Dutch traineddata is installed, else fall back to eng."""
    if prefix is not None:
        root = Path(prefix)
        if (root / "eng.traineddata").is_file() and not (root / "nld.traineddata").is_file():
            return "eng"
    return "eng+nld"


def _flatten_alpha_on_white(img: Any) -> Any:
    from PIL import Image

    if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background
    return img


def preprocess_image_for_ocr(path: Path) -> bytes:
    """Normalize an image for Tesseract: EXIF, white flatten, grayscale, optional 2x."""
    from PIL import Image, ImageOps

    with Image.open(path) as src:
        img = ImageOps.exif_transpose(src)
        if img is src:
            img = src.copy()

    img = _flatten_alpha_on_white(img)
    img = img.convert("L")

    width, height = img.size
    long_side = max(width, height)
    if long_side > 0 and (long_side < _OCR_MIN_LONG_SIDE or height < _OCR_MIN_HEIGHT):
        scale = min(_OCR_UPSCALE, _OCR_MAX_LONG_SIDE / long_side)
        if scale > 1.0:
            img = img.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def parse_image_with_tesseract(path: Path) -> str:
    """OCR an image via Kreuzberg/Tesseract. Raises on empty output."""
    from kreuzberg import ExtractionConfig, OcrConfig, extract_bytes_sync

    prefix = _ensure_tessdata_prefix()
    language = _select_tesseract_language(prefix)
    png_bytes = preprocess_image_for_ocr(path)
    config = ExtractionConfig(
        output_format="markdown",
        ocr=OcrConfig(backend="tesseract", language=language),
    )
    result = extract_bytes_sync(png_bytes, "image/png", config=config)
    text: str = result.content
    if not text or not text.strip():
        raise ValueError("Tesseract OCR returned empty content")
    return text
