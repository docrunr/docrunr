"""Tests for local storage backend."""

from __future__ import annotations

from pathlib import Path

import pytest
from docrunr_worker.storage import LocalStorage


class TestLocalStorage:
    def test_write_and_read(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))

        src = tmp_path / "source.txt"
        src.write_text("hello")

        storage.write(src, "output/2026/03/15/14/abc123.txt")

        result = storage.read("output/2026/03/15/14/abc123.txt")
        assert result.read_text() == "hello"

    def test_exists(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))

        assert not storage.exists("missing.txt")

        (tmp_path / "present.txt").write_text("here")
        assert storage.exists("present.txt")

    def test_read_missing_raises(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))

        try:
            storage.read("nonexistent.txt")
            raise AssertionError("Expected FileNotFoundError")
        except FileNotFoundError:
            pass

    def test_write_creates_directories(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))

        src = tmp_path / "data.bin"
        src.write_bytes(b"\x00\x01\x02")

        storage.write(src, "deep/nested/path/file.bin")

        result = storage.read("deep/nested/path/file.bin")
        assert result.read_bytes() == b"\x00\x01\x02"

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError):
            storage.read("../outside.txt")
        assert storage.exists("../outside.txt") is False

    def test_rejects_absolute_destination(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        src = tmp_path / "src.txt"
        src.write_text("hello")
        with pytest.raises(ValueError):
            storage.write(src, "/tmp/escape.txt")

    def test_cleanup_is_noop_for_local_storage(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        p = tmp_path / "keep.txt"
        p.write_text("keep")
        storage.cleanup(p)
        assert p.is_file()

    def test_delete_removes_stored_object(self, tmp_path: Path) -> None:
        storage = LocalStorage(str(tmp_path))
        src = tmp_path / "src.bin"
        src.write_bytes(b"data")
        storage.write(src, "input/2026/04/11/14/delme.pdf")
        assert storage.exists("input/2026/04/11/14/delme.pdf")
        storage.delete("input/2026/04/11/14/delme.pdf")
        assert not storage.exists("input/2026/04/11/14/delme.pdf")
