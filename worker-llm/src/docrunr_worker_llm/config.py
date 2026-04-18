"""Environment-based configuration for the DocRunr LLM worker."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, urlunparse

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

    # LiteLLM (Compose: http://litellm:4000; host dev: LITELLM_BASE_URL + RABBITMQ_HOST=localhost)
    litellm_base_url: str = "http://litellm:4000"
    litellm_api_key: str = ""
    litellm_timeout_seconds: int = 600

    # Worker behaviour
    job_timeout_seconds: int = 300
    worker_concurrency: int = Field(default=1, ge=1, le=32)

    # Health endpoint
    health_port: int = 8080
    sqlite_base_path: str = "/db"

    # Optional UI / HTTP API gate
    ui_password: str = ""

    @property
    def ui_auth_enabled(self) -> bool:
        return bool(self.ui_password)

    @property
    def consumed_queues(self) -> tuple[str, ...]:
        return (self.rabbitmq_llm_queue,)

    def model_post_init(self, *args: Any) -> None:
        # Map localhost / 127.0.0.1 to the litellm service when using Compose defaults: host
        # .env often sets LITELLM_BASE_URL=http://localhost:4000; inside the container use litellm.
        new_url = self.litellm_base_url
        if self.rabbitmq_host.strip().lower() == "rabbitmq":
            try:
                parsed = urlparse(self.litellm_base_url)
            except ValueError:
                pass
            else:
                h = (parsed.hostname or "").lower()
                if h in ("localhost", "127.0.0.1"):
                    port = parsed.port
                    netloc = f"litellm:{port}" if port is not None else "litellm:4000"
                    new_url = urlunparse(
                        (
                            parsed.scheme or "http",
                            netloc,
                            parsed.path or "",
                            "",
                            parsed.query,
                            parsed.fragment,
                        )
                    )
        if new_url != self.litellm_base_url:
            object.__setattr__(self, "litellm_base_url", new_url)


settings = LlmWorkerSettings()
