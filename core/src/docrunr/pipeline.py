"""Pipeline — orchestrates detect → parse → clean → chunk → output."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from . import chunk, clean, detect, quality
from .models import Result
from .parsers.base import BaseParser
from .parsers.registry import get_parsers

log = logging.getLogger(__name__)


def process_file(path: Path) -> Result:
    """Process a single file through the full pipeline.

    Returns a Result — always succeeds (errors are captured, never raised).
    """
    source = path.name
    try:
        return _process(path)
    except Exception as exc:
        log.error("Failed to process %s: %s", source, exc)
        return Result(source=source, error=str(exc))


def _process(path: Path) -> Result:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    size_bytes = path.stat().st_size

    mime = detect.detect_mime(path)
    if mime is None:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    parsers = get_parsers(mime)
    if not parsers:
        raise ValueError(f"No parser for MIME type: {mime}")

    log.info("Processing %s (%s, %d parser(s))", path.name, mime, len(parsers))

    t0 = time.monotonic()
    markdown, parser_name = _extract_with_fallback(path, parsers)
    markdown = clean.clean_markdown(markdown)
    duration = time.monotonic() - t0

    chunks = chunk.chunk_markdown(
        markdown,
        source_doc_id=chunk.derive_source_doc_id(path.name),
    )

    result = Result(
        source=path.name,
        markdown=markdown,
        chunks=chunks,
        mime_type=mime,
        size_bytes=size_bytes,
        parser=parser_name,
        duration_seconds=duration,
    )
    result.compute_hash()
    result.compute_totals()
    return result


def _extract_with_fallback(path: Path, parsers: list[BaseParser]) -> tuple[str, str]:
    """Try parsers in priority order. Return (markdown, parser_name)."""
    best_text = ""
    best_score = -1.0
    best_name = ""

    for parser in parsers:
        name = parser.__class__.__name__
        try:
            log.debug("Trying %s for %s", name, path.name)
            text = parser.parse(path)
            sc = quality.score(text)
            log.debug("%s scored %.2f for %s", name, sc, path.name)

            if sc >= quality.THRESHOLD:
                log.info("Using %s for %s (score=%.2f)", name, path.name, sc)
                return text, name

            if sc > best_score:
                best_text = text
                best_score = sc
                best_name = name

        except Exception as exc:
            log.debug("%s failed for %s: %s", name, path.name, exc)
            continue

    if best_text:
        log.warning(
            "All parsers scored below threshold for %s, using best (score=%.2f)",
            path.name,
            best_score,
        )
        return best_text, best_name

    raise ValueError(f"All parsers failed for {path.name}")
