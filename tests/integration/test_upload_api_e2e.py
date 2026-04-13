"""POST ``/api/uploads`` against a running worker (docker compose)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.integration.integration_storage import IntegrationStorage
from tests.integration.rmq_helpers import (
    collect_results_for,
    declare_queues,
    open_channel,
    purge_queues,
    try_connect_rabbitmq,
    try_worker_health,
)

pytestmark = pytest.mark.integration


def _upload_api_url() -> str:
    health = os.environ.get("DOCRUNR_HEALTH_URL", "http://127.0.0.1:8080/health")
    base = health.rsplit("/", 1)[0]
    return f"{base}/api/uploads"


def _multipart_body(boundary: str, filename: str, content: bytes) -> bytes:
    b = boundary.encode("ascii")
    return b"".join(
        [
            b"--" + b + b"\r\n",
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode(),
            b"\r\n",
            content,
            b"\r\n--" + b + b"--\r\n",
        ]
    )


def _results_timeout_seconds(job_count: int) -> float:
    raw_override = os.environ.get("INTEGRATION_RESULTS_TIMEOUT_SEC")
    if raw_override is not None and raw_override.strip():
        return float(raw_override)
    per_job = float(os.environ.get("INTEGRATION_RESULTS_TIMEOUT_PER_JOB_SEC", "12"))
    return max(600.0, job_count * per_job)


def _require_services() -> None:
    if not try_connect_rabbitmq():
        pytest.skip(
            "RabbitMQ not reachable (start with: docker compose up -d, or base+local / base+minio)"
        )
    if not try_worker_health():
        pytest.skip(
            "Worker health not reachable (expects DOCRUNR_HEALTH_URL or http://127.0.0.1:8080/health)"
        )


def test_upload_api_post_stores_file_and_worker_processes(
    resolved_worker_e2e_samples: list[Path],
    integration_storage: IntegrationStorage,
) -> None:
    _require_services()
    if not resolved_worker_e2e_samples:
        pytest.skip("No integration samples")

    sample = resolved_worker_e2e_samples[0]
    integration_storage.clear()

    conn, ch = open_channel()
    try:
        declare_queues(ch)
        purge_queues(ch)

        boundary = "----docrunrUploadE2E"
        body = _multipart_body(boundary, sample.name, sample.read_bytes())
        req = urllib.request.Request(
            _upload_api_url(),
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                assert resp.status == 202
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise AssertionError(f"Upload failed: {exc.code} {exc.read()!r}") from exc

        items = payload.get("items")
        assert isinstance(items, list) and len(items) == 1
        row = items[0]
        assert row.get("status") == "queued"
        job_id = str(row.get("job_id", ""))
        source_path = str(row.get("source_path", ""))
        assert job_id and source_path.startswith("input/")

        assert integration_storage.exists(source_path), f"Expected upload object at {source_path}"

        timeout_sec = _results_timeout_seconds(1)
        results = collect_results_for(ch, {job_id}, timeout_sec=timeout_sec)
        assert job_id in results
        assert results[job_id].get("job_id") == job_id

        outcome = results[job_id]
        status = outcome.get("status")
        assert status in ("ok", "error"), f"Unexpected status: {outcome!r}"
        if status == "ok":
            mp = outcome.get("markdown_path")
            cp = outcome.get("chunks_path")
            assert isinstance(mp, str) and integration_storage.exists(mp), f"Missing {mp!r}"
            assert isinstance(cp, str) and integration_storage.exists(cp), f"Missing {cp!r}"
        else:
            mp = outcome.get("markdown_path")
            cp = outcome.get("chunks_path")
            assert mp is None and cp is None
    finally:
        conn.close()
