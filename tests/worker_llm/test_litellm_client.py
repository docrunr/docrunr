"""Tests for LiteLLM client wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from docrunr_worker_llm.config import LlmWorkerSettings
from docrunr_worker_llm.litellm_client import (
    EmbeddingResult,
    LitellmError,
    _infer_provider,
    create_embeddings,
)


class TestInferProvider:
    def test_openai_default(self) -> None:
        assert _infer_provider("text-embedding-ada-002") == "openai"

    def test_ollama_prefix(self) -> None:
        assert _infer_provider("ollama/nomic-embed-text") == "ollama"

    def test_azure_prefix(self) -> None:
        assert _infer_provider("azure/my-deployment") == "azure"


def test_create_embeddings_success() -> None:
    settings = LlmWorkerSettings()

    mock_data = [{"embedding": [0.1, 0.2, 0.3]}]
    mock_usage = MagicMock()
    mock_usage.total_tokens = 5
    mock_response = MagicMock()
    mock_response.data = mock_data
    mock_response.usage = mock_usage

    with patch("litellm.embedding", return_value=mock_response):
        result = create_embeddings(
            ["hello"], settings=settings, llm_profile="text-embedding-ada-002"
        )

    assert isinstance(result, EmbeddingResult)
    assert len(result.vectors) == 1
    assert result.vectors[0] == [0.1, 0.2, 0.3]
    assert result.token_count == 5
    assert result.llm_profile == "text-embedding-ada-002"
    assert result.provider == "openai"


def test_create_embeddings_timeout_raises_litellm_error() -> None:
    settings = LlmWorkerSettings()

    with (
        patch("litellm.embedding", side_effect=TimeoutError("Connection timed out")),
        pytest.raises(LitellmError, match="Connection timed out"),
    ):
        create_embeddings(["hello"], settings=settings, llm_profile="text-embedding-ada-002")


def test_create_embeddings_empty_profile_raises() -> None:
    settings = LlmWorkerSettings()

    with pytest.raises(LitellmError, match="llm_profile is required"):
        create_embeddings(["hello"], settings=settings, llm_profile="")


def test_create_embeddings_with_custom_profile() -> None:
    settings = LlmWorkerSettings()

    mock_data = [{"embedding": [0.5, 0.6]}]
    mock_response = MagicMock()
    mock_response.data = mock_data
    mock_response.usage = None
    mock_response.model = "ollama/nomic-embed-text"

    with patch("litellm.embedding", return_value=mock_response):
        result = create_embeddings(
            ["test"], settings=settings, llm_profile="ollama/nomic-embed-text"
        )

    assert result.llm_profile == "ollama/nomic-embed-text"
    assert result.provider == "ollama"
    assert result.token_count == 0
