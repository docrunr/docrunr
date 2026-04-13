"""Host-side storage helpers for integration tests (local bind mount vs MinIO on published port)."""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from docrunr_worker.job_messages import input_relative_path


def _norm_key(rel_path: str) -> str:
    return PurePosixPath(rel_path).as_posix()


class IntegrationStorage(ABC):
    """Clear/stage/assert against the same layout the worker uses (``input/…``, ``output/…``)."""

    @property
    @abstractmethod
    def report_dir(self) -> Path:
        """Directory for ``integration-report.json`` and related host artifacts."""

    @abstractmethod
    def clear(self) -> None:
        """Remove staged inputs and outputs before a run."""

    @abstractmethod
    def stage_input(self, sample: Path, job_id: str) -> str:
        """Place ``sample`` in storage; return ``source_path`` for the job payload."""

    @abstractmethod
    def exists(self, rel_path: str) -> bool:
        """True if the object exists at the storage-relative key."""

    @abstractmethod
    def count_inputs(self) -> int:
        """Number of objects under ``input/`` (recursive)."""

    @abstractmethod
    def count_outputs(self) -> int:
        """Number of objects under ``output/`` (recursive)."""


def _count_files_under(dir_path: Path) -> int:
    if not dir_path.is_dir():
        return 0
    return sum(1 for p in dir_path.rglob("*") if p.is_file())


class LocalIntegrationStorage(IntegrationStorage):
    def __init__(self, data_root: Path) -> None:
        self._root = data_root.resolve()

    @property
    def report_dir(self) -> Path:
        return self._root

    def clear(self) -> None:
        for name in ("input", "output"):
            p = self._root / name
            if p.is_dir():
                shutil.rmtree(p)

    def stage_input(self, sample: Path, job_id: str) -> str:
        ext = sample.suffix.lower()
        rel = input_relative_path(job_id, ext, now=datetime.now(UTC))
        dest = self._root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sample, dest)
        return rel

    def exists(self, rel_path: str) -> bool:
        key = _norm_key(rel_path)
        return (self._root / key).is_file()

    def count_inputs(self) -> int:
        return _count_files_under(self._root / "input")

    def count_outputs(self) -> int:
        return _count_files_under(self._root / "output")


class MinioIntegrationStorage(IntegrationStorage):
    """Talk to MinIO from the host using the same bucket and keys as the worker."""

    def __init__(
        self,
        *,
        repo_root: Path,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
    ) -> None:
        from minio import Minio

        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket
        self._report_dir = Path(
            os.environ.get("DOCRUNR_INTEGRATION_DATA", str(repo_root / ".data"))
        ).resolve()
        self._report_dir.mkdir(parents=True, exist_ok=True)

    @property
    def report_dir(self) -> Path:
        return self._report_dir

    @classmethod
    def from_env(cls, repo_root: Path) -> MinioIntegrationStorage:
        endpoint = os.environ.get("DOCRUNR_INTEGRATION_MINIO_ENDPOINT", "127.0.0.1:9000")
        access_key = os.environ.get("MINIO_ACCESS_KEY", "")
        secret_key = os.environ.get("MINIO_SECRET_KEY", "")
        bucket = os.environ.get("MINIO_BUCKET", "docrunr")
        secure = os.environ.get("DOCRUNR_INTEGRATION_MINIO_SECURE", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        if not access_key or not secret_key:
            raise RuntimeError(
                "MinIO integration storage requires MINIO_ACCESS_KEY and MINIO_SECRET_KEY "
                "(e.g. from .env matching docker-compose.minio.yml)"
            )
        return cls(
            repo_root=repo_root,
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            secure=secure,
        )

    def clear(self) -> None:
        for prefix in ("input/", "output/"):
            for obj in self._client.list_objects(self._bucket, prefix=prefix, recursive=True):
                self._client.remove_object(self._bucket, obj.object_name)

    def stage_input(self, sample: Path, job_id: str) -> str:
        ext = sample.suffix.lower()
        rel = input_relative_path(job_id, ext, now=datetime.now(UTC))
        key = _norm_key(rel)
        self._client.fput_object(self._bucket, key, str(sample))
        return rel

    def exists(self, rel_path: str) -> bool:
        key = _norm_key(rel_path)
        try:
            self._client.stat_object(self._bucket, key)
            return True
        except Exception:
            return False

    def count_inputs(self) -> int:
        return sum(
            1 for _ in self._client.list_objects(self._bucket, prefix="input/", recursive=True)
        )

    def count_outputs(self) -> int:
        return sum(
            1 for _ in self._client.list_objects(self._bucket, prefix="output/", recursive=True)
        )


def integration_storage_from_env(repo_root: Path) -> IntegrationStorage:
    """Resolve storage from env (``DOCRUNR_INTEGRATION_STORAGE`` or ``INTEGRATION_STORAGE``)."""
    raw = os.environ.get("DOCRUNR_INTEGRATION_STORAGE") or os.environ.get(
        "INTEGRATION_STORAGE", "local"
    )
    kind = raw.strip().lower()
    if kind == "minio":
        return MinioIntegrationStorage.from_env(repo_root)
    if kind == "local":
        data_root = Path(
            os.environ.get("DOCRUNR_INTEGRATION_DATA", str(repo_root / ".data"))
        ).resolve()
        data_root.mkdir(parents=True, exist_ok=True)
        return LocalIntegrationStorage(data_root)
    raise ValueError(f"Unknown integration storage {raw!r}; expected 'local' or 'minio'")
