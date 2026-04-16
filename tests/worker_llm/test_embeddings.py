"""Tests for embedding generation module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from docrunr_worker_llm.config import LlmWorkerSettings
from docrunr_worker_llm.embeddings import (
    _derive_artifact_path,
    _extract_texts,
    generate_embeddings,
)
from docrunr_worker_llm.litellm_client import EmbeddingResult
from docrunr_worker_llm.storage import LocalStorage


class TestDeriveArtifactPath:
    def test_standard_path(self) -> None:
        assert (
            _derive_artifact_path("output/2026/04/15/00/abc.json")
            == "output/2026/04/15/00/abc.embeddings.json"
        )

    def test_nested_path(self) -> None:
        assert _derive_artifact_path("output/x/y/z.json") == "output/x/y/z.embeddings.json"


class TestExtractTexts:
    def test_text_field(self) -> None:
        chunks = [{"text": "hello"}, {"text": "world"}]
        assert _extract_texts(chunks) == ["hello", "world"]

    def test_content_fallback(self) -> None:
        chunks = [{"content": "fallback"}]
        assert _extract_texts(chunks) == ["fallback"]

    def test_empty_text_skipped(self) -> None:
        chunks = [{"text": ""}, {"text": "ok"}, {"text": "  "}]
        assert _extract_texts(chunks) == ["ok"]


def test_generate_embeddings_success(tmp_path: Path) -> None:
    base = tmp_path / "data"
    (base / "output").mkdir(parents=True)
    chunks = [{"text": "hello"}, {"text": "world"}]
    (base / "output" / "doc.json").write_text(json.dumps(chunks))

    storage = LocalStorage(str(base))
    settings = LlmWorkerSettings()

    mock_result = EmbeddingResult(
        vectors=[[0.1, 0.2], [0.3, 0.4]],
        llm_profile="embed-local",
        provider="openai",
        token_count=10,
    )

    with patch("docrunr_worker_llm.embeddings.create_embeddings", return_value=mock_result):
        artifact = generate_embeddings(
            chunks_path="output/doc.json",
            storage=storage,
            settings=settings,
            llm_profile="embed-local",
        )

    assert artifact.chunk_count == 2
    assert artifact.vector_count == 2
    assert artifact.llm_profile == "embed-local"
    assert artifact.artifact_path == "output/doc.embeddings.json"

    artifact_local = storage.read(artifact.artifact_path)
    data = json.loads(artifact_local.read_text())
    assert data["vector_count"] == 2
    assert len(data["embeddings"]) == 2


def test_generate_embeddings_no_texts_raises(tmp_path: Path) -> None:
    base = tmp_path / "data"
    (base / "output").mkdir(parents=True)
    (base / "output" / "empty.json").write_text(json.dumps([{"other": "field"}]))

    storage = LocalStorage(str(base))
    settings = LlmWorkerSettings()

    with pytest.raises(ValueError, match="No embeddable text"):
        generate_embeddings(
            chunks_path="output/empty.json",
            storage=storage,
            settings=settings,
            llm_profile="embed-local",
        )
