"""Publish jobs to RabbitMQ and assert the docker worker writes results to configured storage.

Prerequisites (pick one stack)::

    docker compose up -d --build
    docker compose -f docker-compose.base.yml -f docker-compose.local.yml up -d --build
    docker compose -f docker-compose.base.yml -f docker-compose.llm.yml \\
        -f docker-compose.ollama.yml -f docker-compose.minio.yml up -d --build

Tests run on the host: RabbitMQ on ``127.0.0.1:5672``, worker health on ``8080``.
Storage assertions use ``DOCRUNR_INTEGRATION_STORAGE`` (``local`` or ``minio``) so they
match the running compose overlay.

Override with ``RABBITMQ_HOST``, ``DOCRUNR_HEALTH_URL`` if needed.
For MinIO mode, set ``DOCRUNR_INTEGRATION_MINIO_ENDPOINT`` (default ``127.0.0.1:9000``)
and the same ``MINIO_*`` credentials as in ``.env``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from docrunr_worker.handler import _derive_output_prefix
from docrunr_worker.job_messages import new_job_id

from tests.integration.integration_storage import IntegrationStorage
from tests.integration.reporting import emit_integration_report
from tests.integration.rmq_helpers import (
    collect_results_for,
    declare_queues,
    job_message_bytes,
    open_channel,
    publish_job,
    purge_queues,
    try_connect_rabbitmq,
    try_worker_health,
)

pytestmark = pytest.mark.integration


def _results_timeout_seconds(job_count: int) -> float:
    raw_override = os.environ.get("INTEGRATION_RESULTS_TIMEOUT_SEC")
    if raw_override is not None and raw_override.strip():
        return float(raw_override)
    per_job = float(os.environ.get("INTEGRATION_RESULTS_TIMEOUT_PER_JOB_SEC", "12"))
    return max(600.0, job_count * per_job)


def _require_services() -> None:
    if not try_connect_rabbitmq():
        pytest.skip(
            "RabbitMQ not reachable at RABBITMQ_HOST / RABBITMQ_PORT "
            "(start with: docker compose up -d, or base+local / base+minio overlays)"
        )
    if not try_worker_health():
        pytest.skip(
            "Worker health not reachable (start worker with compose; "
            "expects DOCRUNR_HEALTH_URL or http://127.0.0.1:8080/health)"
        )


def test_worker_processes_jobs_end_to_end(
    resolved_worker_e2e_samples: list[Path],
    integration_storage: IntegrationStorage,
) -> None:
    """Stage N samples, publish N jobs, wait for N results.

    Per-job conversion may succeed or fail; the test only requires one result message per job
    and storage consistent with that result (outputs only when ``status`` is ``ok``).
    """
    _require_services()
    samples = resolved_worker_e2e_samples
    assert samples, "No samples (check --integration-sample-limit and GLOB_PATTERNS)"

    integration_storage.clear()

    conn, ch = open_channel()
    try:
        declare_queues(ch)
        purge_queues(ch)

        staged: list[tuple[str, str, Path]] = []
        expected: set[str] = set()
        for sample in samples:
            job_id = new_job_id()
            rel = integration_storage.stage_input(sample, job_id)
            expected.add(job_id)
            staged.append((job_id, rel, sample))

        for job_id, rel, sample in staged:
            body = job_message_bytes(job_id, sample.name, rel)
            publish_job(ch, body)

        timeout_sec = _results_timeout_seconds(len(expected))
        results = collect_results_for(ch, expected, timeout_sec=timeout_sec)
    finally:
        conn.close()

    assert len(results) == len(expected), (
        f"Timed out waiting for results after {timeout_sec:.1f}s: "
        f"got {len(results)}/{len(expected)} "
        f"(check worker logs: docker compose logs worker -f)"
    )

    ok_count = 0
    for job_id, rel, _sample in staged:
        row = results[job_id]
        status = row.get("status")
        assert status in ("ok", "error"), f"Unexpected status for {job_id}: {row!r}"
        prefix = _derive_output_prefix(rel)
        md_key = f"{prefix}.md"
        json_key = f"{prefix}.json"
        if status == "ok":
            ok_count += 1
            assert integration_storage.exists(md_key), f"Missing markdown for {job_id}: {md_key}"
            assert integration_storage.exists(json_key), (
                f"Missing chunks json for {job_id}: {json_key}"
            )
        else:
            assert row.get("markdown_path") is None and row.get("chunks_path") is None
            assert not integration_storage.exists(md_key), (
                f"Unexpected markdown for failed job {job_id}"
            )
            assert not integration_storage.exists(json_key), (
                f"Unexpected json for failed job {job_id}"
            )

    n = len(samples)
    assert integration_storage.count_inputs() == n, (
        f"Expected {n} staged input object(s), found {integration_storage.count_inputs()}"
    )
    out_count = integration_storage.count_outputs()
    assert out_count == 2 * ok_count, (
        f"Expected {ok_count} ok job(s) × 2 output files = {2 * ok_count}, found {out_count}"
    )

    emit_integration_report(integration_storage.report_dir, staged, results)
