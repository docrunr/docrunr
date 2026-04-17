"""HTTP upload orchestration: multipart parse, temp staging, storage write, queue publish."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docrunr_worker.job_messages import (
    file_suffix_for_upload,
    input_relative_path,
    is_allowed_upload_suffix,
    job_payload_bytes,
    new_job_id,
    safe_client_filename,
    validate_extraction_job_priority_value,
)
from docrunr_worker.publisher import publish_durable_bytes

if TYPE_CHECKING:
    from docrunr_worker.config import WorkerSettings
    from docrunr_worker.storage import StorageBackend

logger = logging.getLogger(__name__)

_FIELD_NAME_RE = re.compile(r'\bname="([^"]*)"', re.IGNORECASE)
_FIELD_FILENAME_QUOTED_RE = re.compile(r'\bfilename="((?:\\.|[^"\\])*)"', re.IGNORECASE)
_FIELD_FILENAME_BARE_RE = re.compile(r"\bfilename=([^;\s]+)", re.IGNORECASE)


def _parse_boundary(content_type: str | None) -> bytes:
    if not content_type or "multipart/form-data" not in content_type.lower():
        raise ValueError("Expected multipart/form-data")
    for segment in content_type.split(";")[1:]:
        segment = segment.strip()
        if segment.lower().startswith("boundary="):
            raw = segment.split("=", 1)[1].strip()
            if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
                raw = raw[1:-1]
            return raw.encode("utf-8")
    raise ValueError("Missing multipart boundary")


def _filename_from_disposition(line: str) -> str | None:
    quoted = _FIELD_FILENAME_QUOTED_RE.search(line)
    if quoted:
        return quoted.group(1)
    bare = _FIELD_FILENAME_BARE_RE.search(line)
    if bare:
        value = bare.group(1).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return value
    return None


def _parse_content_disposition_headers(header_blob: str) -> tuple[str | None, str | None]:
    field_name: str | None = None
    filename: str | None = None
    for line in header_blob.splitlines():
        if not line.lower().lstrip().startswith("content-disposition:"):
            continue
        name_m = _FIELD_NAME_RE.search(line)
        if name_m:
            field_name = name_m.group(1)
        fn = _filename_from_disposition(line)
        if fn is not None:
            filename = fn
    return field_name, filename


def parse_multipart_file_parts(body: bytes, content_type: str | None) -> list[tuple[str, bytes]]:
    """Return ``(client_filename, raw_bytes)`` for each file field named ``files`` or ``file``."""
    boundary = _parse_boundary(content_type)
    delimiter = b"--" + boundary
    raw_parts = body.split(delimiter)
    out: list[tuple[str, bytes]] = []
    for part in raw_parts:
        if not part:
            continue
        chunk = part
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        if chunk.startswith(b"--"):
            continue
        sep = b"\r\n\r\n"
        idx = chunk.find(sep)
        if idx == -1:
            sep = b"\n\n"
            idx = chunk.find(sep)
        if idx == -1:
            continue
        try:
            header_text = chunk[:idx].decode("utf-8")
        except UnicodeDecodeError:
            continue
        payload = chunk[idx + len(sep) :]
        if payload.endswith(b"\r\n"):
            payload = payload[:-2]
        elif payload.endswith(b"\n"):
            payload = payload[:-1]
        name, filename = _parse_content_disposition_headers(header_text)
        if name not in {"files", "file"}:
            continue
        if not filename:
            continue
        out.append((filename, payload))
    return out


def _write_temp_file(content: bytes, *, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or "") as tmp:
        tmp.write(content)
        return Path(tmp.name)


def process_upload_request(
    *,
    body: bytes,
    content_type: str | None,
    storage: StorageBackend,
    settings: WorkerSettings,
    priority: int = 0,
    llm_profile: str = "",
) -> dict[str, Any]:
    """Parse multipart body, stage files, write to storage, publish jobs.

    Response shape: ``{"items": [...]}``.
    """
    validate_extraction_job_priority_value(priority)
    try:
        file_parts = parse_multipart_file_parts(body, content_type)
    except ValueError as exc:
        raise UploadRequestError(str(exc)) from exc

    if not file_parts:
        raise UploadRequestError('No file parts found (use form field name "files")')

    items: list[dict[str, Any]] = []
    queue_name = settings.rabbitmq_queue

    for raw_filename, content in file_parts:
        display_name = safe_client_filename(raw_filename)
        suffix = file_suffix_for_upload(raw_filename)
        if not suffix or not is_allowed_upload_suffix(suffix):
            items.append(
                {
                    "filename": display_name,
                    "status": "error",
                    "error": "Unsupported or missing file extension",
                }
            )
            continue
        if not content:
            items.append(
                {
                    "filename": display_name,
                    "status": "error",
                    "error": "Empty file",
                }
            )
            continue

        job_id = new_job_id()
        source_path = input_relative_path(job_id, suffix)
        tmp_path = _write_temp_file(content, suffix=suffix)
        try:
            storage.write(tmp_path, source_path)
        except Exception:
            logger.exception("Storage write failed for upload filename=%s", display_name)
            items.append(
                {
                    "filename": display_name,
                    "status": "error",
                    "error": "Failed to store file",
                }
            )
            continue
        finally:
            tmp_path.unlink(missing_ok=True)

        payload = job_payload_bytes(job_id, display_name, source_path, priority=priority, llm_profile=llm_profile)
        try:
            publish_durable_bytes(
                settings=settings,
                queue_name=queue_name,
                body=payload,
                priority=priority,
            )
        except Exception:
            logger.exception("Publish failed for job_id=%s; removing stored input", job_id)
            try:
                storage.delete(source_path)
            except Exception:
                logger.debug("Cleanup after failed publish", exc_info=True)
            items.append(
                {
                    "filename": display_name,
                    "status": "error",
                    "error": "Failed to queue job for processing",
                }
            )
            continue

        items.append(
            {
                "job_id": job_id,
                "filename": display_name,
                "source_path": source_path,
                "status": "queued",
                "priority": int(priority),
            }
        )

    return {"items": items}


class UploadRequestError(ValueError):
    """Invalid upload HTTP body or headers."""
