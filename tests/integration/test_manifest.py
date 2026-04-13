"""Fast checks: sample manifest resolves without RabbitMQ or docker."""

from __future__ import annotations

from pathlib import Path


def test_resolved_integration_samples_non_empty(resolved_integration_samples: list[Path]) -> None:
    assert resolved_integration_samples, (
        "No sample paths resolved; check tests/integration/fixtures/sample_sources.py "
        "and selected source path (tests/samples/ or .data/downloads/)"
    )


def test_resolved_paths_exist(resolved_integration_samples: list[Path]) -> None:
    for p in resolved_integration_samples:
        assert p.is_file(), f"Missing sample file: {p}"
