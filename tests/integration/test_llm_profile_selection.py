"""Fast checks for integration LLM profile selection helpers."""

from __future__ import annotations

from tests.integration.fixtures import (
    DEFAULT_LLM_PROFILES,
    _normalize_litellm_profiles_payload,
    resolve_llm_profile,
    resolve_llm_profile_pool,
)


def test_resolve_llm_profile_pool_defaults_to_all_profiles() -> None:
    assert resolve_llm_profile_pool() == DEFAULT_LLM_PROFILES


def test_resolve_llm_profile_pool_filters_and_dedupes() -> None:
    assert resolve_llm_profile_pool(
        "embedding-gemma-300m, nomic-embed-text-137m, embedding-gemma-300m"
    ) == (
        "embedding-gemma-300m",
        "nomic-embed-text-137m",
    )


def test_resolve_llm_profile_single_item_pool_pins_model() -> None:
    picked = resolve_llm_profile(
        raw_profiles="qwen3-embedding-8b",
        choice=lambda profiles: profiles[0],
    )
    assert picked == "qwen3-embedding-8b"


def test_resolve_llm_profile_picks_from_filtered_pool() -> None:
    picked = resolve_llm_profile(
        raw_profiles="bge-m3-560m,embedding-gemma-300m",
        choice=lambda profiles: profiles[-1],
    )
    assert picked == "embedding-gemma-300m"


def test_resolve_llm_profile_rejects_unknown_profiles() -> None:
    try:
        resolve_llm_profile_pool("nomic-embed-text-137m,embed-unknown")
    except ValueError as exc:
        assert "embed-unknown" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown LLM profile")


def test_normalize_litellm_profiles_payload_uses_model_name_values() -> None:
    payload = {
        "data": [
            {"model_name": "nomic-embed-text-137m", "model": "ollama/nomic-embed-text"},
            {"model_name": "embedding-gemma-300m", "model": "ollama/embeddinggemma"},
            {"model_name": "embedding-gemma-300m", "model": "ollama/embeddinggemma"},
        ]
    }
    assert _normalize_litellm_profiles_payload(payload) == (
        "nomic-embed-text-137m",
        "embedding-gemma-300m",
    )
