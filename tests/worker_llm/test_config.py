"""Tests for LLM worker configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from docrunr_worker_llm.config import LlmWorkerSettings, StorageType
from pydantic import ValidationError


class TestLlmWorkerSettings:
    def test_defaults(self) -> None:
        clean = {
            k: v
            for k, v in os.environ.items()
            if not k.upper().startswith(("RABBITMQ_", "STORAGE_", "MINIO_", "LITELLM_"))
            and k.upper()
            not in (
                "JOB_TIMEOUT_SECONDS",
                "HEALTH_PORT",
                "SQLITE_BASE_PATH",
                "UI_PASSWORD",
                "WORKER_CONCURRENCY",
            )
        }
        with patch.dict(os.environ, clean, clear=True):
            settings = LlmWorkerSettings()
        assert settings.rabbitmq_host == "rabbitmq"
        assert settings.rabbitmq_port == 5672
        assert settings.rabbitmq_llm_queue == "docrunr.llm.jobs"
        assert settings.rabbitmq_llm_result_queue == "docrunr.llm.results"
        assert settings.rabbitmq_llm_dlq_queue == "docrunr.llm.dlq"
        assert settings.consumed_queues == ("docrunr.llm.jobs",)
        assert settings.storage_type == StorageType.LOCAL
        assert settings.storage_base_path == "/data"
        assert settings.litellm_base_url == "http://litellm:4000"
        assert settings.litellm_api_key == ""
        assert settings.litellm_timeout_seconds == 120
        assert settings.job_timeout_seconds == 300
        assert settings.worker_concurrency == 1
        assert settings.health_port == 8080
        assert settings.sqlite_base_path == "/db"
        assert settings.ui_password == ""
        assert settings.ui_auth_enabled is False

    def test_env_override(self) -> None:
        env = {
            "RABBITMQ_HOST": "my-rabbit",
            "RABBITMQ_PORT": "5673",
            "STORAGE_TYPE": "minio",
            "LITELLM_BASE_URL": "http://litellm:4000",
            "LITELLM_API_KEY": "sk-test-123",
            "HEALTH_PORT": "9090",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = LlmWorkerSettings()
            assert settings.rabbitmq_host == "my-rabbit"
            assert settings.rabbitmq_port == 5673
            assert settings.storage_type == StorageType.MINIO
            assert settings.litellm_base_url == "http://litellm:4000"
            assert settings.litellm_api_key == "sk-test-123"
            assert settings.health_port == 9090

    def test_localhost_litellm_rewritten_when_rabbitmq_is_compose_service(self) -> None:
        env = {
            "RABBITMQ_HOST": "rabbitmq",
            "LITELLM_BASE_URL": "http://localhost:4000",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = LlmWorkerSettings()
            assert settings.litellm_base_url == "http://litellm:4000"

    def test_localhost_litellm_kept_when_rabbitmq_is_host(self) -> None:
        env = {
            "RABBITMQ_HOST": "127.0.0.1",
            "LITELLM_BASE_URL": "http://localhost:4000",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = LlmWorkerSettings()
            assert settings.litellm_base_url == "http://localhost:4000"

    def test_storage_type_enum(self) -> None:
        assert StorageType.LOCAL.value == "local"
        assert StorageType.MINIO.value == "minio"

    @pytest.mark.parametrize("value", [0, 33])
    def test_worker_concurrency_bounds(self, value: int) -> None:
        with pytest.raises(ValidationError):
            LlmWorkerSettings(worker_concurrency=value)

    def test_ui_auth_env(self) -> None:
        env = {"UI_PASSWORD": "hunter2"}
        with patch.dict(os.environ, env, clear=False):
            settings = LlmWorkerSettings()
            assert settings.ui_password == "hunter2"
            assert settings.ui_auth_enabled is True
