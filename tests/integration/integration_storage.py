"""Host-side storage helpers for integration tests (local bind mount vs S3 endpoint)."""

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


class S3IntegrationStorage(IntegrationStorage):
    """Talk to the configured S3 endpoint using the same bucket and keys as the worker."""

    def __init__(
        self,
        *,
        repo_root: Path,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        import boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import ClientError

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=BotoConfig(s3={"addressing_style": "path"}),
        )
        self._client_error = ClientError
        self._bucket = bucket
        self._region = region
        self._report_dir = Path(
            os.environ.get("DOCRUNR_INTEGRATION_DATA", str(repo_root / ".data"))
        ).resolve()
        self._report_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_bucket()

    @property
    def report_dir(self) -> Path:
        return self._report_dir

    @classmethod
    def from_env(cls, repo_root: Path) -> S3IntegrationStorage:
        endpoint = os.environ.get("DOCRUNR_INTEGRATION_S3_ENDPOINT", "http://127.0.0.1:8333")
        access_key = os.environ.get("S3_ACCESS_KEY", "")
        secret_key = os.environ.get("S3_SECRET_KEY", "")
        bucket = os.environ.get("S3_BUCKET", "docrunr")
        region = os.environ.get("S3_REGION", "us-east-1")
        if not access_key or not secret_key:
            raise RuntimeError(
                "S3 integration storage requires S3_ACCESS_KEY and S3_SECRET_KEY "
                "(e.g. from .env matching docker-compose.seaweedfs.yml)"
            )
        return cls(
            repo_root=repo_root,
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            region=region,
        )

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
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self._region}
        self._client.create_bucket(**create_kwargs)

    def clear(self) -> None:
        for prefix in ("input/", "output/"):
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    self._client.delete_object(Bucket=self._bucket, Key=obj["Key"])

    def stage_input(self, sample: Path, job_id: str) -> str:
        ext = sample.suffix.lower()
        rel = input_relative_path(job_id, ext, now=datetime.now(UTC))
        key = _norm_key(rel)
        self._client.upload_file(str(sample), self._bucket, key)
        return rel

    def exists(self, rel_path: str) -> bool:
        key = _norm_key(rel_path)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client_error:
            return False

    def count_inputs(self) -> int:
        return self._count_objects("input/")

    def count_outputs(self) -> int:
        return self._count_objects("output/")

    def _count_objects(self, prefix: str) -> int:
        paginator = self._client.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            count += len(page.get("Contents", []))
        return count


def integration_storage_from_env(repo_root: Path) -> IntegrationStorage:
    """Resolve storage from env (``DOCRUNR_INTEGRATION_STORAGE`` or ``INTEGRATION_STORAGE``)."""
    raw = os.environ.get("DOCRUNR_INTEGRATION_STORAGE") or os.environ.get(
        "INTEGRATION_STORAGE", "local"
    )
    kind = raw.strip().lower()
    if kind in {"s3", "minio"}:
        return S3IntegrationStorage.from_env(repo_root)
    if kind == "local":
        data_root = Path(
            os.environ.get("DOCRUNR_INTEGRATION_DATA", str(repo_root / ".data"))
        ).resolve()
        data_root.mkdir(parents=True, exist_ok=True)
        return LocalIntegrationStorage(data_root)
    raise ValueError(f"Unknown integration storage {raw!r}; expected 'local' or 's3'")
