"""Parser registry — decorator-based registration with priority ordering."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseParser

log = logging.getLogger(__name__)

_registry: dict[str, list[tuple[int, type[BaseParser]]]] = {}


def register_parser(
    mime_types: list[str], priority: int = 50
) -> Callable[[type[BaseParser]], type[BaseParser]]:
    """Register a parser class for the given MIME types.

    Lower priority number = tried first. If two parsers share a priority,
    the one registered first wins.
    """

    def decorator(cls: type[BaseParser]) -> type[BaseParser]:
        for mime in mime_types:
            entries = _registry.setdefault(mime, [])
            entries.append((priority, cls))
            entries.sort(key=lambda e: e[0])
        log.debug("Registered %s for %s (priority=%d)", cls.__name__, mime_types, priority)
        return cls

    return decorator


def get_parsers(mime_type: str) -> list[BaseParser]:
    """Return parser instances for a MIME type, ordered by priority."""
    entries = _registry.get(mime_type, [])
    return [cls() for _, cls in entries]


def supported_mime_types() -> list[str]:
    """All MIME types with at least one registered parser."""
    return sorted(_registry.keys())
