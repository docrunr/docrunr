"""RabbitMQ broker liveness probe and health.rabbitmq contract."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from docrunr_worker.config import WorkerSettings
from docrunr_worker.health import WorkerStats, stats
from docrunr_worker.rabbitmq_health import (
    configure_rabbitmq_health_probe,
    invalidate_rabbitmq_health_cache,
    rabbitmq_reachable_for_api,
)


@pytest.fixture(autouse=True)
def _reset_probe_globals() -> None:
    configure_rabbitmq_health_probe(None)
    invalidate_rabbitmq_health_cache()
    yield
    configure_rabbitmq_health_probe(None)
    invalidate_rabbitmq_health_cache()


def _probe_settings() -> WorkerSettings:
    return WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_user="guest",
        rabbitmq_password="guest",
        rabbitmq_health_probe_timeout_seconds=1.0,
        rabbitmq_health_probe_cache_seconds=10.0,
    )


def test_reachable_for_api_none_without_configure() -> None:
    assert rabbitmq_reachable_for_api() is None


def test_health_dict_falls_back_to_latch_when_probe_unconfigured() -> None:
    s = WorkerStats()
    assert s.health_dict()["rabbitmq"] == "disconnected"
    s.rabbitmq_connected = True
    assert s.health_dict()["rabbitmq"] == "connected"


@patch("docrunr_worker.rabbitmq_health._probe_once", return_value=True)
def test_health_connected_only_when_probe_and_latch(mock_probe: MagicMock) -> None:
    configure_rabbitmq_health_probe(_probe_settings())
    s = WorkerStats()
    s.rabbitmq_connected = False
    assert s.health_dict()["rabbitmq"] == "disconnected"
    s.rabbitmq_connected = True
    assert s.health_dict()["rabbitmq"] == "connected"
    assert mock_probe.call_count >= 1


@patch("docrunr_worker.rabbitmq_health._probe_once", return_value=False)
def test_health_disconnected_when_probe_fails(mock_probe: MagicMock) -> None:
    configure_rabbitmq_health_probe(_probe_settings())
    s = WorkerStats()
    s.rabbitmq_connected = True
    assert s.health_dict()["rabbitmq"] == "disconnected"


@patch("docrunr_worker.rabbitmq_health._probe_once", return_value=True)
def test_probe_result_cached_within_ttl(mock_probe: MagicMock) -> None:
    cfg = _probe_settings()
    configure_rabbitmq_health_probe(cfg)
    assert rabbitmq_reachable_for_api() is True
    assert rabbitmq_reachable_for_api() is True
    mock_probe.assert_called_once()


@patch("docrunr_worker.rabbitmq_health._probe_once", return_value=True)
def test_invalidate_cache_forces_new_probe(mock_probe: MagicMock) -> None:
    configure_rabbitmq_health_probe(_probe_settings())
    assert rabbitmq_reachable_for_api() is True
    invalidate_rabbitmq_health_cache()
    assert rabbitmq_reachable_for_api() is True
    assert mock_probe.call_count == 2


@patch("docrunr_worker.rabbitmq_health.time.monotonic", side_effect=[0.0, 1.0, 5.0])
@patch("docrunr_worker.rabbitmq_health._probe_once", return_value=True)
def test_cache_expires_after_ttl(mock_probe: MagicMock, _mono: MagicMock) -> None:
    cfg = _probe_settings().model_copy(update={"rabbitmq_health_probe_cache_seconds": 3.0})
    configure_rabbitmq_health_probe(cfg)
    assert rabbitmq_reachable_for_api() is True
    assert rabbitmq_reachable_for_api() is True
    mock_probe.assert_called_once()
    assert rabbitmq_reachable_for_api() is True
    assert mock_probe.call_count == 2


def test_global_stats_overview_respects_probe() -> None:
    prev = stats.rabbitmq_connected
    try:
        configure_rabbitmq_health_probe(_probe_settings())
        stats.rabbitmq_connected = True
        with patch("docrunr_worker.rabbitmq_health._probe_once", return_value=False):
            invalidate_rabbitmq_health_cache()
            assert stats.overview_dict()["health"]["rabbitmq"] == "disconnected"
    finally:
        stats.rabbitmq_connected = prev
