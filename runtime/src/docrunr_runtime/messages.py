"""Shared extraction job contract and storage path helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

JOB_QUEUE_MAX_PRIORITY = 255
EXTRACTION_JOB_QUEUE_ARGUMENTS: dict[str, int] = {"x-max-priority": JOB_QUEUE_MAX_PRIORITY}

ALLOWED_UPLOAD_SUFFIXES = frozenset(
    {
        ".pdf", ".docx", ".doc", ".odt", ".xlsx", ".xls", ".ods", ".csv",
        ".pptx", ".ppt", ".odp", ".eml", ".msg", ".html", ".htm", ".xml",
        ".md", ".json", ".txt", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
    }
)


class InvalidJobPriorityError(ValueError):
    pass


def validate_extraction_job_priority_value(priority: object) -> int:
    if priority is None:
        return 0
    if type(priority) is not int or not 0 <= priority <= JOB_QUEUE_MAX_PRIORITY:
        raise InvalidJobPriorityError("priority must be an integer 0..255")
    return priority


def parse_extraction_job_priority(msg: dict[str, Any]) -> int:
    return validate_extraction_job_priority_value(msg.get("priority"))


def parse_upload_priority_query(raw: str | None) -> int:
    if raw is None or not raw.strip():
        return 0
    try:
        value = int(raw.strip(), 10)
    except ValueError:
        raise InvalidJobPriorityError("priority must be an integer 0..255") from None
    return validate_extraction_job_priority_value(value)


def new_job_id() -> str:
    return str(uuid.uuid4())


def safe_client_filename(raw: str) -> str:
    name = PurePosixPath(raw.replace("\\", "/")).name.strip()
    return name or "unknown"


def file_suffix_for_upload(filename: str) -> str:
    return PurePosixPath(safe_client_filename(filename)).suffix.lower()


def is_allowed_upload_suffix(suffix: str) -> bool:
    return suffix in ALLOWED_UPLOAD_SUFFIXES


def input_relative_path(job_id: str, file_suffix: str, *, now: datetime | None = None) -> str:
    when = now or datetime.now(UTC)
    return (
        f"input/{when.year}/{when.month:02d}/{when.day:02d}/{when.hour:02d}/"
        f"{job_id}{file_suffix.lower()}"
    )


def job_payload_dict(
    job_id: str,
    filename: str,
    source_path: str,
    *,
    options: dict[str, Any] | None = None,
    priority: object = 0,
    llm_profile: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "filename": filename,
        "source_path": source_path,
        "options": options or {},
        "priority": validate_extraction_job_priority_value(priority),
    }
    if llm_profile:
        payload["llm_profile"] = llm_profile
    return payload


def job_payload_bytes(
    job_id: str,
    filename: str,
    source_path: str,
    *,
    options: dict[str, Any] | None = None,
    priority: object = 0,
    llm_profile: str = "",
) -> bytes:
    return json.dumps(
        job_payload_dict(
            job_id,
            filename,
            source_path,
            options=options,
            priority=priority,
            llm_profile=llm_profile,
        ),
        separators=(",", ":"),
    ).encode()
