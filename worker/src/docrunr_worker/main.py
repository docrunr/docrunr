"""Worker entrypoint — wire config, storage, health, consumer, and signal handling."""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docrunr_worker.config import WorkerSettings
from docrunr_worker.consumer import Consumer
from docrunr_worker.health import UploadServerContext, start_health_server, stats
from docrunr_worker.job_store import SQLiteJobStore
from docrunr_worker.rabbitmq_health import invalidate_rabbitmq_health_cache
from docrunr_worker.storage import create_storage

logger = logging.getLogger("docrunr_worker")
_SQLITE_FILENAME = "docrunr.sqlite"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)


def _resolve_sqlite_path(settings: WorkerSettings) -> Path:
    replica_id = _replica_id()
    base_path = Path(settings.sqlite_base_path).expanduser()
    return base_path / replica_id / _SQLITE_FILENAME


def _replica_id() -> str:
    value = os.environ.get("HOSTNAME", "").strip() or socket.gethostname().strip()
    cleaned = value.replace("/", "_")
    return cleaned or "local"


def main() -> None:
    _configure_logging()

    settings = WorkerSettings()
    logger.info("DocRunr Worker starting")

    storage = create_storage(settings)
    sqlite_path = _resolve_sqlite_path(settings)
    job_store: SQLiteJobStore | None = None
    try:
        job_store = SQLiteJobStore(str(sqlite_path))
        job_store.start()
        stats.attach_job_store(job_store)
    except Exception:
        logger.exception(
            "SQLite job store unavailable at %s; falling back to in-memory UI data",
            sqlite_path,
        )
        job_store = None

    upload_context = UploadServerContext(storage=storage, settings=settings)
    start_health_server(settings.health_port, storage=storage, upload_context=upload_context)

    consumer = Consumer(settings, storage)
    shutdown_event = threading.Event()

    def _shutdown(signum: int, _frame: object) -> None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Signal frame received: %r", _frame)
        shutdown_event.set()
        sig_name = signal.Signals(signum).name
        logger.info("Received %s; shutting down gracefully", sig_name)
        consumer.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while not shutdown_event.is_set():
        try:
            consumer.connect()
            consumer.start()
        except KeyboardInterrupt:
            shutdown_event.set()
            consumer.stop()
        except Exception:
            if shutdown_event.is_set():
                break
            stats.rabbitmq_connected = False
            invalidate_rabbitmq_health_cache()
            logger.exception("Consumer connection lost; reconnecting in 5s")
            shutdown_event.wait(5.0)

    if job_store is not None:
        job_store.stop()

    logger.info("Worker exited")
    sys.exit(0)


if __name__ == "__main__":
    main()
