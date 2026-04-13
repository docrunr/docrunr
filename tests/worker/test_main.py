"""Tests for worker main loop behavior."""

from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import patch

from docrunr_worker.config import WorkerSettings
from docrunr_worker.main import _resolve_sqlite_path, main


def test_resolve_sqlite_path_uses_base_path_per_replica() -> None:
    settings = WorkerSettings(sqlite_base_path="/db")
    with patch.dict("os.environ", {"HOSTNAME": "worker-0"}, clear=False):
        resolved = _resolve_sqlite_path(settings)
    assert resolved == Path("/db/worker-0/docrunr.sqlite")


def test_resolve_sqlite_path_supports_relative_base_path() -> None:
    settings = WorkerSettings(sqlite_base_path=".data")
    with patch.dict("os.environ", {"HOSTNAME": "worker-0"}, clear=False):
        resolved = _resolve_sqlite_path(settings)
    assert resolved == Path(".data/worker-0/docrunr.sqlite")


def test_resolve_sqlite_path_keeps_absolute_base_path() -> None:
    settings = WorkerSettings(sqlite_base_path="/var/lib/docrunr")
    with patch.dict("os.environ", {"HOSTNAME": "worker-0"}, clear=False):
        resolved = _resolve_sqlite_path(settings)
    assert resolved == Path("/var/lib/docrunr/worker-0/docrunr.sqlite")


def test_main_exits_loop_after_signal_without_reconnect() -> None:
    settings = WorkerSettings(
        rabbitmq_queue="docrunr.jobs",
        rabbitmq_result_queue="docrunr.results",
    )
    handlers: dict[int, object] = {}

    instance_holder: dict[str, object] = {}

    class FakeConsumer:
        def __init__(self, _settings: WorkerSettings, _storage: object) -> None:
            self.connect_calls = 0
            self.start_calls = 0
            self.stop_calls = 0
            instance_holder["consumer"] = self

        def connect(self) -> None:
            self.connect_calls += 1

        def start(self) -> None:
            self.start_calls += 1
            handler = handlers[signal.SIGTERM]
            handler(signal.SIGTERM, None)

        def stop(self) -> None:
            self.stop_calls += 1

    def fake_signal(sig: int, handler: object) -> None:
        handlers[sig] = handler

    with (
        patch("docrunr_worker.main._configure_logging"),
        patch("docrunr_worker.main.WorkerSettings", return_value=settings),
        patch("docrunr_worker.main.create_storage", return_value=object()),
        patch("docrunr_worker.main.SQLiteJobStore"),
        patch("docrunr_worker.main.stats.attach_job_store"),
        patch("docrunr_worker.main.start_health_server"),
        patch("docrunr_worker.main.Consumer", FakeConsumer),
        patch("docrunr_worker.main.signal.signal", side_effect=fake_signal),
        patch("docrunr_worker.main.sys.exit"),
    ):
        main()

    consumer = instance_holder["consumer"]
    assert isinstance(consumer, FakeConsumer)
    assert consumer.connect_calls == 1
    assert consumer.start_calls == 1
    assert consumer.stop_calls == 1
