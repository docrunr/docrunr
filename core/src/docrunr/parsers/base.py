"""Base parser protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    """Contract: takes a path, returns Markdown, raises on failure."""

    @abstractmethod
    def parse(self, path: Path) -> str:
        """Extract document content as Markdown.

        Returns a Markdown string. Raises any exception on failure.
        """
