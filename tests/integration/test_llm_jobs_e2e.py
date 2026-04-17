"""Two-hop e2e: extraction with llm_profile → worker-llm embedding result.

Prerequisites::

    node ./scripts/dev.mjs --llm
    # or
    docker compose -f docker-compose.base.yml -f docker-compose.local.yml \
        -f docker-compose.llm.yml -f docker-compose.ollama.yml up -d --build

Tests run on the host: RabbitMQ on ``127.0.0.1:5672``, worker health on ``8080``,
worker-llm health on ``8081``.

Profile selection
~~~~~~~~~~~~~~~~~

By default a **random** profile is picked from the live LiteLLM ``/models`` list each run.

Narrow the pool via env vars:

- ``INTEGRATION_LLM_PROFILES=nomic-embed-text-137m,bge-m3-560m``  — allowlist
- ``INTEGRATION_LLM_PROFILES=nomic-embed-text-137m``              — pin one profile

The random pick draws from ``INTEGRATION_LLM_PROFILES`` (or all when empty).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from docrunr_worker.handler import _derive_output_prefix
from docrunr_worker.job_messages import new_job_id

from tests.integration.integration_storage import IntegrationStorage
from tests.integration.reporting import emit_integration_report
from tests.integration.rmq_helpers import (
    DEFAULT_LLM_RESULTS_QUEUE,
    collect_results_for,
    declare_llm_queues,
    declare_queues,
    job_message_bytes,
    open_channel,
    publish_job,
    purge_llm_queues,
    purge_queues,
    try_connect_rabbitmq,
    try_worker_health,
    try_worker_llm_health,
)

pytestmark = [pytest.mark.integration, pytest.mark.llm_jobs]


def _results_timeout_seconds(job_count: int) -> float:
    raw_override = os.environ.get("INTEGRATION_RESULTS_TIMEOUT_SEC")
    if raw_override is not None and raw_override.strip():
        return float(raw_override)
    per_job = float(os.environ.get("INTEGRATION_RESULTS_TIMEOUT_PER_JOB_SEC", "12"))
    return max(600.0, job_count * per_job)


def _llm_timeout_seconds(job_count: int) -> float:
    raw_override = os.environ.get("INTEGRATION_LLM_TIMEOUT_SEC")
    if raw_override is not None and raw_override.strip():
        return float(raw_override)
    per_job = float(os.environ.get("INTEGRATION_LLM_TIMEOUT_PER_JOB_SEC", "60"))
    return max(600.0, job_count * per_job)


def _require_services() -> None:
    if not try_connect_rabbitmq():
        pytest.skip(
            "RabbitMQ not reachable at RABBITMQ_HOST / RABBITMQ_PORT "
            "(start with: node ./scripts/dev.mjs --llm)"
        )
    if not try_worker_health():
        pytest.skip(
            "Worker health not reachable "
            "(expects DOCRUNR_HEALTH_URL or http://127.0.0.1:8080/health)"
        )
    if not try_worker_llm_health():
        pytest.skip(
            "Worker-LLM health not reachable "
            "(expects DOCRUNR_LLM_HEALTH_URL or http://127.0.0.1:8081/health)"
        )


def _print_llm_summary(
    staged: list[tuple[str, str, Path]],
    extraction_results: dict[str, dict[str, Any]],
    llm_results: dict[str, dict[str, Any]],
    llm_profile: str,
) -> None:
    ok_extractions = [jid for jid, r in extraction_results.items() if r.get("status") == "ok"]
    llm_ok = sum(1 for r in llm_results.values() if r.get("status") == "ok")
    line = "=" * 72
    print(f"\n{line}")
    print(
        f"LLM integration — {llm_ok}/{len(ok_extractions)} embeddings OK  "
        f"(profile: {llm_profile})"
    )
    print(line)
    header = f"{'#':>3}  {'filename':<36}  {'extract':<8}  {'llm':<8}  {'vectors':>7}"
    print(header)
    print("-" * len(header))
    for idx, (job_id, _rel, sample) in enumerate(staged, start=1):
        ext_row = extraction_results.get(job_id, {})
        ext_status = str(ext_row.get("status", "?"))
        llm_row = llm_results.get(job_id, {})
        llm_status = str(llm_row.get("status", "-"))
        vectors = llm_row.get("vector_count", "")
        name = sample.name
        if len(name) > 36:
            name = name[:33] + "..."
        print(f"{idx:>3}  {name:<36}  {ext_status:<8}  {llm_status:<8}  {vectors!s:>7}")
    print(line)


def test_extraction_with_llm_produces_embeddings(
    resolved_worker_e2e_samples: list[Path],
    integration_storage: IntegrationStorage,
    integration_llm_profile: str,
) -> None:
    """Stage N samples, publish with llm_profile, wait for extraction + LLM results."""
    _require_services()
    samples = resolved_worker_e2e_samples
    assert samples, "No samples (check --integration-sample-limit and GLOB_PATTERNS)"

    integration_storage.clear()

    conn, ch = open_channel()
    try:
        declare_queues(ch)
        declare_llm_queues(ch)
        purge_queues(ch)
        purge_llm_queues(ch)

        staged: list[tuple[str, str, Path]] = []
        expected: set[str] = set()
        for sample in samples:
            job_id = new_job_id()
            rel = integration_storage.stage_input(sample, job_id)
            expected.add(job_id)
            staged.append((job_id, rel, sample))

        for job_id, rel, sample in staged:
            body = job_message_bytes(job_id, sample.name, rel, llm_profile=integration_llm_profile)
            publish_job(ch, body)

        # Hop 1: collect extraction results
        ext_timeout = _results_timeout_seconds(len(expected))
        extraction_results = collect_results_for(ch, expected, timeout_sec=ext_timeout)

        assert len(extraction_results) == len(expected), (
            f"Timed out waiting for extraction results after {ext_timeout:.1f}s: "
            f"got {len(extraction_results)}/{len(expected)}"
        )

        ok_ids = {jid for jid, r in extraction_results.items() if r.get("status") == "ok"}

        if not ok_ids:
            pytest.skip(
                "All extractions failed — cannot verify LLM hop "
                "(check worker logs for extraction errors)"
            )

        # Hop 2: collect LLM results (keyed by extract_job_id → extraction job_id)
        llm_timeout = _llm_timeout_seconds(len(ok_ids))
        llm_results = collect_results_for(
            ch,
            ok_ids,
            results_queue=DEFAULT_LLM_RESULTS_QUEUE,
            id_field="extract_job_id",
            timeout_sec=llm_timeout,
        )
    finally:
        conn.close()

    assert len(llm_results) == len(ok_ids), (
        f"Timed out waiting for LLM results after {llm_timeout:.1f}s: "
        f"got {len(llm_results)}/{len(ok_ids)}"
    )

    # Assert extraction artifacts
    ok_count = 0
    for job_id, rel, _sample in staged:
        row = extraction_results[job_id]
        status = row.get("status")
        assert status in ("ok", "error"), f"Unexpected extraction status for {job_id}: {row!r}"
        prefix = _derive_output_prefix(rel)
        if status == "ok":
            ok_count += 1
            assert integration_storage.exists(f"{prefix}.md"), f"Missing markdown for {job_id}"
            assert integration_storage.exists(f"{prefix}.json"), f"Missing chunks json for {job_id}"

    # Assert LLM artifacts
    llm_ok_count = 0
    llm_errors: list[str] = []
    for job_id in ok_ids:
        llm_row = llm_results.get(job_id, {})
        llm_status = llm_row.get("status")
        assert llm_status in ("ok", "error"), (
            f"Unexpected LLM status for extract_job_id={job_id}: {llm_row!r}"
        )
        if llm_status == "ok":
            llm_ok_count += 1
            artifact_path = llm_row.get("artifact_path", "")
            assert artifact_path and integration_storage.exists(artifact_path), (
                f"Missing embeddings artifact for extract_job_id={job_id}: {artifact_path}"
            )
        else:
            llm_errors.append(str(llm_row.get("error", "unknown")))

    # Reports
    emit_integration_report(integration_storage.report_dir, staged, extraction_results)
    _print_llm_summary(staged, extraction_results, llm_results, integration_llm_profile)

    assert llm_ok_count > 0, (
        f"All {len(ok_ids)} LLM jobs failed — no embeddings produced.\n"
        f"First error: {llm_errors[0] if llm_errors else '?'}\n"
        f"Check: ollama list (is the embedding model pulled?), "
        f"LiteLLM logs, worker-llm logs."
    )
