"""Tests for LLM worker storage abstraction."""

from __future__ import annotations

from pathlib import Path

import pytest
from docrunr_worker_llm.storage import LocalStorage


class TestLocalStorage:
    def test_read_write(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        local = tmp_path / "src.txt"
        local.write_text("hello")
        storage.write(local, "output/doc.txt")
        read_path = storage.read("output/doc.txt")
        assert read_path.read_text() == "hello"

    def test_read_not_found(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(FileNotFoundError):
            storage.read("missing/file.txt")

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError, match="escapes"):
            storage.read("../../etc/passwd")

    def test_absolute_path_blocked(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError, match="relative"):
            storage.read("/etc/passwd")

    def test_exists(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        assert not storage.exists("missing.txt")
        (tmp_path / "present.txt").write_text("here")
        assert storage.exists("present.txt")

    def test_delete(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        f = tmp_path / "doomed.txt"
        f.write_text("bye")
        storage.delete("doomed.txt")
        assert not f.exists()

    def test_cleanup_is_noop(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        f = tmp_path / "keep.txt"
        f.write_text("safe")
        storage.cleanup(f)
        assert f.exists()
