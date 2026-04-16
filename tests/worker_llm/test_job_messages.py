"""Tests for LLM worker job message payloads."""

from __future__ import annotations

import json

from docrunr_worker_llm.job_messages import (
    llm_job_payload_bytes,
    llm_job_payload_dict,
    new_job_id,
)


def test_new_job_id_is_uuid() -> None:
    jid = new_job_id()
    assert len(jid) == 36
    assert jid.count("-") == 4


def test_llm_job_payload_dict_shape() -> None:
    payload = llm_job_payload_dict(
        job_id="j1",
        extract_job_id="e1",
        filename="test.pdf",
        source_path="input/2026/04/15/00/j1.pdf",
        chunks_path="output/2026/04/15/00/j1.json",
        llm_profile="embed-local",
    )
    assert payload["job_id"] == "j1"
    assert payload["extract_job_id"] == "e1"
    assert payload["filename"] == "test.pdf"
    assert payload["source_path"] == "input/2026/04/15/00/j1.pdf"
    assert payload["chunks_path"] == "output/2026/04/15/00/j1.json"
    assert payload["llm_profile"] == "embed-local"
    assert payload["priority"] == 0
    assert payload["metadata"] == {}


def test_llm_job_payload_bytes_roundtrip() -> None:
    raw = llm_job_payload_bytes(
        job_id="j2",
        extract_job_id="e2",
        filename="doc.docx",
        source_path="input/2026/04/15/01/j2.docx",
        chunks_path="output/2026/04/15/01/j2.json",
        llm_profile="text-embedding-ada-002",
    )
    parsed = json.loads(raw)
    assert parsed["job_id"] == "j2"
    assert parsed["extract_job_id"] == "e2"
    assert parsed["llm_profile"] == "text-embedding-ada-002"
    assert parsed["priority"] == 0
    assert parsed["metadata"] == {}


def test_llm_job_payload_with_metadata_and_priority() -> None:
    payload = llm_job_payload_dict(
        job_id="j3",
        extract_job_id="e3",
        filename="info.pdf",
        source_path="input/j3.pdf",
        chunks_path="output/j3.json",
        llm_profile="embed-local",
        priority=10,
        metadata={"tenant": "acme"},
    )
    assert payload["metadata"] == {"tenant": "acme"}
    assert payload["priority"] == 10
    assert payload["llm_profile"] == "embed-local"
