"""RabbitMQ outbox publisher and result projection consumer."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import pika

from docrunr_runtime.messages import EXTRACTION_JOB_QUEUE_ARGUMENTS

from docrunr_api.config import ApiSettings
from docrunr_api.repository import JobRepository

logger = logging.getLogger(__name__)


class BrokerBridge:
    def __init__(self, settings: ApiSettings, repository: JobRepository) -> None:
        self._settings = settings
        self._repository = repository
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="api-rabbitmq", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def notify_outbox(self) -> None:
        self._wake.set()

    def wait_published(self, job_id: str, *, timeout: float = 10.0) -> bool:
        self.notify_outbox()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._repository.is_published(job_id):
                return True
            if self._stop.wait(0.05):
                break
        return False

    def _run(self) -> None:
        while not self._stop.is_set():
            connection: pika.BlockingConnection | None = None
            try:
                connection = pika.BlockingConnection(self._connection_parameters())
                channel = connection.channel()
                channel.queue_declare(
                    queue=self._settings.rabbitmq_queue,
                    durable=True,
                    arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS,
                )
                for queue in (
                    self._settings.rabbitmq_result_queue,
                    self._settings.rabbitmq_llm_result_queue,
                    self._settings.rabbitmq_lifecycle_queue,
                ):
                    channel.queue_declare(queue=queue, durable=True)
                channel.confirm_delivery()
                channel.basic_qos(prefetch_count=20)
                channel.basic_consume(
                    queue=self._settings.rabbitmq_result_queue,
                    on_message_callback=self._extraction_callback,
                )
                channel.basic_consume(
                    queue=self._settings.rabbitmq_llm_result_queue,
                    on_message_callback=self._llm_callback,
                )
                channel.basic_consume(
                    queue=self._settings.rabbitmq_lifecycle_queue,
                    on_message_callback=self._lifecycle_callback,
                )
                self._ready.set()
                while not self._stop.is_set() and connection.is_open:
                    self._flush_outbox(channel)
                    connection.process_data_events(time_limit=0.2)
                    self._wake.clear()
            except Exception:
                self._ready.clear()
                if not self._stop.is_set():
                    logger.exception("RabbitMQ bridge disconnected; retrying")
                    self._stop.wait(2)
            finally:
                self._ready.clear()
                if connection is not None and connection.is_open:
                    connection.close()

    def _flush_outbox(self, channel: Any) -> None:
        for item in self._repository.pending_outbox():
            published = channel.basic_publish(
                exchange="",
                routing_key=self._settings.rabbitmq_queue,
                body=bytes(item["body"]),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                    priority=int(item["priority"]),
                ),
                mandatory=True,
            )
            if published is False:
                raise RuntimeError("RabbitMQ did not confirm job publish")
            self._repository.mark_published(int(item["id"]))

    def _decode(self, body: bytes) -> dict[str, Any]:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload

    def _extraction_callback(
        self, channel: Any, method: Any, _properties: Any, body: bytes
    ) -> None:
        self._consume(channel, method, body, self._repository.apply_extraction_result)

    def _llm_callback(self, channel: Any, method: Any, _properties: Any, body: bytes) -> None:
        self._consume(channel, method, body, self._repository.apply_llm_result)

    def _lifecycle_callback(
        self, channel: Any, method: Any, _properties: Any, body: bytes
    ) -> None:
        self._consume(channel, method, body, self._repository.apply_lifecycle)

    def _consume(self, channel: Any, method: Any, body: bytes, apply: Any) -> None:
        try:
            apply(self._decode(body))
        except Exception:
            logger.exception("Could not project RabbitMQ message")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def _connection_parameters(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=self._settings.rabbitmq_host,
            port=self._settings.rabbitmq_port,
            credentials=pika.PlainCredentials(
                self._settings.rabbitmq_user,
                self._settings.rabbitmq_password,
            ),
            heartbeat=60,
            blocked_connection_timeout=30,
        )
