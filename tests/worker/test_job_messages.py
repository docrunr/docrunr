"""Tests for centralized job message and input path helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from docrunr_worker.job_messages import (
    InvalidJobPriorityError,
    file_suffix_for_upload,
    input_relative_path,
    is_allowed_upload_suffix,
    job_payload_bytes,
    job_payload_dict,
    new_job_id,
    parse_extraction_job_priority,
    parse_upload_priority_query,
    safe_client_filename,
    validate_extraction_job_priority_value,
)


def test_new_job_id_is_uuid_v4_string() -> None:
    jid = new_job_id()
    parts = jid.split("-")
    assert len(parts) == 5
    assert len(parts[0]) == 8 and len(parts[-1]) == 12


def test_input_relative_path_uses_utc_hour_partition() -> None:
    fixed = datetime(2026, 3, 15, 14, 30, tzinfo=UTC)
    jid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert input_relative_path(jid, ".PDF", now=fixed) == f"input/2026/03/15/14/{jid}.pdf"


def test_job_payload_round_trip_shape() -> None:
    d = job_payload_dict("j1", "Report.pdf", "input/2026/03/15/14/j1.pdf")
    assert d == {
        "job_id": "j1",
        "filename": "Report.pdf",
        "source_path": "input/2026/03/15/14/j1.pdf",
        "options": {},
        "priority": 0,
    }
    raw = job_payload_bytes("j1", "Report.pdf", "input/2026/03/15/14/j1.pdf", priority=255)
    assert b'"job_id":"j1"' in raw
    assert b'"options":{}' in raw
    assert b'"priority":255' in raw


def test_parse_extraction_job_priority_defaults_and_bounds() -> None:
    assert parse_extraction_job_priority({}) == 0
    assert parse_extraction_job_priority({"priority": 0}) == 0
    assert parse_extraction_job_priority({"priority": 255}) == 255
    assert parse_extraction_job_priority({"priority": None}) == 0


def test_validate_extraction_job_priority_value_none() -> None:
    assert validate_extraction_job_priority_value(None) == 0


@pytest.mark.parametrize(
    "bad",
    [True, 1.5, "5", 256, -1],
)
def test_job_payload_dict_rejects_invalid_priority(bad: object) -> None:
    with pytest.raises(InvalidJobPriorityError):
        job_payload_dict("j", "f.pdf", "input/2026/04/11/14/j.pdf", priority=bad)


@pytest.mark.parametrize(
    "bad",
    [
        {"priority": -1},
        {"priority": 256},
        {"priority": 1.0},
        {"priority": "5"},
        {"priority": True},
    ],
)
def test_parse_extraction_job_priority_rejects_invalid(bad: dict) -> None:
    with pytest.raises(InvalidJobPriorityError):
        parse_extraction_job_priority(bad)


def test_parse_upload_priority_query() -> None:
    assert parse_upload_priority_query(None) == 0
    assert parse_upload_priority_query("") == 0
    assert parse_upload_priority_query("  ") == 0
    assert parse_upload_priority_query("0") == 0
    assert parse_upload_priority_query("255") == 255


@pytest.mark.parametrize("raw", ["x", "1.5", "256", "-1"])
def test_parse_upload_priority_query_rejects_invalid(raw: str) -> None:
    with pytest.raises(InvalidJobPriorityError):
        parse_upload_priority_query(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../x.pdf", "x.pdf"),
        (r"a\b\c.docx", "c.docx"),
        ("", "unknown"),
        ("  ", "unknown"),
    ],
)
def test_safe_client_filename(raw: str, expected: str) -> None:
    assert safe_client_filename(raw) == expected


def test_file_suffix_for_upload() -> None:
    assert file_suffix_for_upload("A.PDF") == ".pdf"
    assert file_suffix_for_upload(r"path\to\X.DOCX") == ".docx"


def test_is_allowed_upload_suffix() -> None:
    assert is_allowed_upload_suffix(".pdf") is True
    assert is_allowed_upload_suffix(".exe") is False
