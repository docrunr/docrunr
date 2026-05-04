"""Storage abstraction — local filesystem or S3-compatible object storage."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

from docrunr_worker_llm.config import LlmWorkerSettings, StorageType

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    def read(self, path: str) -> Path: ...
    def write(self, local_path: Path, dest_path: str) -> None: ...
    def delete(self, path: str) -> None: ...
    def cleanup(self, local_path: Path) -> None: ...
    def exists(self, path: str) -> bool: ...


class LocalStorage:
    def __init__(self, base_path: str) -> None:
        self._base = Path(base_path).resolve()

    def _resolve_under_base(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            raise ValueError(f"Storage paths must be relative: {path}")
        resolved = (self._base / candidate).resolve()
        try:
            resolved.relative_to(self._base)
        except ValueError as exc:
            raise ValueError(f"Storage path escapes base directory: {path}") from exc
        return resolved

    def read(self, path: str) -> Path:
        full = self._resolve_under_base(path)
        if not full.exists():
            raise FileNotFoundError(f"File not found in local storage: {full}")
        return full

    def write(self, local_path: Path, dest_path: str) -> None:
        full = self._resolve_under_base(dest_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        if local_path != full:
            shutil.copy2(local_path, full)
        logger.debug("Wrote %s", full)

    def delete(self, path: str) -> None:
        full = self._resolve_under_base(path)
        try:
            full.unlink(missing_ok=True)
        except OSError:
            logger.warning("Local storage delete failed for %s", path, exc_info=True)

    def cleanup(self, local_path: Path) -> None:
        logger.debug("Local storage cleanup noop for %s", local_path)

    def exists(self, path: str) -> bool:
        try:
            return self._resolve_under_base(path).exists()
        except ValueError:
            return False


class S3Storage:
    def __init__(self, settings: LlmWorkerSettings) -> None:
        try:
            import boto3
            from botocore.config import Config as BotoConfig
            from botocore.exceptions import ClientError
        except ImportError as exc:
            raise ImportError(
                "The boto3 package is required for S3 storage (pip install boto3>=1.35)"
            ) from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=BotoConfig(s3={"addressing_style": "path"}),
        )
        self._client_error = ClientError
        self._bucket = settings.s3_bucket
        self._region = settings.s3_region
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except self._client_error as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise

        create_kwargs: dict[str, object] = {"Bucket": self._bucket}
        if self._region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {
                "LocationConstraint": self._region
            }
        self._client.create_bucket(**create_kwargs)
        logger.info("Created S3 bucket: %s", self._bucket)

    def read(self, path: str) -> Path:
        import tempfile

        suffix = Path(path).suffix
        fd, tmp_name = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            self._client.download_file(self._bucket, path, str(tmp))
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return tmp

    def write(self, local_path: Path, dest_path: str) -> None:
        self._client.upload_file(str(local_path), self._bucket, dest_path)
        logger.debug("Uploaded %s -> %s/%s", local_path, self._bucket, dest_path)

    def delete(self, path: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=path)
        except Exception:
            logger.warning("S3 delete failed for %s", path, exc_info=True)

    def cleanup(self, local_path: Path) -> None:
        local_path.unlink(missing_ok=True)

    def exists(self, path: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=path)
            return True
        except self._client_error:
            return False


def create_storage(settings: LlmWorkerSettings) -> StorageBackend:
    if settings.storage_type == StorageType.S3:
        return S3Storage(settings)
    return LocalStorage(settings.storage_base_path)
