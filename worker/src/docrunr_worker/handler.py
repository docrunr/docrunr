"""Job handlers for extraction message processing."""

from __future__ import annotations

import hashlib
import json
import logging
import signal
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import FrameType
from typing import TYPE_CHECKING, Any, cast

from docrunr import convert

from docrunr_worker.job_messages import parse_extraction_job_priority

if TYPE_CHECKING:
    from docrunr_worker.storage import StorageBackend

logger = logging.getLogger(__name__)


class JobTimeoutError(Exception):
    pass


@dataclass(frozen=True)
class JobRequest:
    job_id: str
    filename: str
    source_path: str
    priority: int = 0
    llm_profile: str = ""


@dataclass(frozen=True)
class OutputArtifacts:
    stem: str
    markdown_path: str
    chunks_path: str


@dataclass(frozen=True)
class ExtractionRequest:
    request: JobRequest


@dataclass(frozen=True)
class ExtractionOutcome:
    result_json: str
    result: dict[str, object] = field(default_factory=dict)
    status: str = "error"
    duration_seconds: float = 0.0


def _build_outcome(
    *,
    request: JobRequest,
    status: str,
    duration_seconds: float,
    markdown_path: str | None,
    chunks_path: str | None,
    total_tokens: int,
    chunk_count: int,
    error: str | None,
    mime_type: str = "",
    size_bytes: int = 0,
) -> ExtractionOutcome:
    result = {
        "job_id": request.job_id,
        "status": status,
        "filename": request.filename,
        "source_path": request.source_path,
        "markdown_path": markdown_path,
        "chunks_path": chunks_path,
        "total_tokens": total_tokens,
        "chunk_count": chunk_count,
        "duration_seconds": round(duration_seconds, 2),
        "error": error,
        "mime_type": mime_type,
        "size_bytes": int(size_bytes),
        "priority": int(request.priority),
        "llm_profile": request.llm_profile,
    }
    return ExtractionOutcome(
        result_json=json.dumps(result),
        result=cast(dict[str, object], result),
        status=status,
        duration_seconds=duration_seconds,
    )


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


def _parse_job_request(msg: dict[str, Any]) -> JobRequest:
    raw_filename = msg.get("filename")
    filename = raw_filename if isinstance(raw_filename, str) and raw_filename else "unknown"
    priority = parse_extraction_job_priority(msg)
    raw_llm_profile = msg.get("llm_profile")
    llm_profile = raw_llm_profile.strip() if isinstance(raw_llm_profile, str) else ""
    return JobRequest(
        job_id=_require_non_empty_str(msg, "job_id", context="job"),
        filename=filename,
        source_path=_require_non_empty_str(msg, "source_path", context="job"),
        priority=priority,
        llm_profile=llm_profile,
    )


def _parse_extraction_request(*, body: bytes) -> ExtractionRequest:
    msg = _parse_json_object(body, context="job")
    raw_options = msg.get("options")
    if raw_options is not None and not isinstance(raw_options, dict):
        raise ValueError("Invalid job payload: options must be a JSON object")
    request = _parse_job_request(msg)
    return ExtractionRequest(request=request)


def _malformed_job_id(body: bytes, *, delivery_id: str | None = None) -> str:
    """Synthetic id for invalid payloads: body hash plus optional per-delivery suffix.

    The consumer passes a fresh ``delivery_id`` per queue message so repeated deliveries of the
    same malformed bytes still get distinct ``job_id`` values and do not overwrite one row.
    """
    digest = hashlib.sha256(body).hexdigest()[:24]
    base = f"malformed-{digest}"
    if delivery_id and delivery_id.strip():
        return f"{base}-{delivery_id.strip()}"
    return base


def parse_job_request_from_body(body: bytes, *, delivery_id: str | None = None) -> JobRequest:
    """Parse ``job_id``, ``filename``, and ``source_path`` using the same rules as extraction.

    Used at the consumer boundary before work is handed off. On any parse/validation error,
    returns a :class:`JobRequest` whose ``job_id`` is derived from the body hash and optional
    ``delivery_id`` (see :func:`_malformed_job_id`).
    """
    try:
        return _parse_extraction_request(body=body).request
    except Exception:
        return JobRequest(
            job_id=_malformed_job_id(body, delivery_id=delivery_id),
            filename="unknown",
            source_path="unknown",
            priority=0,
        )


def _derive_output_prefix(source_path: str) -> str:
    """Derive output prefix from ``source_path``: ``input/.../uuid.ext`` -> ``output/.../uuid``.

    Mirrors the relative segments after ``input/`` (for example hour-partitioned
    ``input/YYYY/MM/DD/HH/uuid.ext`` -> ``output/YYYY/MM/DD/HH/uuid``). Shallower
    layouts such as legacy ``input/YYYY/MM/uuid.ext`` are still accepted.
    """
    source = PurePosixPath(source_path)
    if not source.parts or source.parts[0] != "input":
        raise ValueError(f"Invalid source_path (must start with 'input/'): {source_path}")
    relative = PurePosixPath(*source.parts[1:])
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise ValueError(f"Invalid source_path (unsafe relative path): {source_path}")
    return str(PurePosixPath("output") / relative.with_suffix(""))


def _build_artifacts(source_path: str) -> OutputArtifacts:
    prefix = _derive_output_prefix(source_path)
    stem = PurePosixPath(prefix).name
    return OutputArtifacts(
        stem=stem,
        markdown_path=f"{prefix}.md",
        chunks_path=f"{prefix}.json",
    )


def handle_extract_job(
    *,
    body: bytes,
    storage: StorageBackend,
    timeout: int,
    delivery_id: str | None = None,
) -> ExtractionOutcome:
    start = time.monotonic()
    request = parse_job_request_from_body(body, delivery_id=delivery_id)
    local_file: Path | None = None

    def _timeout_handler(signum: int, frame: FrameType | None) -> None:
        _ = signum, frame
        raise JobTimeoutError(f"Job {request.job_id} exceeded {timeout}s timeout")

    old_handler: signal.Handlers | int | None | Callable[[int, FrameType | None], Any] = None
    timeout_enabled = hasattr(signal, "SIGALRM") and timeout > 0
    try:
        parsed = _parse_extraction_request(body=body)
        request = parsed.request
        logger.info("Processing job %s (%s)", request.job_id, request.filename)

        if timeout_enabled:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)

        local_file = storage.read(request.source_path)
        result = convert(local_file)

        if not result.ok:
            duration = time.monotonic() - start
            err = result.error or "conversion failed"
            logger.error("Job %s conversion failed: %s", request.job_id, err)
            return _build_outcome(
                request=request,
                status="error",
                duration_seconds=duration,
                markdown_path=None,
                chunks_path=None,
                total_tokens=0,
                chunk_count=0,
                error=err,
                mime_type=result.mime_type,
                size_bytes=result.size_bytes,
            )

        artifacts = _build_artifacts(request.source_path)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result.write(tmp_dir, artifacts.stem)
            storage.write(tmp_dir / f"{artifacts.stem}.md", artifacts.markdown_path)
            storage.write(tmp_dir / f"{artifacts.stem}.json", artifacts.chunks_path)

        duration = time.monotonic() - start
        return _build_outcome(
            request=request,
            status="ok",
            duration_seconds=duration,
            markdown_path=artifacts.markdown_path,
            chunks_path=artifacts.chunks_path,
            total_tokens=result.total_tokens,
            chunk_count=len(result.chunks),
            error=None,
            mime_type=result.mime_type,
            size_bytes=result.size_bytes,
        )

    except Exception as exc:
        duration = time.monotonic() - start
        logger.exception("Job %s failed: %s", request.job_id, exc)
        return _build_outcome(
            request=request,
            status="error",
            duration_seconds=duration,
            markdown_path=None,
            chunks_path=None,
            total_tokens=0,
            chunk_count=0,
            error=str(exc),
        )

    finally:
        if timeout_enabled:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
        if local_file is not None:
            try:
                storage.cleanup(local_file)
            except Exception:
                logger.debug("Failed to cleanup local file %s", local_file, exc_info=True)


def handle_job(
    body: bytes,
    storage: StorageBackend,
    timeout: int,
    *,
    delivery_id: str | None = None,
) -> str:
    """Backward-compatible extraction-only wrapper for tests/callers."""
    outcome = handle_extract_job(
        body=body,
        storage=storage,
        timeout=timeout,
        delivery_id=delivery_id,
    )
    return outcome.result_json
