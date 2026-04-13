"""RabbitMQ publish helpers (durable messages to a named queue)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pika

from docrunr_worker.job_messages import (
    EXTRACTION_JOB_QUEUE_ARGUMENTS,
    validate_extraction_job_priority_value,
)

if TYPE_CHECKING:
    from docrunr_worker.config import WorkerSettings

logger = logging.getLogger(__name__)


def publish_durable_bytes(
    *,
    settings: WorkerSettings,
    queue_name: str,
    body: bytes,
    priority: int = 0,
) -> None:
    """Open a short-lived connection, declare the queue, publish (delivery_mode=2), close.

    When ``queue_name`` matches ``settings.rabbitmq_queue``, the queue is declared with
    ``x-max-priority`` and ``BasicProperties.priority`` is set. Other queues get a plain
    durable declare and no message priority (avoids ``PRECONDITION_FAILED`` on reuse).
    """
    credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password)
    params = pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        is_jobs_queue = queue_name == settings.rabbitmq_queue
        if is_jobs_queue:
            channel.queue_declare(
                queue=queue_name,
                durable=True,
                arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS,
            )
        else:
            channel.queue_declare(queue=queue_name, durable=True)
        if is_jobs_queue:
            props = pika.BasicProperties(
                delivery_mode=2,
                priority=validate_extraction_job_priority_value(priority),
            )
        else:
            props = pika.BasicProperties(delivery_mode=2)
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=body,
            properties=props,
        )
    finally:
        try:
            connection.close()
        except Exception:
            logger.debug("RabbitMQ connection close failed", exc_info=True)
