"""RabbitMQ publish helpers for the LLM worker (durable messages to a named queue)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pika

if TYPE_CHECKING:
    from docrunr_worker_llm.config import LlmWorkerSettings

logger = logging.getLogger(__name__)


def publish_durable_bytes(
    *,
    settings: LlmWorkerSettings,
    queue_name: str,
    body: bytes,
) -> None:
    """Open a short-lived connection, declare the queue, publish (delivery_mode=2), close."""
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
        channel.queue_declare(queue=queue_name, durable=True)
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
