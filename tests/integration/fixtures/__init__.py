"""Manifests and helpers for integration tests."""

from __future__ import annotations

import os
import random
from collections.abc import Callable, Sequence
from json import JSONDecodeError, loads
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

# Default profile set used by fast unit tests for helper logic.
DEFAULT_LLM_PROFILES: tuple[str, ...] = (
    "nomic-embed-text-137m",
    "embedding-gemma-300m",
    "bge-m3-560m",
    "qwen3-embedding-8b",
)


def _csv_items(raw: str | None) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _normalize_litellm_profiles_payload(payload: object) -> tuple[str, ...]:
    raw_items = payload
    if isinstance(payload, dict):
        raw_items = payload.get("data", [])
    if not isinstance(raw_items, list):
        return ()

    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        profile = ""
        if isinstance(raw, str):
            profile = raw.strip()
        elif isinstance(raw, dict):
            for key in ("model_name", "id", "model"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    profile = value.strip()
                    break
        if not profile or profile in seen:
            continue
        seen.add(profile)
        items.append(profile)
    return tuple(items)


def resolve_integration_litellm_base_url(raw_base_url: str | None = None) -> str:
    """Return a host-reachable LiteLLM base URL for integration tests."""
    candidate = (
        (raw_base_url or "").strip()
        or os.environ.get("DOCRUNR_INTEGRATION_LITELLM_BASE_URL", "").strip()
        or os.environ.get("LITELLM_BASE_URL", "").strip()
        or "http://127.0.0.1:4000"
    )
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").strip().lower()
    if host not in {"litellm", "localhost"}:
        return candidate

    port = parsed.port or 4000
    return urlunparse(
        (
            parsed.scheme or "http",
            f"127.0.0.1:{port}",
            parsed.path or "",
            "",
            parsed.query,
            parsed.fragment,
        )
    )


def fetch_litellm_profiles(
    base_url: str,
    *,
    api_key: str = "",
    timeout_seconds: float = 30.0,
) -> tuple[str, ...]:
    """Fetch the live LiteLLM model_name list from ``/models``."""
    headers = {"Accept": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    request = Request(f"{base_url.rstrip('/')}/models", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"LiteLLM model list request failed: {exc}") from exc
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise RuntimeError("LiteLLM model list returned invalid JSON") from exc

    profiles = _normalize_litellm_profiles_payload(payload)
    if not profiles:
        raise RuntimeError("LiteLLM model list returned no configured profiles")
    return profiles


def fetch_litellm_profiles_from_env() -> tuple[str, ...]:
    """Fetch the live LiteLLM model list using integration-test environment defaults."""
    timeout = float(os.environ.get("LITELLM_TIMEOUT_SECONDS", "120"))
    return fetch_litellm_profiles(
        resolve_integration_litellm_base_url(),
        api_key=os.environ.get("LITELLM_API_KEY", ""),
        timeout_seconds=timeout,
    )


def _validate_profiles(
    requested: Sequence[str],
    *,
    all_profiles: Sequence[str] = DEFAULT_LLM_PROFILES,
) -> tuple[str, ...]:
    unknown = [profile for profile in requested if profile not in all_profiles]
    if unknown:
        valid = ", ".join(all_profiles)
        unknown_csv = ", ".join(unknown)
        raise ValueError(
            f"Unknown LLM profile(s): {unknown_csv}. Valid profiles: {valid}."
        )

    unique: list[str] = []
    seen: set[str] = set()
    for profile in requested:
        if profile in seen:
            continue
        seen.add(profile)
        unique.append(profile)
    return tuple(unique)


def resolve_llm_profile_pool(
    raw_profiles: str | None = None,
    *,
    all_profiles: Sequence[str] = DEFAULT_LLM_PROFILES,
) -> tuple[str, ...]:
    """Resolve the candidate pool for integration LLM runs."""
    requested = _csv_items(raw_profiles)
    if not requested:
        return tuple(all_profiles)
    return _validate_profiles(requested, all_profiles=all_profiles)


def resolve_llm_profile(
    raw_profiles: str | None = None,
    *,
    choice: Callable[[Sequence[str]], str] = random.choice,
    all_profiles: Sequence[str] = DEFAULT_LLM_PROFILES,
) -> str:
    """Resolve one integration LLM profile from the candidate pool."""
    pool = resolve_llm_profile_pool(raw_profiles, all_profiles=all_profiles)
    return choice(pool)


def resolve_llm_profile_pool_from_env(*, all_profiles: Sequence[str]) -> tuple[str, ...]:
    """Resolve the integration LLM profile pool from environment variables."""
    return resolve_llm_profile_pool(
        os.environ.get("INTEGRATION_LLM_PROFILES"),
        all_profiles=all_profiles,
    )


def resolve_llm_profile_from_env(
    *,
    choice: Callable[[Sequence[str]], str] = random.choice,
    all_profiles: Sequence[str],
) -> str:
    """Resolve the integration LLM profile selection from environment variables."""
    return resolve_llm_profile(
        os.environ.get("INTEGRATION_LLM_PROFILES"),
        choice=choice,
        all_profiles=all_profiles,
    )
