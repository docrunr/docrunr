"""Backward-compatible imports for shared storage primitives."""

from docrunr_runtime.storage import LocalStorage, S3Storage, StorageBackend, create_storage

__all__ = ["LocalStorage", "S3Storage", "StorageBackend", "create_storage"]
