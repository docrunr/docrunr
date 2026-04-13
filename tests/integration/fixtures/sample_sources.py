"""Resolve paths for integration runs from tests/samples or .data/downloads.

Sample source can be selected via ``INTEGRATION_SAMPLE_SOURCE`` or
``--integration-sample-source``:

- ``samples`` => ``tests/samples/**/*``
- ``downloads`` => ``.data/downloads/**/*``

After globbing, the pool is **shuffled** (random order each run), then ``take_limit`` applies:
- if *N* <= pool size: first *N* items (random subset without replacement),
- if *N* > pool size: *N* random picks from the pool (with replacement).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Literal

IntegrationSampleSource = Literal["samples", "downloads"]

_DEFAULT_SOURCE: IntegrationSampleSource = "samples"

# Globbed relative to the repository root.
_GLOB_PATTERNS_BY_SOURCE: dict[IntegrationSampleSource, tuple[str, ...]] = {
    "samples": ("tests/samples/**/*",),
    "downloads": (".data/downloads/**/*",),
}


def resolve_sample_source(raw: str | None) -> IntegrationSampleSource:
    source = (raw or _DEFAULT_SOURCE).strip().lower()
    if source == "samples":
        return "samples"
    if source == "downloads":
        return "downloads"
    valid = ", ".join(sorted(_GLOB_PATTERNS_BY_SOURCE.keys()))
    raise ValueError(f"Invalid integration sample source '{raw}'. Expected one of: {valid}.")


def glob_patterns_for_source(source: IntegrationSampleSource) -> tuple[str, ...]:
    return _GLOB_PATTERNS_BY_SOURCE[source]


def _is_skippable_file(path: Path) -> bool:
    name = path.name
    return name.startswith(".") or name == ".DS_Store"


def iter_sample_files(
    repo_root: Path,
    *,
    source: IntegrationSampleSource = _DEFAULT_SOURCE,
) -> list[Path]:
    """Unique files matching source glob patterns, then shuffled in random order."""
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in glob_patterns_for_source(source):
        for p in repo_root.glob(pattern):
            if not p.is_file() or _is_skippable_file(p):
                continue
            resolved = p.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            out.append(resolved)
    random.shuffle(out)
    return out


def take_limit(paths: list[Path], limit: int | None) -> list[Path]:
    if limit is None or limit < 0:
        return paths
    if limit <= len(paths):
        return paths[:limit]
    if not paths:
        return []
    return random.choices(paths, k=limit)


def repeat_to_count(paths: list[Path], count: int) -> list[Path]:
    """Cycle through paths until `count` entries (for stress-style runs)."""
    if not paths or count <= 0:
        return []
    out: list[Path] = []
    i = 0
    while len(out) < count:
        out.append(paths[i % len(paths)])
        i += 1
    return out
