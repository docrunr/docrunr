"""Environment-based configuration for the DocRunr worker."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings


class StorageType(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class WorkerSettings(BaseSettings):
    model_config = {"env_prefix": "", "case_sensitive": False}

    # RabbitMQ
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_queue: str = "docrunr.jobs"
    rabbitmq_result_queue: str = "docrunr.results"
    rabbitmq_dlq_queue: str = "docrunr.dlq"
    rabbitmq_llm_queue: str = "docrunr.llm.jobs"
    #: TCP/AMQP handshake timeout for ``/api/overview`` broker liveness (seconds).
    rabbitmq_health_probe_timeout_seconds: float = Field(default=2.0, ge=0.5, le=30.0)
    #: Reuse probe result; default > UI poll interval (4s) so steady-state polls hit cache.
    rabbitmq_health_probe_cache_seconds: float = Field(default=5.0, ge=0.0, le=60.0)

    # Storage
    storage_type: StorageType = StorageType.LOCAL
    storage_base_path: str = "/data"

    # S3-compatible storage (only when storage_type=s3)
    s3_endpoint: str = "http://seaweedfs:8333"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "docrunr"
    s3_region: str = "us-east-1"

    # Worker behaviour
    job_timeout_seconds: int = 120
    worker_concurrency: int = Field(default=1, ge=1, le=32)

    # Health endpoint
    health_port: int = 8080
    sqlite_base_path: str = "/db"

    # Optional UI / HTTP API gate (same port as health). Empty password = disabled.
    ui_password: str = ""

    @property
    def ui_auth_enabled(self) -> bool:
        return bool(self.ui_password)

    @property
    def consumed_queues(self) -> tuple[str, ...]:
        return (self.rabbitmq_queue,)


settings = WorkerSettings()
