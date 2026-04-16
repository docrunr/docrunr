"""LLM job payload construction and validation."""

from __future__ import annotations

import json
import uuid
from typing import Any


def new_job_id() -> str:
    return str(uuid.uuid4())


def llm_job_payload_dict(
    *,
    job_id: str,
    extract_job_id: str,
    filename: str,
    source_path: str,
    chunks_path: str,
    llm_profile: str,
    priority: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape published to ``docrunr.llm.jobs``."""
    payload: dict[str, Any] = {
        "job_id": job_id,
        "extract_job_id": extract_job_id,
        "filename": filename,
        "source_path": source_path,
        "chunks_path": chunks_path,
        "llm_profile": llm_profile,
        "priority": priority,
        "metadata": metadata if metadata is not None else {},
    }
    return payload


def llm_job_payload_bytes(
    *,
    job_id: str,
    extract_job_id: str,
    filename: str,
    source_path: str,
    chunks_path: str,
    llm_profile: str,
    priority: int = 0,
    metadata: dict[str, Any] | None = None,
) -> bytes:
    return json.dumps(
        llm_job_payload_dict(
            job_id=job_id,
            extract_job_id=extract_job_id,
            filename=filename,
            source_path=source_path,
            chunks_path=chunks_path,
            llm_profile=llm_profile,
            priority=priority,
            metadata=metadata,
        ),
        separators=(",", ":"),
    ).encode()
