"""Tests for extraction handlers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from docrunr.models import Chunk, Result
from docrunr_worker.handler import (
    _derive_output_prefix,
    handle_extract_job,
    handle_job,
    parse_job_request_from_body,
)
from docrunr_worker.storage import LocalStorage


def test_parse_malformed_distinct_delivery_ids_yield_distinct_job_ids() -> None:
    body = b"{}"
    a = parse_job_request_from_body(body, delivery_id="delivery-a").job_id
    b = parse_job_request_from_body(body, delivery_id="delivery-b").job_id
    assert a != b
    assert a.endswith("-delivery-a")
    assert b.endswith("-delivery-b")


class TestDeriveOutputPrefix:
    def test_standard_path(self) -> None:
        result = _derive_output_prefix("input/2026/03/15/14/abc123.pdf")
        assert result == "output/2026/03/15/14/abc123"

    def test_legacy_year_month_partition_still_derives_output(self) -> None:
        result = _derive_output_prefix("input/2025/12/deadbeef.docx")
        assert result == "output/2025/12/deadbeef"

    def test_strips_extension(self) -> None:
        result = _derive_output_prefix("input/2026/01/05/09/uuid-here.html")
        assert result == "output/2026/01/05/09/uuid-here"

    def test_requires_input_prefix(self) -> None:
        with pytest.raises(ValueError):
            _derive_output_prefix("uploads/2026/01/05/09/uuid-here.html")

    def test_rejects_parent_segments(self) -> None:
        with pytest.raises(ValueError):
            _derive_output_prefix("input/2026/01/05/09/../../etc/passwd")


def _ok_result(source: str = "j1.pdf") -> Result:
    return Result(
        source=source,
        markdown="# hello",
        chunks=[
            Chunk(
                chunk_id="chunk_1",
                source_doc_id="doc_1",
                chunk_index=0,
                text="hello world",
                token_count=2,
                char_count=11,
                splitter_version="recursive_v1_token300_overlap0",
            )
        ],
        total_tokens=2,
        mime_type="application/pdf",
        size_bytes=4,
    )


def test_handle_job_returns_error_when_convert_returns_failed_result(tmp_path: Path) -> None:
    base = tmp_path / "data"
    (base / "input/2026/03/15/14").mkdir(parents=True)
    (base / "input/2026/03/15/14/j1.pdf").write_bytes(b"%PDF-1.4 minimal")
    storage = LocalStorage(str(base))
    body = json.dumps(
        {
            "job_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "filename": "j1.pdf",
            "source_path": "input/2026/03/15/14/j1.pdf",
            "options": {},
        }
    ).encode()
    bad = Result(source="j1.pdf", error="All parsers failed for j1.pdf")
    with patch("docrunr_worker.handler.convert", return_value=bad):
        out = handle_job(body, storage, timeout=120)
    row = json.loads(out)
    assert row["status"] == "error"
    assert row["markdown_path"] is None
    assert "All parsers failed" in (row.get("error") or "")
    assert row.get("mime_type") == ""
    assert row.get("size_bytes") == 0
    assert row.get("priority") == 0
    assert not (base / "output/2026/03/15/14/j1.md").exists()


def test_handle_job_returns_error_for_invalid_json(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    body = b"{not-json"
    out = handle_job(body, storage, timeout=120)
    row = json.loads(out)
    assert row["status"] == "error"
    assert row["job_id"] == parse_job_request_from_body(body).job_id
    assert row["job_id"].startswith("malformed-")
    assert row["source_path"] == "unknown"
    assert row["error"]
    assert row.get("priority") == 0


def test_handle_job_returns_error_for_missing_required_fields(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    body = json.dumps({"job_id": "abc"}).encode()
    out = handle_job(body, storage, timeout=120)
    row = json.loads(out)
    assert row["status"] == "error"
    assert row["job_id"] == parse_job_request_from_body(body).job_id
    assert row["job_id"].startswith("malformed-")
    assert row["source_path"] == "unknown"
    assert "source_path" in str(row["error"])
    assert row.get("priority") == 0


def test_handle_job_rejects_invalid_priority_payload(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    body = json.dumps(
        {
            "job_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "filename": "j1.pdf",
            "source_path": "input/2026/03/15/14/j1.pdf",
            "options": {},
            "priority": 300,
        }
    ).encode()
    out = handle_job(body, storage, timeout=120)
    row = json.loads(out)
    assert row["status"] == "error"
    assert str(row["job_id"]).startswith("malformed-")


def test_handle_extract_job_writes_markdown_and_chunks(tmp_path: Path) -> None:
    base = tmp_path / "data"
    (base / "input/2026/03/15/14").mkdir(parents=True)
    (base / "input/2026/03/15/14/job1.pdf").write_bytes(b"test")
    storage = LocalStorage(str(base))
    body = json.dumps(
        {
            "job_id": "job-1",
            "filename": "job1.pdf",
            "source_path": "input/2026/03/15/14/job1.pdf",
            "options": {"some_option": 500},
            "priority": 240,
        }
    ).encode()

    with patch("docrunr_worker.handler.convert", return_value=_ok_result("job1.pdf")):
        out = handle_extract_job(
            body=body,
            storage=storage,
            timeout=120,
        )

    row = json.loads(out.result_json)
    assert row["status"] == "ok"
    assert row["markdown_path"] == "output/2026/03/15/14/job1.md"
    assert row["chunks_path"] == "output/2026/03/15/14/job1.json"
    assert row["mime_type"] == "application/pdf"
    assert row["size_bytes"] == 4
    assert row["priority"] == 240


def test_handle_extract_job_rejects_non_object_options(tmp_path: Path) -> None:
    storage = LocalStorage(str(tmp_path))
    body = json.dumps(
        {
            "job_id": "job-1",
            "filename": "job1.pdf",
            "source_path": "input/2026/03/15/14/job1.pdf",
            "options": True,
        }
    ).encode()

    out = handle_extract_job(
        body=body,
        storage=storage,
        timeout=120,
    )

    row = json.loads(out.result_json)
    assert row["status"] == "error"
    assert str(row["job_id"]).startswith("malformed-")
    assert "options must be a JSON object" in str(row["error"])
