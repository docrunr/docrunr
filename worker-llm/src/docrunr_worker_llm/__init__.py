"""DocRunr Worker LLM — optional post-processing worker for embeddings and LLM-backed insights."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("docrunr-worker-llm")
except PackageNotFoundError:
    __version__ = "0.0.0"
