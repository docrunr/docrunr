"""Embedding generation from extracted chunks — reads chunk JSON, calls LiteLLM, writes artifact."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from docrunr_worker_llm.litellm_client import EmbeddingResult, create_embeddings

if TYPE_CHECKING:
    from docrunr_worker_llm.config import LlmWorkerSettings
    from docrunr_worker_llm.storage import StorageBackend

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


@dataclass(frozen=True)
class EmbeddingArtifact:
    chunk_count: int
    vector_count: int
    llm_profile: str
    provider: str
    token_count: int
    artifact_path: str


def _load_chunks(storage: StorageBackend, chunks_path: str) -> list[dict[str, Any]]:
    local = storage.read(chunks_path)
    try:
        raw = local.read_text(encoding="utf-8")
        data = json.loads(raw)
    finally:
        storage.cleanup(local)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "chunks" in data:
        return data["chunks"]
    raise ValueError(f"Unexpected chunk JSON shape at {chunks_path}")


def _extract_texts(chunks: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for chunk in chunks:
        text = chunk.get("text") or chunk.get("content") or ""
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def _derive_artifact_path(chunks_path: str) -> str:
    """``output/.../uuid.json`` → ``output/.../uuid.embeddings.json``."""
    p = PurePosixPath(chunks_path)
    return str(p.with_suffix(".embeddings.json"))


def generate_embeddings(
    *,
    chunks_path: str,
    storage: StorageBackend,
    settings: LlmWorkerSettings,
    llm_profile: str,
) -> EmbeddingArtifact:
    """Load chunk JSON, batch-embed via LiteLLM, write embedding artifact to storage."""
    chunks = _load_chunks(storage, chunks_path)
    texts = _extract_texts(chunks)
    if not texts:
        raise ValueError(f"No embeddable text found in {chunks_path}")

    all_vectors: list[list[float]] = []
    resolved_profile = ""
    resolved_provider = ""
    total_tokens = 0

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        result: EmbeddingResult = create_embeddings(
            batch, settings=settings, llm_profile=llm_profile
        )
        all_vectors.extend(result.vectors)
        resolved_profile = result.llm_profile
        resolved_provider = result.provider
        total_tokens += result.token_count

    artifact_path = _derive_artifact_path(chunks_path)
    artifact_data = {
        "llm_profile": resolved_profile,
        "provider": resolved_provider,
        "chunk_count": len(chunks),
        "vector_count": len(all_vectors),
        "token_count": total_tokens,
        "dimensions": len(all_vectors[0]) if all_vectors else 0,
        "embeddings": [
            {"index": idx, "text": texts[idx] if idx < len(texts) else "", "vector": vec}
            for idx, vec in enumerate(all_vectors)
        ],
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_file = Path(tmp) / "embeddings.json"
        tmp_file.write_text(json.dumps(artifact_data), encoding="utf-8")
        storage.write(tmp_file, artifact_path)

    return EmbeddingArtifact(
        chunk_count=len(chunks),
        vector_count=len(all_vectors),
        llm_profile=resolved_profile,
        provider=resolved_provider,
        token_count=total_tokens,
        artifact_path=artifact_path,
    )
