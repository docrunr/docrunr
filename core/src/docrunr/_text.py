"""Shared text normalization helpers."""

from __future__ import annotations

import re


def normalize_for_comparison(text: str) -> str:
    """Collapse whitespace for stable comparison and hashing."""
    return re.sub(r"\s+", " ", text).strip()
