"""Shared job id generation, input storage paths, and job payload serialization."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

# RabbitMQ priority queue: AMQP ``BasicProperties.priority`` and ``x-max-priority`` must match.
JOB_QUEUE_MAX_PRIORITY: int = 255
EXTRACTION_JOB_QUEUE_ARGUMENTS: dict[str, int] = {"x-max-priority": JOB_QUEUE_MAX_PRIORITY}


class InvalidJobPriorityError(ValueError):
    """Raised when ``priority`` is not an integer in ``0..255`` (payload or upload query)."""


def validate_extraction_job_priority_value(priority: object) -> int:
    """Same rules as JSON ingest: ``None``/missing → ``0``; else only ``int`` in ``0..255``."""
    if priority is None:
        return 0
    if type(priority) is bool:
        raise InvalidJobPriorityError("Invalid job payload: priority must be an integer 0..255")
    if type(priority) is not int:
        raise InvalidJobPriorityError("Invalid job payload: priority must be an integer 0..255")
    if priority < 0 or priority > JOB_QUEUE_MAX_PRIORITY:
        raise InvalidJobPriorityError("Invalid job payload: priority must be an integer 0..255")
    return priority


def parse_extraction_job_priority(msg: dict[str, Any]) -> int:
    """Read optional ``priority`` from a job JSON object; default ``0``.

    Accepts only JSON integers (not bool, float, or string).
    """
    return validate_extraction_job_priority_value(msg.get("priority"))


def parse_upload_priority_query(raw: str | None) -> int:
    """Parse ``POST /api/uploads?priority=``; omitted or blank → ``0``."""
    if raw is None or not str(raw).strip():
        return 0
    text = str(raw).strip()
    try:
        value = int(text, 10)
    except ValueError:
        raise InvalidJobPriorityError("priority must be an integer 0..255") from None
    if value < 0 or value > JOB_QUEUE_MAX_PRIORITY:
        raise InvalidJobPriorityError("priority must be an integer 0..255")
    return value


# Lowercase extensions DocRunr supports (README — Worker / supported formats).
ALLOWED_UPLOAD_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".odt",
        ".xlsx",
        ".xls",
        ".ods",
        ".csv",
        ".pptx",
        ".ppt",
        ".odp",
        ".eml",
        ".msg",
        ".html",
        ".htm",
        ".xml",
        ".md",
        ".json",
        ".txt",
        ".jpg",
        ".jpeg",
        ".png",
        ".tiff",
        ".tif",
        ".bmp",
    }
)


def new_job_id() -> str:
    return str(uuid.uuid4())


def safe_client_filename(raw: str) -> str:
    """Use the basename only; empty becomes 'unknown'."""
    name = PurePosixPath(raw.replace("\\", "/")).name.strip()
    return name if name else "unknown"


def file_suffix_for_upload(filename: str) -> str:
    """Lowercase suffix including dot, or ''."""
    return PurePosixPath(safe_client_filename(filename)).suffix.lower()


def is_allowed_upload_suffix(suffix: str) -> bool:
    return suffix in ALLOWED_UPLOAD_SUFFIXES


def input_relative_path(job_id: str, file_suffix: str, *, now: datetime | None = None) -> str:
    """Return storage-relative path ``input/YYYY/MM/DD/HH/<job_id><ext>`` (UTC; ext lowercased)."""
    when = now or datetime.now(UTC)
    y = when.year
    mo = f"{when.month:02d}"
    d = f"{when.day:02d}"
    h = f"{when.hour:02d}"
    ext = file_suffix.lower() if file_suffix else ""
    return f"input/{y}/{mo}/{d}/{h}/{job_id}{ext}"


def job_payload_dict(
    job_id: str,
    filename: str,
    source_path: str,
    *,
    options: dict[str, Any] | None = None,
    priority: object = 0,
) -> dict[str, Any]:
    """Shape published to ``docrunr.jobs`` (matches README contract)."""
    p = validate_extraction_job_priority_value(priority)
    payload: dict[str, Any] = {
        "job_id": job_id,
        "filename": filename,
        "source_path": source_path,
        "options": options if options is not None else {},
        "priority": p,
    }
    return payload


def job_payload_bytes(
    job_id: str,
    filename: str,
    source_path: str,
    *,
    options: dict[str, Any] | None = None,
    priority: object = 0,
) -> bytes:
    return json.dumps(
        job_payload_dict(
            job_id,
            filename,
            source_path,
            options=options,
            priority=priority,
        ),
        separators=(",", ":"),
    ).encode()
