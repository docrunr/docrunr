"""Tests for LLM RabbitMQ consumer (ack/nack, prefetch, parallel pool)."""

from __future__ import annotations

import json
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from docrunr_worker_llm.config import LlmWorkerSettings
from docrunr_worker_llm.consumer import Consumer
from docrunr_worker_llm.handler import LlmOutcome


def _llm_settings(*, worker_concurrency: int = 1) -> LlmWorkerSettings:
    return LlmWorkerSettings(
        rabbitmq_host="rabbitmq",
        rabbitmq_port=5672,
        rabbitmq_user="guest",
        rabbitmq_password="guest",
        rabbitmq_llm_queue="docrunr.llm.jobs",
        rabbitmq_llm_result_queue="docrunr.llm.results",
        rabbitmq_llm_dlq_queue="docrunr.llm.dlq",
        job_timeout_seconds=120,
        worker_concurrency=worker_concurrency,
    )


def _consumer(*, worker_concurrency: int = 1) -> Consumer:
    return Consumer(_llm_settings(worker_concurrency=worker_concurrency), storage=Mock())


def _job_body(*, job_id: str) -> bytes:
    return json.dumps(
        {
            "job_id": job_id,
            "extract_job_id": f"ext-{job_id}",
            "filename": f"{job_id}.pdf",
            "source_path": f"input/2026/04/11/14/{job_id}.pdf",
            "chunks_path": f"output/2026/04/11/14/{job_id}.json",
            "llm_profile": "embed-local",
        }
    ).encode()


def _llm_outcome(
    *,
    job_id: str = "job-1",
    status: str = "ok",
    duration_seconds: float = 1.25,
) -> LlmOutcome:
    result = {
        "job_id": job_id,
        "extract_job_id": f"ext-{job_id}",
        "status": status,
        "filename": f"{job_id}.pdf",
        "source_path": f"input/{job_id}.pdf",
        "chunks_path": f"output/{job_id}.json",
        "llm_profile": "embed-local",
        "provider": "openai",
        "chunk_count": 1,
        "vector_count": 1,
        "duration_seconds": duration_seconds,
        "artifact_path": None,
        "error": None,
    }
    return LlmOutcome(
        result_json=json.dumps(result),
        result=result,
        status=status,
        duration_seconds=duration_seconds,
    )


def test_start_registers_llm_queue() -> None:
    consumer = _consumer()
    channel = Mock()
    consumer._channel = channel  # type: ignore[attr-defined]

    consumer.start()

    queues = [c.kwargs["queue"] for c in channel.basic_consume.call_args_list]
    assert queues == ["docrunr.llm.jobs"]
    channel.start_consuming.assert_called_once()


def test_connect_declares_expected_queues_and_qos() -> None:
    with patch("docrunr_worker_llm.consumer.pika.BlockingConnection") as blocking_connection:
        consumer = _consumer(worker_concurrency=4)
        consumer.connect()
        params = blocking_connection.call_args.args[0]
        assert params.heartbeat == 150
        assert params.blocked_connection_timeout == 300
        declare_calls = consumer._channel.queue_declare.call_args_list  # type: ignore[union-attr]
        declared = [c.kwargs["queue"] for c in declare_calls]
        assert declared == ["docrunr.llm.jobs", "docrunr.llm.results", "docrunr.llm.dlq"]
        consumer._channel.basic_qos.assert_called_once_with(prefetch_count=4)  # type: ignore[union-attr]


def test_on_message_for_queue_delegates_to_llm_handler() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=1, redelivered=False)
    body = _job_body(job_id="delegated")

    with patch(
        "docrunr_worker_llm.consumer.handle_llm_job",
        return_value=_llm_outcome(job_id="delegated"),
    ) as handle:
        consumer._on_message_for_queue("docrunr.llm.jobs", channel, method, None, body)

    handle.assert_called_once()
    channel.basic_ack.assert_called_once_with(delivery_tag=1)


def test_llm_publishes_result_and_ack() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=42, redelivered=False)
    body = _job_body(job_id="job-1")

    with (
        patch("docrunr_worker_llm.consumer.stats.record_job") as record_job,
        patch(
            "docrunr_worker_llm.consumer.handle_llm_job",
            return_value=_llm_outcome(job_id="job-1"),
        ),
    ):
        consumer._on_llm_message("docrunr.llm.jobs", channel, method, body)

    channel.basic_publish.assert_called_once()
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "docrunr.llm.results"
    channel.basic_ack.assert_called_once_with(delivery_tag=42)
    terminal = [c.args[0] for c in record_job.call_args_list if c.args[0].get("status") == "ok"]
    assert len(terminal) == 1
    assert terminal[0]["job_id"] == "job-1"


def test_parallel_llm_completes_two_jobs_and_acks_independent_of_order() -> None:
    consumer = _consumer(worker_concurrency=2)
    consumer._connection = Mock(is_open=True)  # type: ignore[attr-defined]
    consumer._connection.add_callback_threadsafe.side_effect = lambda cb: cb()  # type: ignore[union-attr]
    consumer._executor = Mock()

    first_future: Future[LlmOutcome] = Future()
    second_future: Future[LlmOutcome] = Future()
    consumer._executor.submit.side_effect = [first_future, second_future]

    channel = Mock()
    method_one = SimpleNamespace(delivery_tag=11, redelivered=False)
    method_two = SimpleNamespace(delivery_tag=12, redelivered=False)

    with patch("docrunr_worker_llm.consumer.stats.record_job") as record_job:
        consumer._on_llm_message("docrunr.llm.jobs", channel, method_one, _job_body(job_id="job-1"))
        consumer._on_llm_message("docrunr.llm.jobs", channel, method_two, _job_body(job_id="job-2"))

        second_future.set_result(_llm_outcome(job_id="job-2", duration_seconds=2.0))
        first_future.set_result(_llm_outcome(job_id="job-1", duration_seconds=1.0))

    assert channel.basic_publish.call_count == 2
    assert {call.kwargs["routing_key"] for call in channel.basic_publish.call_args_list} == {
        "docrunr.llm.results"
    }
    assert channel.basic_ack.call_args_list == [
        call(delivery_tag=12),
        call(delivery_tag=11),
    ]
    terminal = [c.args[0] for c in record_job.call_args_list if c.args[0].get("status") == "ok"]
    assert [row["job_id"] for row in terminal] == ["job-2", "job-1"]
    assert [row["duration_seconds"] for row in terminal] == [2.0, 1.0]
    assert sum(1 for c in record_job.call_args_list if c.args[0].get("status") == "processing") == 2


def test_connect_failure_clears_rabbitmq_latch() -> None:
    from docrunr_worker_llm.health import stats as health_stats

    with patch(
        "docrunr_worker_llm.consumer.pika.BlockingConnection",
        side_effect=RuntimeError("refused"),
    ):
        consumer = _consumer()
        health_stats.rabbitmq_connected = True
        with pytest.raises(RuntimeError):
            consumer.connect()
        assert health_stats.rabbitmq_connected is False
