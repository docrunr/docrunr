"""Tests for upload multipart parsing and enqueue orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from docrunr_worker.config import WorkerSettings
from docrunr_worker.job_messages import InvalidJobPriorityError
from docrunr_worker.storage import LocalStorage
from docrunr_worker.uploads import (
    UploadRequestError,
    parse_multipart_file_parts,
    process_upload_request,
)


def _multipart_bytes(*, boundary: str, filename: str, content: bytes) -> tuple[bytes, str]:
    b = boundary.encode("ascii")
    body = b"".join(
        [
            b"--" + b + b"\r\n",
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content,
            b"\r\n--" + b + b"--\r\n",
        ]
    )
    ct = f'multipart/form-data; boundary="{boundary}"'
    return body, ct


def test_parse_multipart_extracts_files_field() -> None:
    body, ct = _multipart_bytes(boundary="----abc123", filename="doc.pdf", content=b"%PDF-1.4")
    parts = parse_multipart_file_parts(body, ct)
    assert parts == [("doc.pdf", b"%PDF-1.4")]


def test_parse_multipart_rejects_non_multipart() -> None:
    with pytest.raises(ValueError, match="multipart"):
        parse_multipart_file_parts(b"x", "text/plain")


def test_process_upload_queues_and_writes_storage(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_queue="docrunr.jobs",
    )
    body, ct = _multipart_bytes(boundary="b1", filename="hello.pdf", content=b"%PDF-1.4 test")
    with patch("docrunr_worker.uploads.publish_durable_bytes"):
        out = process_upload_request(body=body, content_type=ct, storage=storage, settings=settings)
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["status"] == "queued"
    assert item["job_id"]
    assert item["filename"] == "hello.pdf"
    assert str(item["source_path"]).startswith("input/")
    assert item["priority"] == 0
    assert (tmp_path / str(item["source_path"])).is_file()


def test_process_upload_rejects_bad_extension(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings()
    body, ct = _multipart_bytes(boundary="b2", filename="x.exe", content=b"MZ")
    out = process_upload_request(body=body, content_type=ct, storage=storage, settings=settings)
    assert out["items"][0]["status"] == "error"
    assert "extension" in str(out["items"][0]["error"]).lower()


def test_process_upload_empty_body_field_errors(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings()
    body, ct = _multipart_bytes(boundary="b3", filename="empty.pdf", content=b"")
    out = process_upload_request(body=body, content_type=ct, storage=storage, settings=settings)
    assert out["items"][0]["status"] == "error"


def test_process_upload_publish_failure_deletes_stored_file(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings()
    body, ct = _multipart_bytes(boundary="b4", filename="gone.pdf", content=b"%PDF")
    with patch(
        "docrunr_worker.uploads.publish_durable_bytes",
        side_effect=RuntimeError("broker down"),
    ):
        out = process_upload_request(body=body, content_type=ct, storage=storage, settings=settings)
    assert out["items"][0]["status"] == "error"
    assert "queue" in str(out["items"][0]["error"]).lower()
    # No leftover input files
    input_root = tmp_path / "input"
    assert not input_root.exists() or not any(input_root.rglob("*.pdf"))


def test_process_upload_no_parts_raises() -> None:
    storage = LocalStorage("/tmp")
    settings = WorkerSettings()
    body, ct = _multipart_bytes(boundary="b5", filename="n.pdf", content=b"x")
    # Wrong field name
    b = b"----b5"
    body = b"".join(
        [
            b"--" + b + b"\r\n",
            b'Content-Disposition: form-data; name="other"; filename="n.pdf"\r\n\r\n',
            b"x",
            b"\r\n--" + b + b"--\r\n",
        ]
    )
    with pytest.raises(UploadRequestError, match="No file parts"):
        process_upload_request(body=body, content_type=ct, storage=storage, settings=settings)


def test_publish_invokes_expected_payload(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings(rabbitmq_queue="docrunr.jobs")
    body, ct = _multipart_bytes(boundary="b6", filename="a.pdf", content=b"%PDF")
    captured: list[dict[str, object]] = []

    def _capture(**kwargs: object) -> None:
        captured.append(dict(kwargs))

    with patch("docrunr_worker.uploads.publish_durable_bytes", side_effect=_capture):
        out = process_upload_request(body=body, content_type=ct, storage=storage, settings=settings)
    assert out["items"][0]["status"] == "queued"
    msg = json.loads(captured[0]["body"].decode())  # type: ignore[index]
    assert msg["job_id"] == out["items"][0]["job_id"]
    assert msg["source_path"] == out["items"][0]["source_path"]
    assert msg["filename"] == "a.pdf"
    assert msg["options"] == {}
    assert msg["priority"] == 0
    assert captured[0]["priority"] == 0  # type: ignore[index]


def test_process_upload_rejects_out_of_range_priority(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings()
    body, ct = _multipart_bytes(boundary="b8", filename="z.pdf", content=b"%PDF")
    with pytest.raises(InvalidJobPriorityError):
        process_upload_request(
            body=body,
            content_type=ct,
            storage=storage,
            settings=settings,
            priority=400,
        )


def test_process_upload_passes_priority_to_payload_and_publish(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings(rabbitmq_queue="docrunr.jobs")
    body, ct = _multipart_bytes(boundary="b7", filename="p.pdf", content=b"%PDF")
    captured: list[dict[str, object]] = []

    def _capture(**kwargs: object) -> None:
        captured.append(dict(kwargs))

    with patch("docrunr_worker.uploads.publish_durable_bytes", side_effect=_capture):
        out = process_upload_request(
            body=body,
            content_type=ct,
            storage=storage,
            settings=settings,
            priority=42,
        )
    assert out["items"][0]["status"] == "queued"
    assert out["items"][0]["priority"] == 42
    msg = json.loads(captured[0]["body"].decode())  # type: ignore[index]
    assert msg["priority"] == 42
    assert captured[0]["priority"] == 42  # type: ignore[index]
