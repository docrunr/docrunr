"""Tests for worker configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from docrunr_worker.config import StorageType, WorkerSettings
from pydantic import ValidationError


class TestWorkerSettings:
    def test_defaults(self) -> None:
        settings = WorkerSettings()
        assert settings.rabbitmq_host == "rabbitmq"
        assert settings.rabbitmq_port == 5672
        assert settings.rabbitmq_queue == "docrunr.jobs"
        assert settings.rabbitmq_result_queue == "docrunr.results"
        assert settings.consumed_queues == ("docrunr.jobs",)
        assert settings.storage_type == StorageType.LOCAL
        assert settings.storage_base_path == "/data"
        assert settings.worker_concurrency == 1
        assert settings.job_timeout_seconds == 120
        assert settings.rabbitmq_health_probe_timeout_seconds == 2.0
        assert settings.rabbitmq_health_probe_cache_seconds == 5.0
        assert settings.health_port == 8080
        assert settings.sqlite_base_path == "/db"
        assert settings.ui_password == ""
        assert settings.ui_auth_enabled is False

    def test_env_override(self) -> None:
        env = {
            "RABBITMQ_HOST": "my-rabbit",
            "RABBITMQ_PORT": "5673",
            "STORAGE_TYPE": "minio",
            "WORKER_CONCURRENCY": "4",
            "HEALTH_PORT": "9090",
            "SQLITE_BASE_PATH": "/tmp/jobs-db",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = WorkerSettings()
            assert settings.rabbitmq_host == "my-rabbit"
            assert settings.rabbitmq_port == 5673
            assert settings.consumed_queues == ("docrunr.jobs",)
            assert settings.storage_type == StorageType.MINIO
            assert settings.worker_concurrency == 4
            assert settings.health_port == 9090
            assert settings.sqlite_base_path == "/tmp/jobs-db"

    def test_storage_type_enum(self) -> None:
        assert StorageType.LOCAL.value == "local"
        assert StorageType.MINIO.value == "minio"

    @pytest.mark.parametrize("value", [0, 33])
    def test_worker_concurrency_bounds(self, value: int) -> None:
        with pytest.raises(ValidationError):
            WorkerSettings(worker_concurrency=value)

    def test_ui_auth_env(self) -> None:
        env = {
            "UI_PASSWORD": "hunter2",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = WorkerSettings()
            assert settings.ui_password == "hunter2"
            assert settings.ui_auth_enabled is True
