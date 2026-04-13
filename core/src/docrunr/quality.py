"""Quality gate — fast heuristics to score extraction output."""

from __future__ import annotations

import re

THRESHOLD = 0.3


def score(text: str) -> float:
    """Score extracted text from 0.0 (garbage) to 1.0 (clean).

    Checks: length, printable ratio, whitespace density, repetition.
    """
    if not text or not text.strip():
        return 0.0

    scores: list[float] = []

    length = len(text.strip())
    scores.append(min(length / 200, 1.0))

    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    scores.append(printable / len(text) if text else 0.0)

    whitespace = text.count(" ") + text.count("\n") + text.count("\t")
    ws_ratio = whitespace / len(text) if text else 0.0
    if 0.1 <= ws_ratio <= 0.5:
        scores.append(1.0)
    elif ws_ratio < 0.05 or ws_ratio > 0.8:
        scores.append(0.2)
    else:
        scores.append(0.6)

    words = text.split()
    if len(words) > 10:
        unique_ratio = len(set(words)) / len(words)
        scores.append(unique_ratio)
    else:
        scores.append(0.3)

    has_structure = bool(re.search(r"^#{1,6}\s", text, re.MULTILINE))
    if has_structure:
        scores.append(1.0)
    else:
        scores.append(0.5)

    return sum(scores) / len(scores)


def passes(text: str) -> bool:
    return score(text) >= THRESHOLD
