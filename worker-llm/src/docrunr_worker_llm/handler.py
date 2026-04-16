"""Job handler for LLM/embedding message processing."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from docrunr_worker_llm.embeddings import generate_embeddings

if TYPE_CHECKING:
    from docrunr_worker_llm.config import LlmWorkerSettings
    from docrunr_worker_llm.storage import StorageBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmJobRequest:
    job_id: str
    extract_job_id: str
    filename: str
    source_path: str
    chunks_path: str
    llm_profile: str = ""


@dataclass(frozen=True)
class LlmOutcome:
    result_json: str
    result: dict[str, object] = field(default_factory=dict)
    status: str = "error"
    duration_seconds: float = 0.0


def _parse_json_object(body: bytes, *, context: str) -> dict[str, Any]:
    msg = json.loads(body)
    if not isinstance(msg, dict):
        raise ValueError(f"Invalid {context} payload: expected JSON object")
    return msg


def _require_non_empty_str(data: dict[str, Any], key: str, *, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid {context} payload: {key} must be a non-empty string")
    return value


def _parse_llm_request(body: bytes) -> LlmJobRequest:
    msg = _parse_json_object(body, context="llm-job")
    raw_profile = msg.get("llm_profile")
    llm_profile = raw_profile if isinstance(raw_profile, str) else ""
    return LlmJobRequest(
        job_id=_require_non_empty_str(msg, "job_id", context="llm-job"),
        extract_job_id=_require_non_empty_str(msg, "extract_job_id", context="llm-job"),
        filename=msg.get("filename") if isinstance(msg.get("filename"), str) else "unknown",
        source_path=_require_non_empty_str(msg, "source_path", context="llm-job"),
        chunks_path=_require_non_empty_str(msg, "chunks_path", context="llm-job"),
        llm_profile=llm_profile,
    )


def _malformed_job_id(body: bytes, *, delivery_id: str | None = None) -> str:
    digest = hashlib.sha256(body).hexdigest()[:24]
    base = f"malformed-{digest}"
    if delivery_id and delivery_id.strip():
        return f"{base}-{delivery_id.strip()}"
    return base


def parse_job_request_from_body(body: bytes, *, delivery_id: str | None = None) -> LlmJobRequest:
    """Best-effort parse; returns a stub with synthetic job_id on failure."""
    try:
        return _parse_llm_request(body)
    except Exception:
        return LlmJobRequest(
            job_id=_malformed_job_id(body, delivery_id=delivery_id),
            extract_job_id="unknown",
            filename="unknown",
            source_path="unknown",
            chunks_path="unknown",
        )


def _build_outcome(
    *,
    request: LlmJobRequest,
    status: str,
    duration_seconds: float,
    llm_profile: str = "",
    provider: str = "",
    chunk_count: int = 0,
    vector_count: int = 0,
    artifact_path: str | None = None,
    error: str | None = None,
) -> LlmOutcome:
    result = {
        "job_id": request.job_id,
        "extract_job_id": request.extract_job_id,
        "status": status,
        "filename": request.filename,
        "source_path": request.source_path,
        "chunks_path": request.chunks_path,
        "llm_profile": llm_profile,
        "provider": provider,
        "chunk_count": chunk_count,
        "vector_count": vector_count,
        "duration_seconds": round(duration_seconds, 2),
        "artifact_path": artifact_path,
        "error": error,
    }
    return LlmOutcome(
        result_json=json.dumps(result),
        result=cast(dict[str, object], result),
        status=status,
        duration_seconds=duration_seconds,
    )


def handle_llm_job(
    *,
    body: bytes,
    storage: StorageBackend,
    settings: LlmWorkerSettings,
    delivery_id: str | None = None,
) -> LlmOutcome:
    start = time.monotonic()
    request = parse_job_request_from_body(body, delivery_id=delivery_id)

    try:
        parsed = _parse_llm_request(body)
        request = parsed
        logger.info("Processing LLM job %s (%s)", request.job_id, request.filename)

        artifact = generate_embeddings(
            chunks_path=request.chunks_path,
            storage=storage,
            settings=settings,
            llm_profile=request.llm_profile,
        )

        duration = time.monotonic() - start
        return _build_outcome(
            request=request,
            status="ok",
            duration_seconds=duration,
            llm_profile=artifact.llm_profile,
            provider=artifact.provider,
            chunk_count=artifact.chunk_count,
            vector_count=artifact.vector_count,
            artifact_path=artifact.artifact_path,
        )

    except Exception as exc:
        duration = time.monotonic() - start
        logger.exception("LLM job %s failed: %s", request.job_id, exc)
        return _build_outcome(
            request=request,
            status="error",
            duration_seconds=duration,
            llm_profile=request.llm_profile,
            error=str(exc),
        )
