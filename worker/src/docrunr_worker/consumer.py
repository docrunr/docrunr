"""RabbitMQ consumer — connection, channel, and consume loop."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pika
from pika.adapters.blocking_connection import BlockingChannel

from docrunr_worker.handler import (
    ExtractionOutcome,
    handle_extract_job,
    parse_job_request_from_body,
)
from docrunr_worker.health import stats
from docrunr_worker.job_messages import EXTRACTION_JOB_QUEUE_ARGUMENTS
from docrunr_worker.job_status import PROCESSING
from docrunr_worker.rabbitmq_health import invalidate_rabbitmq_health_cache

if TYPE_CHECKING:
    from docrunr_worker.config import WorkerSettings
    from docrunr_worker.storage import StorageBackend

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


def _run_extract_in_child(
    body: bytes,
    timeout: int,
    settings_payload: dict[str, Any],
    delivery_id: str,
) -> ExtractionOutcome:
    from docrunr_worker.config import WorkerSettings
    from docrunr_worker.storage import create_storage

    settings = WorkerSettings.model_validate(settings_payload)
    storage = create_storage(settings)
    return handle_extract_job(
        body=body,
        storage=storage,
        timeout=timeout,
        delivery_id=delivery_id,
    )


class Consumer:
    def __init__(self, settings: WorkerSettings, storage: StorageBackend) -> None:
        self._settings = settings
        self._storage = storage
        self._settings_payload = settings.model_dump()
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None
        self._executor: ProcessPoolExecutor | None = None
        self._pending_deliveries: dict[Future[ExtractionOutcome], _PendingDelivery] = {}
        self._pending_lock = threading.Lock()
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
            if queue_name == self._settings.rabbitmq_queue:
                self._channel.queue_declare(
                    queue=queue_name,
                    durable=True,
                    arguments=EXTRACTION_JOB_QUEUE_ARGUMENTS,
                )
            else:
                self._channel.queue_declare(queue=queue_name, durable=True)
        self._channel.queue_declare(queue=self._settings.rabbitmq_result_queue, durable=True)
        self._channel.queue_declare(queue=self._settings.rabbitmq_dlq_queue, durable=True)
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
        """Publish a failed message to the dead-letter queue."""
        channel.basic_publish(
            exchange="",
            routing_key=self._settings.rabbitmq_dlq_queue,
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

    def _ensure_executor(self) -> None:
        if self._settings.worker_concurrency <= 1 or self._executor is not None:
            return
        self._executor = ProcessPoolExecutor(max_workers=self._settings.worker_concurrency)
        logger.info(
            "Started process pool with max_workers=%d",
            self._settings.worker_concurrency,
        )

    def _result_payload(self, outcome: ExtractionOutcome) -> dict[str, object] | None:
        if outcome.result:
            return outcome.result
        try:
            parsed = json.loads(outcome.result_json)
        except Exception:
            logger.debug("Failed to parse extraction outcome JSON", exc_info=True)
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    def _apply_stats_from_outcome(self, outcome: ExtractionOutcome) -> None:
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
        outcome: ExtractionOutcome,
        body: bytes,
        *,
        delivery_id: str,
    ) -> None:
        self._publish_json(
            channel=channel,
            queue_name=self._settings.rabbitmq_result_queue,
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
                        "markdown_path": None,
                        "chunks_path": None,
                        "total_tokens": 0,
                        "chunk_count": 0,
                        "duration_seconds": outcome.duration_seconds,
                        "error": "Worker returned a non-object JSON result",
                        "priority": req.priority,
                    }
                )
        except Exception:
            logger.debug("Failed to record extraction outcome in stats", exc_info=True)
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
                    "markdown_path": None,
                    "chunks_path": None,
                    "total_tokens": 0,
                    "chunk_count": 0,
                    "duration_seconds": 0.0,
                    "error": None,
                    "priority": req.priority,
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
                    "markdown_path": None,
                    "chunks_path": None,
                    "total_tokens": 0,
                    "chunk_count": 0,
                    "duration_seconds": 0.0,
                    "error": reason,
                    "priority": req.priority,
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
        logger.exception("Unhandled extraction error for queue %s", queue_name)
        if not channel.is_open:
            # The broker already dropped this channel/connection; RabbitMQ will requeue it.
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
                self._settings.rabbitmq_dlq_queue,
                queue_name,
            )
        except Exception:
            logger.exception(
                "Failed to publish to DLQ %s; nacking with requeue",
                self._settings.rabbitmq_dlq_queue,
            )
            if channel.is_open:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                # Broker closed the channel while attempting to dead-letter.
                raise

    def _pop_pending_delivery(self, future: Future[ExtractionOutcome]) -> _PendingDelivery | None:
        with self._pending_lock:
            return self._pending_deliveries.pop(future, None)

    def _get_pending_delivery(self, future: Future[ExtractionOutcome]) -> _PendingDelivery | None:
        with self._pending_lock:
            return self._pending_deliveries.get(future)

    def _finish_future(self, future: Future[ExtractionOutcome]) -> None:
        delivery = self._pop_pending_delivery(future)
        if delivery is None:
            return

        try:
            outcome = future.result()
            self._complete_delivery(
                delivery.channel,
                delivery.method,
                outcome,
                delivery.body,
                delivery_id=delivery.delivery_id,
            )
        except Exception as exc:
            self._handle_processing_exception(
                delivery.queue_name,
                delivery.channel,
                delivery.method,
                delivery.body,
                exc,
                delivery_id=delivery.delivery_id,
            )

    def _on_future_done(self, future: Future[ExtractionOutcome]) -> None:
        if self._stopping:
            return

        delivery = self._get_pending_delivery(future)
        if delivery is None:
            return
        if not delivery.channel.is_open:
            self._pop_pending_delivery(future)
            logger.warning(
                "Dropping completed extraction result because the delivery channel is closed"
            )
            return

        connection = self._connection
        if connection is None or not connection.is_open:
            self._pop_pending_delivery(future)
            logger.warning(
                "Dropping completed extraction result because broker connection is closed"
            )
            return

        try:
            connection.add_callback_threadsafe(lambda: self._finish_future(future))
        except Exception:
            self._pop_pending_delivery(future)
            logger.exception("Failed to schedule extraction completion on broker thread")

    def _drain_pending_futures(self) -> None:
        while True:
            with self._pending_lock:
                futures = list(self._pending_deliveries)
            if not futures:
                return
            for future in futures:
                self._finish_future(future)

    def _on_extraction_message(
        self,
        queue_name: str,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        body: bytes,
    ) -> None:
        delivery_id = uuid.uuid4().hex
        self._persist_processing(body, delivery_id=delivery_id)
        if self._settings.worker_concurrency <= 1:
            try:
                outcome = handle_extract_job(
                    body=body,
                    storage=self._storage,
                    timeout=self._settings.job_timeout_seconds,
                    delivery_id=delivery_id,
                )
                self._complete_delivery(channel, method, outcome, body, delivery_id=delivery_id)
            except Exception as exc:
                self._handle_processing_exception(
                    queue_name, channel, method, body, exc, delivery_id=delivery_id
                )
            return

        self._ensure_executor()
        if self._executor is None:
            raise RuntimeError("Process pool executor was not initialized")

        try:
            future = self._executor.submit(
                _run_extract_in_child,
                body,
                self._settings.job_timeout_seconds,
                self._settings_payload,
                delivery_id,
            )
            with self._pending_lock:
                self._pending_deliveries[future] = _PendingDelivery(
                    queue_name=queue_name,
                    channel=channel,
                    method=method,
                    body=body,
                    delivery_id=delivery_id,
                )
            future.add_done_callback(self._on_future_done)
        except Exception as exc:
            self._handle_processing_exception(
                queue_name, channel, method, body, exc, delivery_id=delivery_id
            )

    def _on_message_for_queue(
        self,
        queue_name: str,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        _props: object,  # skylos: ignore — pika ``basic_consume`` callback arity
        body: bytes,
    ) -> None:
        """Backward-compatible callback kept for older tests/callers."""
        self._on_extraction_message(queue_name, channel, method, body)

    def start(self) -> None:
        if self._channel is None:
            raise RuntimeError("Call connect() before start()")

        self._ensure_executor()
        for queue_name in self._settings.consumed_queues:
            self._channel.basic_consume(
                queue=queue_name,
                on_message_callback=(
                    lambda ch, method, _props, body, queue=queue_name: self._on_extraction_message(
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
        self._drain_pending_futures()
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._executor = None
        if self._connection and self._connection.is_open:
            self._connection.close()
        logger.info("Consumer stopped")
