"""Tests for RabbitMQ publish helper (queue declare + message properties)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from docrunr_worker.config import WorkerSettings
from docrunr_worker.job_messages import EXTRACTION_JOB_QUEUE_ARGUMENTS
from docrunr_worker.publisher import publish_durable_bytes


def test_publish_declares_priority_queue_and_sets_basic_priority() -> None:
    settings = WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_queue="docrunr.jobs",
    )
    channel = MagicMock()
    connection = MagicMock()
    connection.channel.return_value = channel

    with patch("docrunr_worker.publisher.pika.BlockingConnection", return_value=connection):
        publish_durable_bytes(
            settings=settings,
            queue_name="docrunr.jobs",
            body=b'{"job_id":"j1"}',
            priority=200,
        )

    channel.queue_declare.assert_called_once_with(
        queue="docrunr.jobs",
        durable=True,
        arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS,
    )
    channel.basic_publish.assert_called_once()
    props = channel.basic_publish.call_args.kwargs["properties"]
    assert props.delivery_mode == 2
    assert props.priority == 200


def test_publish_other_queue_plain_declare_no_message_priority() -> None:
    settings = WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_queue="docrunr.jobs",
    )
    channel = MagicMock()
    connection = MagicMock()
    connection.channel.return_value = channel

    with patch("docrunr_worker.publisher.pika.BlockingConnection", return_value=connection):
        publish_durable_bytes(
            settings=settings,
            queue_name="docrunr.results",
            body=b"{}",
            priority=99,
        )

    channel.queue_declare.assert_called_once_with(queue="docrunr.results", durable=True)
    props = channel.basic_publish.call_args.kwargs["properties"]
    assert props.delivery_mode == 2
    assert getattr(props, "priority", None) is None
