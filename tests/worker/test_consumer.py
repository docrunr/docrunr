"""Tests for consumer queue routing and ack/nack behavior."""

from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import ANY, Mock, call, patch

import pytest
from docrunr_worker.config import WorkerSettings
from docrunr_worker.consumer import Consumer
from docrunr_worker.handler import ExtractionOutcome


def _settings(*, worker_concurrency: int = 1) -> WorkerSettings:
    return WorkerSettings(
        rabbitmq_host="rabbitmq",
        rabbitmq_port=5672,
        rabbitmq_user="guest",
        rabbitmq_password="guest",
        rabbitmq_queue="docrunr.jobs",
        rabbitmq_result_queue="docrunr.results",
        rabbitmq_dlq_queue="docrunr.dlq",
        job_timeout_seconds=120,
        worker_concurrency=worker_concurrency,
    )


def _consumer(*, worker_concurrency: int = 1) -> Consumer:
    return Consumer(_settings(worker_concurrency=worker_concurrency), storage=Mock())


def _outcome(
    *,
    job_id: str = "job-1",
    status: str = "ok",
    duration_seconds: float = 1.25,
) -> ExtractionOutcome:
    result = {
        "job_id": job_id,
        "status": status,
        "duration_seconds": duration_seconds,
    }
    return ExtractionOutcome(
        result_json=f'{{"job_id":"{job_id}","status":"{status}","duration_seconds":{duration_seconds}}}',
        result=result,
        status=status,
        duration_seconds=duration_seconds,
    )


def test_start_registers_all_consumed_queues() -> None:
    consumer = _consumer()
    channel = Mock()
    consumer._channel = channel  # type: ignore[attr-defined]

    consumer.start()

    queues = [c.kwargs["queue"] for c in channel.basic_consume.call_args_list]
    assert queues == ["docrunr.jobs"]
    channel.start_consuming.assert_called_once()


def test_connect_failure_clears_rabbitmq_latch() -> None:
    from docrunr_worker.health import stats as health_stats

    with patch(
        "docrunr_worker.consumer.pika.BlockingConnection",
        side_effect=RuntimeError("refused"),
    ):
        consumer = _consumer()
        health_stats.rabbitmq_connected = True
        with pytest.raises(RuntimeError):
            consumer.connect()
        assert health_stats.rabbitmq_connected is False


def test_connect_declares_expected_queues() -> None:
    with patch("docrunr_worker.consumer.pika.BlockingConnection") as blocking_connection:
        consumer = _consumer(worker_concurrency=4)
        consumer.connect()
        params = blocking_connection.call_args.args[0]
        assert params.heartbeat == 150
        assert params.blocked_connection_timeout == 300
        declare_calls = consumer._channel.queue_declare.call_args_list  # type: ignore[union-attr]
        declared = [c.kwargs["queue"] for c in declare_calls]
        assert declared == ["docrunr.jobs", "docrunr.results", "docrunr.dlq"]
        assert declare_calls[0].kwargs.get("arguments") == {"x-max-priority": 255}
        assert declare_calls[1].kwargs.get("arguments") is None
        assert declare_calls[2].kwargs.get("arguments") is None
        consumer._channel.basic_qos.assert_called_once_with(prefetch_count=4)  # type: ignore[union-attr]


def test_extraction_publishes_result_and_ack() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=42, redelivered=False)

    with (
        patch("docrunr_worker.consumer.stats.record_job") as record_job,
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=_outcome(),
        ),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-1","source_path":"input/2026/04/11/14/a.pdf"}',
        )

    assert channel.basic_publish.call_args_list == [
        call(
            exchange="",
            routing_key="docrunr.results",
            body=b'{"job_id":"job-1","status":"ok","duration_seconds":1.25}',
            properties=ANY,
        )
    ]
    assert record_job.call_count == 2
    proc = record_job.call_args_list[0].args[0]
    assert proc["status"] == "processing"
    assert proc["job_id"] == "job-1"
    assert record_job.call_args_list[1].args[0] == {
        "job_id": "job-1",
        "status": "ok",
        "duration_seconds": 1.25,
    }
    channel.basic_ack.assert_called_once_with(delivery_tag=42)
    channel.basic_nack.assert_not_called()


def _assert_dlq_headers(channel: Mock, source_queue: str, reason: str) -> None:
    assert len(channel.basic_publish.call_args_list) == 2
    dlq_publish = channel.basic_publish.call_args_list[1]
    assert dlq_publish.kwargs["routing_key"] == "docrunr.dlq"
    props = dlq_publish.kwargs["properties"]
    assert props.headers["x-docrunr-source-queue"] == source_queue
    assert props.headers["x-docrunr-reason"] == reason
    datetime.fromisoformat(props.headers["x-docrunr-failed-at"])


def test_extraction_first_delivery_nacks_requeue_when_publish_fails() -> None:
    consumer = _consumer()
    channel = Mock()
    channel.basic_publish.side_effect = RuntimeError("publish failed")
    method = SimpleNamespace(delivery_tag=7, redelivered=False)

    with patch(
        "docrunr_worker.consumer.handle_extract_job",
        return_value=_outcome(job_id="job-2"),
    ):
        consumer._on_message_for_queue("docrunr.jobs", channel, method, None, b"{}")

    assert len(channel.basic_publish.call_args_list) == 1
    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=7, requeue=True)


def test_extraction_redelivery_dead_letters_and_acks_when_publish_fails() -> None:
    consumer = _consumer()
    channel = Mock()
    channel.basic_publish.side_effect = [RuntimeError("publish failed"), None]
    method = SimpleNamespace(delivery_tag=8, redelivered=True)

    with patch(
        "docrunr_worker.consumer.handle_extract_job",
        return_value=_outcome(job_id="job-2"),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-2","source_path":"input/2026/04/11/14/b.pdf"}',
        )

    _assert_dlq_headers(channel, "docrunr.jobs", "publish failed")
    channel.basic_ack.assert_called_once_with(delivery_tag=8)
    channel.basic_nack.assert_not_called()


def test_extraction_redelivery_nacks_requeue_when_dlq_publish_fails() -> None:
    consumer = _consumer()
    channel = Mock()
    channel.basic_publish.side_effect = [
        RuntimeError("publish failed"),
        RuntimeError("dlq publish failed"),
    ]
    method = SimpleNamespace(delivery_tag=9, redelivered=True)

    with patch(
        "docrunr_worker.consumer.handle_extract_job",
        return_value=_outcome(job_id="job-2"),
    ):
        consumer._on_message_for_queue("docrunr.jobs", channel, method, None, b"{}")

    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=9, requeue=True)


def test_extraction_records_error_when_result_json_is_not_an_object() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=99, redelivered=False)

    with (
        patch("docrunr_worker.consumer.stats.record_job") as record_job,
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=ExtractionOutcome(result_json='["not-an-object"]'),
        ),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-99","source_path":"input/2026/04/11/14/x.pdf"}',
        )

    assert record_job.call_count == 2
    assert record_job.call_args_list[0].args[0]["status"] == "processing"
    err = record_job.call_args_list[1].args[0]
    assert err["status"] == "error"
    assert err["job_id"] == "job-99"
    assert "non-object" in str(err.get("error", ""))
    channel.basic_ack.assert_called_once_with(delivery_tag=99)


def test_extraction_publish_failure_on_closed_channel_re_raises_without_nack() -> None:
    consumer = _consumer()
    channel = Mock()
    channel.is_open = False
    channel.basic_publish.side_effect = RuntimeError("stream lost")
    method = SimpleNamespace(delivery_tag=101, redelivered=False)

    with (
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=_outcome(job_id="job-3"),
        ),
        pytest.raises(RuntimeError, match="stream lost"),
    ):
        consumer._on_message_for_queue("docrunr.jobs", channel, method, None, b"{}")

    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_not_called()


def test_parallel_extraction_completes_two_jobs_and_acks_independent_of_order() -> None:
    consumer = _consumer(worker_concurrency=2)
    consumer._connection = Mock(is_open=True)  # type: ignore[attr-defined]
    consumer._connection.add_callback_threadsafe.side_effect = lambda callback: callback()  # type: ignore[union-attr]
    consumer._executor = Mock()

    first_future: Future[ExtractionOutcome] = Future()
    second_future: Future[ExtractionOutcome] = Future()
    consumer._executor.submit.side_effect = [first_future, second_future]

    channel = Mock()
    method_one = SimpleNamespace(delivery_tag=11, redelivered=False)
    method_two = SimpleNamespace(delivery_tag=12, redelivered=False)

    with patch("docrunr_worker.consumer.stats.record_job") as record_job:
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method_one,
            None,
            b'{"job_id":"job-1","source_path":"input/2026/04/11/14/a.pdf"}',
        )
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method_two,
            None,
            b'{"job_id":"job-2","source_path":"input/2026/04/11/14/b.pdf"}',
        )

        second_future.set_result(_outcome(job_id="job-2", duration_seconds=2.0))
        first_future.set_result(_outcome(job_id="job-1", duration_seconds=1.0))

    assert channel.basic_publish.call_count == 2
    assert {call.kwargs["routing_key"] for call in channel.basic_publish.call_args_list} == {
        "docrunr.results"
    }
    assert {call.kwargs["body"] for call in channel.basic_publish.call_args_list} == {
        b'{"job_id":"job-1","status":"ok","duration_seconds":1.0}',
        b'{"job_id":"job-2","status":"ok","duration_seconds":2.0}',
    }
    assert channel.basic_ack.call_args_list == [
        call(delivery_tag=12),
        call(delivery_tag=11),
    ]
    terminal = [c.args[0] for c in record_job.call_args_list if c.args[0].get("status") == "ok"]
    assert terminal == [
        {"job_id": "job-2", "status": "ok", "duration_seconds": 2.0},
        {"job_id": "job-1", "status": "ok", "duration_seconds": 1.0},
    ]
    assert sum(1 for c in record_job.call_args_list if c.args[0].get("status") == "processing") == 2


# --- LLM follow-up publish tests ---


def _outcome_with_llm(
    *,
    job_id: str = "job-1",
    status: str = "ok",
    duration_seconds: float = 1.25,
    llm_profile: str = "embed-local",
    chunks_path: str = "output/2026/04/15/00/job-1.json",
    filename: str = "test.pdf",
    source_path: str = "input/2026/04/15/00/test.pdf",
    priority: int = 0,
) -> ExtractionOutcome:
    result: dict[str, object] = {
        "job_id": job_id,
        "status": status,
        "duration_seconds": duration_seconds,
        "filename": filename,
        "source_path": source_path,
        "chunks_path": chunks_path,
        "llm_profile": llm_profile,
        "priority": priority,
    }
    import json

    return ExtractionOutcome(
        result_json=json.dumps(result),
        result=result,
        status=status,
        duration_seconds=duration_seconds,
    )


def test_llm_followup_published_on_success_with_llm_profile() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=50, redelivered=False)

    with (
        patch("docrunr_worker.consumer.stats.record_job"),
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=_outcome_with_llm(llm_profile="embed-local"),
        ),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-1","source_path":"input/2026/04/15/00/test.pdf"}',
        )

    publishes = channel.basic_publish.call_args_list
    assert len(publishes) == 2
    assert publishes[0].kwargs["routing_key"] == "docrunr.results"
    assert publishes[1].kwargs["routing_key"] == "docrunr.llm.jobs"
    import json

    llm_body = json.loads(publishes[1].kwargs["body"])
    assert llm_body["extract_job_id"] == "job-1"
    assert llm_body["llm_profile"] == "embed-local"
    assert llm_body["chunks_path"] == "output/2026/04/15/00/job-1.json"
    assert "job_id" in llm_body
    assert llm_body["job_id"] != "job-1"
    channel.queue_declare.assert_any_call(queue="docrunr.llm.jobs", durable=True)
    channel.basic_ack.assert_called_once_with(delivery_tag=50)


def test_no_llm_followup_when_llm_profile_absent() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=51, redelivered=False)

    with (
        patch("docrunr_worker.consumer.stats.record_job"),
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=_outcome_with_llm(llm_profile=""),
        ),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-1","source_path":"input/2026/04/15/00/test.pdf"}',
        )

    publishes = channel.basic_publish.call_args_list
    assert len(publishes) == 1
    assert publishes[0].kwargs["routing_key"] == "docrunr.results"
    channel.basic_ack.assert_called_once_with(delivery_tag=51)


def test_no_llm_followup_when_extraction_fails() -> None:
    consumer = _consumer()
    channel = Mock()
    method = SimpleNamespace(delivery_tag=52, redelivered=False)

    with (
        patch("docrunr_worker.consumer.stats.record_job"),
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=_outcome_with_llm(
                status="error",
                llm_profile="embed-local",
            ),
        ),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-1","source_path":"input/2026/04/15/00/test.pdf"}',
        )

    publishes = channel.basic_publish.call_args_list
    assert len(publishes) == 1
    assert publishes[0].kwargs["routing_key"] == "docrunr.results"
    channel.basic_ack.assert_called_once_with(delivery_tag=52)


def test_llm_followup_failure_does_not_block_extraction_ack() -> None:
    """If LLM follow-up publish fails, extraction result should still be acked."""
    consumer = _consumer()
    channel = Mock()
    call_count = [0]
    original_publish = channel.basic_publish

    def selective_publish(**kwargs: object) -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            return original_publish(**kwargs)
        if str(kwargs.get("routing_key", "")) == "docrunr.llm.jobs":
            raise RuntimeError("LLM queue unavailable")
        return original_publish(**kwargs)

    channel.basic_publish = Mock(side_effect=selective_publish)
    method = SimpleNamespace(delivery_tag=53, redelivered=False)

    with (
        patch("docrunr_worker.consumer.stats.record_job"),
        patch(
            "docrunr_worker.consumer.handle_extract_job",
            return_value=_outcome_with_llm(llm_profile="embed-local"),
        ),
    ):
        consumer._on_message_for_queue(
            "docrunr.jobs",
            channel,
            method,
            None,
            b'{"job_id":"job-1","source_path":"input/2026/04/15/00/test.pdf"}',
        )

    channel.basic_ack.assert_called_once_with(delivery_tag=53)
