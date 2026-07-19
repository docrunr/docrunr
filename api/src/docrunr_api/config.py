"""Environment configuration for the DocRunr API."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class StorageType(StrEnum):
    LOCAL = "local"
    S3 = "s3"


class ApiSettings(BaseSettings):
    model_config = {"env_prefix": "", "case_sensitive": False}

    api_host: str = "127.0.0.1"
    api_port: int = 8080
    api_key: str = ""
    api_allow_unauthenticated_public: bool = False
    api_db_path: str = "/db/docrunr-api.sqlite"
    api_max_upload_bytes: int = Field(default=100 * 1024 * 1024, ge=1)

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_queue: str = "docrunr.jobs"
    rabbitmq_result_queue: str = "docrunr.results"
    rabbitmq_llm_result_queue: str = "docrunr.llm.results"
    rabbitmq_lifecycle_queue: str = "docrunr.lifecycle"

    storage_type: StorageType = StorageType.LOCAL
    storage_base_path: str = "/data"
    s3_endpoint: str = "http://seaweedfs:8333"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "docrunr"
    s3_region: str = "us-east-1"

    litellm_base_url: str = ""
    litellm_api_key: str = ""
    litellm_timeout_seconds: float = 10.0
    litellm_profiles_cache_seconds: float = 30.0

    @model_validator(mode="after")
    def validate_public_auth(self) -> ApiSettings:
        public_hosts = {"0.0.0.0", "::", "[::]"}
        if (
            self.api_host.strip() in public_hosts
            and not self.api_key
            and not self.api_allow_unauthenticated_public
        ):
            raise ValueError(
                "API_KEY is required for a public API_HOST; "
                "set API_ALLOW_UNAUTHENTICATED_PUBLIC=true only behind a trusted binding"
            )
        return self
