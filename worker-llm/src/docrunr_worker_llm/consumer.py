"""RabbitMQ consumer — connection, channel, and consume loop for LLM jobs."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pika
from pika.adapters.blocking_connection import BlockingChannel

from docrunr_worker_llm.handler import (
    LlmOutcome,
    handle_llm_job,
    parse_job_request_from_body,
)
from docrunr_worker_llm.health import stats
from docrunr_worker_llm.job_status import PROCESSING
from docrunr_worker_llm.rabbitmq_health import invalidate_rabbitmq_health_cache

if TYPE_CHECKING:
    from docrunr_worker_llm.config import LlmWorkerSettings
    from docrunr_worker_llm.storage import StorageBackend

logger = logging.getLogger(__name__)
_HEARTBEAT_FLOOR_SECONDS = 60
_HEARTBEAT_GRACE_SECONDS = 30
_BLOCKED_TIMEOUT_FLOOR_SECONDS = 300


@dataclass(frozen=True)
class _PendingDelivery:
    queue_name: str
    channel: BlockingChannel
    method: pika.spec.Basic.Deliver
    body: bytes
    delivery_id: str


class Consumer:
    def __init__(self, settings: LlmWorkerSettings, storage: StorageBackend) -> None:
        self._settings = settings
        self._storage = storage
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None
        self._stopping = False

    def connect(self) -> None:
        self._stopping = False
        stats.rabbitmq_connected = False
        credentials = pika.PlainCredentials(
            self._settings.rabbitmq_user,
            self._settings.rabbitmq_password,
        )
        heartbeat_seconds = max(
            _HEARTBEAT_FLOOR_SECONDS,
            self._settings.job_timeout_seconds + _HEARTBEAT_GRACE_SECONDS,
        )
        blocked_timeout_seconds = max(
            _BLOCKED_TIMEOUT_FLOOR_SECONDS,
            heartbeat_seconds + _HEARTBEAT_GRACE_SECONDS,
        )
        params = pika.ConnectionParameters(
            host=self._settings.rabbitmq_host,
            port=self._settings.rabbitmq_port,
            credentials=credentials,
            heartbeat=heartbeat_seconds,
            blocked_connection_timeout=blocked_timeout_seconds,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        for queue_name in self._settings.consumed_queues:
            self._channel.queue_declare(queue=queue_name, durable=True)
        self._channel.queue_declare(queue=self._settings.rabbitmq_llm_result_queue, durable=True)
        self._channel.queue_declare(queue=self._settings.rabbitmq_llm_dlq_queue, durable=True)
        self._channel.basic_qos(prefetch_count=self._settings.worker_concurrency)

        stats.rabbitmq_connected = True
        invalidate_rabbitmq_health_cache()
        logger.info(
            "Connected to RabbitMQ at %s:%d; consuming queues=%s",
            self._settings.rabbitmq_host,
            self._settings.rabbitmq_port,
            ",".join(self._settings.consumed_queues),
        )

    def _publish_json(
        self, *, channel: BlockingChannel, queue_name: str, payload_json: str
    ) -> None:
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=payload_json.encode(),
            properties=pika.BasicProperties(delivery_mode=2),
        )

    def _publish_to_dlq(
        self,
        *,
        channel: BlockingChannel,
        body: bytes,
        source_queue: str,
        reason: str,
    ) -> None:
        channel.basic_publish(
            exchange="",
            routing_key=self._settings.rabbitmq_llm_dlq_queue,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,
                headers={
                    "x-docrunr-source-queue": source_queue,
                    "x-docrunr-reason": reason,
                    "x-docrunr-failed-at": datetime.now(UTC).isoformat(),
                },
            ),
        )

    def _result_payload(self, outcome: LlmOutcome) -> dict[str, object] | None:
        if outcome.result:
            return outcome.result
        try:
            parsed = json.loads(outcome.result_json)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _apply_stats_from_outcome(self, outcome: LlmOutcome) -> None:
        payload = self._result_payload(outcome)
        status = outcome.status
        duration_seconds = outcome.duration_seconds

        if payload is not None:
            raw_status = payload.get("status")
            if isinstance(raw_status, str):
                status = raw_status
            raw_duration = payload.get("duration_seconds")
            if isinstance(raw_duration, (int, float)):
                duration_seconds = float(raw_duration)

        if status == "ok":
            stats.record_success(duration_seconds)
        elif status == "error":
            stats.record_failure()

    def _complete_delivery(
        self,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        outcome: LlmOutcome,
        body: bytes,
        *,
        delivery_id: str,
    ) -> None:
        self._publish_json(
            channel=channel,
            queue_name=self._settings.rabbitmq_llm_result_queue,
            payload_json=outcome.result_json,
        )
        try:
            self._apply_stats_from_outcome(outcome)
            parsed_outcome = self._result_payload(outcome)
            if parsed_outcome is not None:
                stats.record_job(parsed_outcome)
            else:
                req = parse_job_request_from_body(body, delivery_id=delivery_id)
                stats.record_job(
                    {
                        "job_id": req.job_id,
                        "status": "error",
                        "filename": req.filename,
                        "source_path": req.source_path,
                        "chunks_path": req.chunks_path,
                        "llm_profile": "",
                        "provider": "",
                        "chunk_count": 0,
                        "vector_count": 0,
                        "duration_seconds": outcome.duration_seconds,
                        "artifact_path": None,
                        "error": "Worker returned a non-object JSON result",
                    }
                )
        except Exception:
            logger.debug("Failed to record LLM outcome in stats", exc_info=True)
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def _persist_processing(self, body: bytes, *, delivery_id: str) -> None:
        req = parse_job_request_from_body(body, delivery_id=delivery_id)
        try:
            stats.record_job(
                {
                    "job_id": req.job_id,
                    "status": PROCESSING,
                    "filename": req.filename,
                    "source_path": req.source_path,
                    "chunks_path": req.chunks_path,
                    "llm_profile": req.llm_profile,
                    "provider": "",
                    "chunk_count": 0,
                    "vector_count": 0,
                    "duration_seconds": 0.0,
                    "artifact_path": None,
                    "error": None,
                }
            )
        except Exception:
            logger.debug("Failed to record processing job receipt", exc_info=True)

    def _record_terminal_dlq(self, body: bytes, reason: str, *, delivery_id: str) -> None:
        req = parse_job_request_from_body(body, delivery_id=delivery_id)
        try:
            stats.record_failure()
            stats.record_job(
                {
                    "job_id": req.job_id,
                    "status": "error",
                    "filename": req.filename,
                    "source_path": req.source_path,
                    "chunks_path": req.chunks_path,
                    "llm_profile": "",
                    "provider": "",
                    "chunk_count": 0,
                    "vector_count": 0,
                    "duration_seconds": 0.0,
                    "artifact_path": None,
                    "error": reason,
                }
            )
        except Exception:
            logger.debug("Failed to record DLQ terminal outcome", exc_info=True)

    def _handle_processing_exception(
        self,
        queue_name: str,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        body: bytes,
        exc: Exception,
        *,
        delivery_id: str,
    ) -> None:
        logger.exception("Unhandled LLM error for queue %s", queue_name)
        if not channel.is_open:
            raise exc
        if not method.redelivered:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return
        try:
            self._publish_to_dlq(
                channel=channel,
                body=body,
                source_queue=queue_name,
                reason=str(exc),
            )
            self._record_terminal_dlq(body, str(exc), delivery_id=delivery_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            logger.warning(
                "Message dead-lettered to %s from %s",
                self._settings.rabbitmq_llm_dlq_queue,
                queue_name,
            )
        except Exception:
            logger.exception(
                "Failed to publish to DLQ %s; nacking with requeue",
                self._settings.rabbitmq_llm_dlq_queue,
            )
            if channel.is_open:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                raise

    def _on_llm_message(
        self,
        queue_name: str,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        body: bytes,
    ) -> None:
        delivery_id = uuid.uuid4().hex
        self._persist_processing(body, delivery_id=delivery_id)
        try:
            outcome = handle_llm_job(
                body=body,
                storage=self._storage,
                settings=self._settings,
                delivery_id=delivery_id,
            )
            self._complete_delivery(channel, method, outcome, body, delivery_id=delivery_id)
        except Exception as exc:
            self._handle_processing_exception(
                queue_name, channel, method, body, exc, delivery_id=delivery_id
            )

    def start(self) -> None:
        if self._channel is None:
            raise RuntimeError("Call connect() before start()")

        for queue_name in self._settings.consumed_queues:
            self._channel.basic_consume(
                queue=queue_name,
                on_message_callback=(
                    lambda ch, method, _props, body, queue=queue_name: self._on_llm_message(
                        queue,
                        ch,
                        method,
                        body,
                    )
                ),
            )
            logger.info("Consuming from queue: %s", queue_name)
        self._channel.start_consuming()

    def stop(self) -> None:
        stats.rabbitmq_connected = False
        invalidate_rabbitmq_health_cache()
        self._stopping = True
        if self._channel and self._channel.is_open:
            self._channel.stop_consuming()
        if self._connection and self._connection.is_open:
            self._connection.close()
        logger.info("Consumer stopped")
