"""DocRunr — document to clean Markdown and chunks."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .models import Chunk, Result

__all__ = ["Chunk", "Result", "convert"]
try:
    __version__ = version("docrunr")
except PackageNotFoundError:
    __version__ = "0.0.0"


def convert(input_path: str | Path) -> Result:
    """Convert a document to clean Markdown and chunks.

    This is the public Python API. Same behavior as the CLI.
    """
    from . import parsers  # noqa: F401 — triggers registration
    from .pipeline import process_file

    return process_file(Path(input_path))
