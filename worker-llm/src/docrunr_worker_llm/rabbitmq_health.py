"""Short-timeout RabbitMQ broker reachability probe for health reporting (cached)."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docrunr_worker_llm.config import LlmWorkerSettings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_settings: LlmWorkerSettings | None = None
_cache_mono: float | None = None
_cache_ok: bool | None = None


def configure_rabbitmq_health_probe(settings: LlmWorkerSettings | None) -> None:
    global _settings
    _settings = settings
    invalidate_rabbitmq_health_cache()


def invalidate_rabbitmq_health_cache() -> None:
    global _cache_mono, _cache_ok
    with _lock:
        _cache_mono = None
        _cache_ok = None


def _probe_once(settings: LlmWorkerSettings) -> bool:
    import pika

    timeout = float(settings.rabbitmq_health_probe_timeout_seconds)
    credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password)
    params = pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        credentials=credentials,
        socket_timeout=timeout,
        connection_attempts=1,
        retry_delay=0,
        heartbeat=30,
        blocked_connection_timeout=max(timeout + 1.0, 5.0),
    )
    try:
        conn = pika.BlockingConnection(params)
        try:
            if conn.is_open:
                conn.close()
        except Exception:
            logger.debug("Probe connection close failed", exc_info=True)
        return True
    except Exception:
        logger.debug("RabbitMQ broker health probe failed", exc_info=True)
        return False


def rabbitmq_reachable_for_api() -> bool | None:
    global _cache_mono, _cache_ok
    cfg = _settings
    if cfg is None:
        return None

    ttl = float(cfg.rabbitmq_health_probe_cache_seconds)
    now = time.monotonic()
    with _lock:
        if _cache_mono is not None and (now - _cache_mono) < ttl:
            return _cache_ok is True
        ok = _probe_once(cfg)
        _cache_mono = now
        _cache_ok = ok
        return ok
