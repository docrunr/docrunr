"""Storage abstraction — local filesystem or MinIO (same contract as extraction worker)."""

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


class MinioStorage:
    def __init__(self, settings: LlmWorkerSettings) -> None:
        try:
            from minio import Minio
        except ImportError as exc:
            raise ImportError(
                "The minio package is required for MinIO storage (pip install minio>=7)"
            ) from exc

        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("Created MinIO bucket: %s", self._bucket)

    def read(self, path: str) -> Path:
        import tempfile

        suffix = Path(path).suffix
        fd, tmp_name = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            self._client.fget_object(self._bucket, path, str(tmp))
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return tmp

    def write(self, local_path: Path, dest_path: str) -> None:
        self._client.fput_object(self._bucket, dest_path, str(local_path))
        logger.debug("Uploaded %s -> %s/%s", local_path, self._bucket, dest_path)

    def delete(self, path: str) -> None:
        try:
            self._client.remove_object(self._bucket, path)
        except Exception:
            logger.warning("MinIO delete failed for %s", path, exc_info=True)

    def cleanup(self, local_path: Path) -> None:
        local_path.unlink(missing_ok=True)

    def exists(self, path: str) -> bool:
        try:
            self._client.stat_object(self._bucket, path)
            return True
        except Exception:
            return False


def create_storage(settings: LlmWorkerSettings) -> StorageBackend:
    if settings.storage_type == StorageType.MINIO:
        return MinioStorage(settings)
    return LocalStorage(settings.storage_base_path)
