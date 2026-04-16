"""RabbitMQ + staging helpers for integration tests (host talks to docker-published ports)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

import pika
from docrunr_worker.job_messages import (
    EXTRACTION_JOB_QUEUE_ARGUMENTS,
    job_payload_bytes,
)
from pika.adapters.blocking_connection import BlockingChannel

DEFAULT_JOBS_QUEUE = "docrunr.jobs"
DEFAULT_RESULTS_QUEUE = "docrunr.results"
DEFAULT_LLM_JOBS_QUEUE = "docrunr.llm.jobs"
DEFAULT_LLM_RESULTS_QUEUE = "docrunr.llm.results"
DEFAULT_LLM_DLQ_QUEUE = "docrunr.llm.dlq"


def rabbitmq_params(timeout_sec: float = 3.0) -> pika.ConnectionParameters:
    host = os.environ.get("RABBITMQ_HOST", "127.0.0.1")
    port = int(os.environ.get("RABBITMQ_PORT", "5672"))
    user = os.environ.get("RABBITMQ_USER", "guest")
    password = os.environ.get("RABBITMQ_PASSWORD", "guest")
    credentials = pika.PlainCredentials(user, password)
    return pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=timeout_sec,
        socket_timeout=timeout_sec,
    )


def try_connect_rabbitmq(timeout_sec: float = 3.0) -> bool:
    try:
        conn = pika.BlockingConnection(rabbitmq_params(timeout_sec=timeout_sec))
        conn.close()
        return True
    except Exception:
        return False


def try_worker_health(url: str | None = None, timeout_sec: float = 2.0) -> bool:
    u = url or os.environ.get("DOCRUNR_HEALTH_URL", "http://127.0.0.1:8080/health")
    try:
        with urllib.request.urlopen(u, timeout=timeout_sec) as resp:
            return int(resp.status) == 200
    except (urllib.error.URLError, OSError):
        return False


def try_worker_llm_health(url: str | None = None, timeout_sec: float = 2.0) -> bool:
    u = url or os.environ.get("DOCRUNR_LLM_HEALTH_URL", "http://127.0.0.1:8081/health")
    try:
        with urllib.request.urlopen(u, timeout=timeout_sec) as resp:
            return int(resp.status) == 200
    except (urllib.error.URLError, OSError):
        return False


def open_channel() -> tuple[pika.BlockingConnection, BlockingChannel]:
    conn = pika.BlockingConnection(rabbitmq_params())
    ch = conn.channel()
    return conn, ch


def declare_queues(
    ch: BlockingChannel,
    jobs_queue: str = DEFAULT_JOBS_QUEUE,
    results_queue: str = DEFAULT_RESULTS_QUEUE,
) -> None:
    ch.queue_declare(
        queue=jobs_queue,
        durable=True,
        arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS,
    )
    ch.queue_declare(queue=results_queue, durable=True)


def purge_queues(
    ch: BlockingChannel,
    jobs_queue: str = DEFAULT_JOBS_QUEUE,
    results_queue: str = DEFAULT_RESULTS_QUEUE,
) -> None:
    """Clear queues (local integration only — do not point at production)."""
    ch.queue_purge(jobs_queue)
    ch.queue_purge(results_queue)


def declare_llm_queues(
    ch: BlockingChannel,
    llm_jobs_queue: str = DEFAULT_LLM_JOBS_QUEUE,
    llm_results_queue: str = DEFAULT_LLM_RESULTS_QUEUE,
    llm_dlq_queue: str = DEFAULT_LLM_DLQ_QUEUE,
) -> None:
    ch.queue_declare(queue=llm_jobs_queue, durable=True)
    ch.queue_declare(queue=llm_results_queue, durable=True)
    ch.queue_declare(queue=llm_dlq_queue, durable=True)


def purge_llm_queues(
    ch: BlockingChannel,
    llm_jobs_queue: str = DEFAULT_LLM_JOBS_QUEUE,
    llm_results_queue: str = DEFAULT_LLM_RESULTS_QUEUE,
    llm_dlq_queue: str = DEFAULT_LLM_DLQ_QUEUE,
) -> None:
    """Clear LLM queues (local integration only)."""
    ch.queue_purge(llm_jobs_queue)
    ch.queue_purge(llm_results_queue)
    ch.queue_purge(llm_dlq_queue)


def job_message_bytes(
    job_id: str,
    filename: str,
    source_path: str,
    *,
    priority: int = 0,
    llm_profile: str = "",
) -> bytes:
    """Serialize the job body published to ``docrunr.jobs`` (see SPEC.md)."""
    return job_payload_bytes(
        job_id, filename, source_path, priority=priority, llm_profile=llm_profile
    )


def publish_job(
    ch: BlockingChannel,
    body: bytes,
    queue: str = DEFAULT_JOBS_QUEUE,
    *,
    priority: int = 0,
) -> None:
    ch.basic_publish(
        exchange="",
        routing_key=queue,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, priority=int(priority)),
    )


def collect_results_for(
    ch: BlockingChannel,
    expected_ids: set[str],
    *,
    results_queue: str = DEFAULT_RESULTS_QUEUE,
    id_field: str = "job_id",
    timeout_sec: float = 600.0,
    poll_interval_sec: float = 0.25,
) -> dict[str, dict[str, Any]]:
    """Drain ``results_queue`` until all ``expected_ids`` are seen or timeout.

    Results are keyed by ``id_field`` (default ``job_id``).  Use
    ``id_field="extract_job_id"`` for LLM results so they key back to the
    originating extraction job.

    Unknown result messages are acknowledged and ignored so they cannot block
    queue progress for this test run.
    """
    results: dict[str, dict[str, Any]] = {}
    deadline = time.monotonic() + timeout_sec
    while len(results) < len(expected_ids) and time.monotonic() < deadline:
        method, _props, body = ch.basic_get(results_queue, auto_ack=False)
        if method is None:
            time.sleep(poll_interval_sec)
            continue
        try:
            data = json.loads(body.decode())
            jid = str(data.get(id_field, ""))
            if jid in expected_ids:
                results[jid] = data
            ch.basic_ack(method.delivery_tag)
        except Exception:
            ch.basic_nack(method.delivery_tag, requeue=True)
            raise
    return results
