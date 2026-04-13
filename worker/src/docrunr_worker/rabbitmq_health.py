"""Short-timeout RabbitMQ broker reachability probe for health reporting (cached)."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docrunr_worker.config import WorkerSettings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_settings: WorkerSettings | None = None
_cache_mono: float | None = None
_cache_ok: bool | None = None


def configure_rabbitmq_health_probe(settings: WorkerSettings | None) -> None:
    """Register broker coordinates for cached AMQP liveness (health server startup)."""
    global _settings
    _settings = settings
    invalidate_rabbitmq_health_cache()


def invalidate_rabbitmq_health_cache() -> None:
    """Drop cached probe result (e.g. after tests mutate broker)."""
    global _cache_mono, _cache_ok
    with _lock:
        _cache_mono = None
        _cache_ok = None


def _probe_once(settings: WorkerSettings) -> bool:
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
    """Whether the broker accepts an AMQP connection now (cached short-timeout probe).

    ``health_dict`` combines this with ``WorkerStats.rabbitmq_connected`` so the UI does not
    show connected when only TCP works but the consumer never finished setup.

    Returns:
        ``True`` / ``False`` when probe settings are configured.
        ``None`` when not configured (caller should use the consumer latch only).
    """
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
