"""Tests for LLM worker handler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from docrunr_worker_llm.config import LlmWorkerSettings
from docrunr_worker_llm.embeddings import EmbeddingArtifact
from docrunr_worker_llm.handler import (
    handle_llm_job,
    parse_job_request_from_body,
)
from docrunr_worker_llm.storage import LocalStorage


def test_parse_malformed_body_returns_stub() -> None:
    req = parse_job_request_from_body(b"{}", delivery_id="d1")
    assert req.job_id.startswith("malformed-")
    assert req.job_id.endswith("-d1")
    assert req.filename == "unknown"
    assert req.chunks_path == "unknown"


def test_parse_valid_body() -> None:
    body = json.dumps(
        {
            "job_id": "abc",
            "extract_job_id": "ext-1",
            "filename": "test.pdf",
            "source_path": "input/test.pdf",
            "chunks_path": "output/test.json",
            "llm_profile": "embed-local",
        }
    ).encode()
    req = parse_job_request_from_body(body)
    assert req.job_id == "abc"
    assert req.extract_job_id == "ext-1"
    assert req.filename == "test.pdf"
    assert req.llm_profile == "embed-local"


def test_handle_llm_job_success(tmp_path: Path) -> None:
    base = tmp_path / "data"
    (base / "output/2026/04/15/00").mkdir(parents=True)
    chunks = [{"text": "hello world", "token_count": 2}]
    (base / "output/2026/04/15/00/j1.json").write_text(json.dumps(chunks))
    storage = LocalStorage(str(base))
    settings = LlmWorkerSettings()

    body = json.dumps(
        {
            "job_id": "j1",
            "extract_job_id": "ext-1",
            "filename": "j1.pdf",
            "source_path": "input/2026/04/15/00/j1.pdf",
            "chunks_path": "output/2026/04/15/00/j1.json",
            "llm_profile": "embed-local",
        }
    ).encode()

    mock_artifact = EmbeddingArtifact(
        chunk_count=1,
        vector_count=1,
        llm_profile="embed-local",
        provider="openai",
        token_count=2,
        artifact_path="output/2026/04/15/00/j1.embeddings.json",
    )

    with patch("docrunr_worker_llm.handler.generate_embeddings", return_value=mock_artifact):
        outcome = handle_llm_job(body=body, storage=storage, settings=settings)

    result = json.loads(outcome.result_json)
    assert result["status"] == "ok"
    assert result["job_id"] == "j1"
    assert result["llm_profile"] == "embed-local"
    assert result["chunk_count"] == 1
    assert result["vector_count"] == 1
    assert result["artifact_path"] == "output/2026/04/15/00/j1.embeddings.json"


def test_handle_llm_job_error_on_missing_chunks(tmp_path: Path) -> None:
    base = tmp_path / "data"
    base.mkdir()
    storage = LocalStorage(str(base))
    settings = LlmWorkerSettings()

    body = json.dumps(
        {
            "job_id": "j2",
            "extract_job_id": "ext-2",
            "filename": "j2.pdf",
            "source_path": "input/j2.pdf",
            "chunks_path": "output/j2.json",
            "llm_profile": "embed-local",
        }
    ).encode()

    outcome = handle_llm_job(body=body, storage=storage, settings=settings)
    result = json.loads(outcome.result_json)
    assert result["status"] == "error"
    assert result["error"] is not None
    assert result["llm_profile"] == "embed-local"
