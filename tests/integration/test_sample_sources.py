"""Unit checks for integration sample source limiting behavior."""

from __future__ import annotations

from pathlib import Path

from tests.integration.fixtures import sample_sources


def _paths(n: int) -> list[Path]:
    return [Path(f"/tmp/sample_{i}.txt") for i in range(n)]


def test_take_limit_within_pool_returns_subset_without_replacement() -> None:
    paths = _paths(5)
    out = sample_sources.take_limit(paths, 3)
    assert out == paths[:3]


def test_take_limit_above_pool_repeats_random_picks(monkeypatch) -> None:
    paths = _paths(3)
    called: dict[str, object] = {}

    def _fake_choices(population: list[Path], *, k: int) -> list[Path]:
        called["population"] = population
        called["k"] = k
        return [population[1]] * k

    monkeypatch.setattr(sample_sources.random, "choices", _fake_choices)
    out = sample_sources.take_limit(paths, 8)
    assert called == {"population": paths, "k": 8}
    assert out == [paths[1]] * 8


def test_take_limit_with_empty_pool_returns_empty() -> None:
    assert sample_sources.take_limit([], 10) == []
