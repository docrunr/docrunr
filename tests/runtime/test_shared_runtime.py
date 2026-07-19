from __future__ import annotations

from datetime import UTC, datetime

import pytest
from docrunr_runtime.messages import (
    InvalidJobPriorityError,
    input_relative_path,
    job_payload_dict,
    safe_client_filename,
)
from docrunr_runtime.storage import LocalStorage


def test_job_contract_and_paths_are_stable() -> None:
    now = datetime(2026, 7, 19, 10, tzinfo=UTC)
    assert input_relative_path("job-id", ".PDF", now=now) == ("input/2026/07/19/10/job-id.pdf")
    assert safe_client_filename("../../secret/report.pdf") == "report.pdf"
    assert (
        job_payload_dict("job-id", "report.pdf", "input/report.pdf", llm_profile="embed")[
            "llm_profile"
        ]
        == "embed"
    )


def test_priority_rejects_bool() -> None:
    with pytest.raises(InvalidJobPriorityError):
        job_payload_dict("id", "a.pdf", "input/a.pdf", priority=True)


def test_local_storage_prevents_path_escape(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    source = tmp_path / "source.txt"
    source.write_text("hello")
    storage.write(source, "input/job.txt")
    assert storage.read("input/job.txt").read_text() == "hello"
    with pytest.raises(ValueError):
        storage.read("../outside.txt")
