"""Environment-based configuration for the DocRunr LLM worker."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings


class StorageType(StrEnum):
    LOCAL = "local"
    MINIO = "minio"


class LlmWorkerSettings(BaseSettings):
    model_config = {"env_prefix": "", "case_sensitive": False}

    # RabbitMQ
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_llm_queue: str = "docrunr.llm.jobs"
    rabbitmq_llm_result_queue: str = "docrunr.llm.results"
    rabbitmq_llm_dlq_queue: str = "docrunr.llm.dlq"
    rabbitmq_health_probe_timeout_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    rabbitmq_health_probe_cache_seconds: float = Field(default=5.0, ge=0.0, le=60.0)

    # Storage (reads chunks written by extraction worker)
    storage_type: StorageType = StorageType.LOCAL
    storage_base_path: str = "/data"

    # MinIO (only when storage_type=minio)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "docrunr"
    minio_secure: bool = False

    # LiteLLM
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = ""
    litellm_timeout_seconds: int = 120

    # Worker behaviour
    job_timeout_seconds: int = 300
    worker_concurrency: int = Field(default=1, ge=1, le=32)

    # Health endpoint
    health_port: int = 8081
    sqlite_base_path: str = "/db"

    # Optional UI / HTTP API gate
    ui_password: str = ""

    @property
    def ui_auth_enabled(self) -> bool:
        return bool(self.ui_password)

    @property
    def consumed_queues(self) -> tuple[str, ...]:
        return (self.rabbitmq_llm_queue,)


settings = LlmWorkerSettings()
