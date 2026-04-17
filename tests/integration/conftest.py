"""Integration test configuration: sample corpus and fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.integration.fixtures import (
    fetch_litellm_profiles_from_env,
    resolve_llm_profile_from_env,
    resolve_llm_profile_pool_from_env,
)
from tests.integration.fixtures.sample_sources import (
    iter_sample_files,
    repeat_to_count,
    resolve_sample_source,
    take_limit,
)
from tests.integration.integration_storage import (
    IntegrationStorage,
    integration_storage_from_env,
)


def _opt_int(config: pytest.Config, name: str, env_var: str) -> int | None:
    opt = config.getoption(name)
    if opt is not None:
        return int(opt)
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return None
    return int(raw)


def _resolve_limited_paths(
    request: pytest.FixtureRequest,
    paths: list[Path],
) -> list[Path]:
    repeat_to = _opt_int(request.config, "--integration-repeat-to", "INTEGRATION_REPEAT_TO")
    limit = _opt_int(request.config, "--integration-sample-limit", "INTEGRATION_SAMPLE_LIMIT")

    if repeat_to is not None and repeat_to > 0:
        base = take_limit(paths, limit)
        return repeat_to_count(base, repeat_to)

    return take_limit(paths, limit)


def _sample_source(config: pytest.Config) -> str:
    raw = config.getoption("--integration-sample-source")
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get("INTEGRATION_SAMPLE_SOURCE")
    return resolve_sample_source(raw)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root (monorepo)."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def resolved_integration_samples(request: pytest.FixtureRequest, repo_root: Path) -> list[Path]:
    """Sample files from selected source (shuffled), then limited by flags.

    Examples::

        uv run pytest tests/integration -k manifest -v
        uv run pytest tests/integration --integration-sample-limit=2 -k manifest -v
        INTEGRATION_SAMPLE_LIMIT=2 uv run pytest tests/integration -k manifest -v
        INTEGRATION_SAMPLE_SOURCE=downloads uv run pytest tests/integration -k manifest -v
        uv run pytest tests/integration --integration-repeat-to=100 -k manifest -v
    """
    source = _sample_source(request.config)
    return _resolve_limited_paths(request, list(iter_sample_files(repo_root, source=source)))


@pytest.fixture(scope="session")
def resolved_worker_e2e_samples(
    resolved_integration_samples: list[Path],
) -> list[Path]:
    """Same paths as ``resolved_integration_samples``; worker jobs may end ``ok`` or ``error``."""
    return resolved_integration_samples


@pytest.fixture
def integration_storage(repo_root: Path) -> IntegrationStorage:
    """Host-side storage matching the running worker (``DOCRUNR_INTEGRATION_STORAGE``)."""
    return integration_storage_from_env(repo_root)


@pytest.fixture(scope="session")
def available_integration_llm_profiles() -> tuple[str, ...]:
    """Live LiteLLM profile list available to the integration test runner."""
    try:
        return fetch_litellm_profiles_from_env()
    except RuntimeError as exc:
        pytest.skip(f"LiteLLM model list not reachable for integration test selection ({exc})")


@pytest.fixture(scope="session")
def integration_llm_profiles(
    available_integration_llm_profiles: tuple[str, ...],
) -> tuple[str, ...]:
    """Candidate LLM profiles; LLM e2e draws one at random per staged document."""
    try:
        return resolve_llm_profile_pool_from_env(all_profiles=available_integration_llm_profiles)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc


@pytest.fixture(scope="session")
def integration_llm_profile(
    available_integration_llm_profiles: tuple[str, ...],
) -> str:
    """One random profile from the pool (session). Prefer ``integration_llm_profiles`` when selecting per job."""
    try:
        return resolve_llm_profile_from_env(all_profiles=available_integration_llm_profiles)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
