"""Tests for data models."""

from __future__ import annotations

from pathlib import Path

import docrunr
from docrunr.models import BatchReport, Chunk, Result


class TestChunk:
    def test_to_dict(self) -> None:
        c = Chunk(
            chunk_id="chunk_1",
            source_doc_id="doc_1",
            chunk_index=0,
            text="hello",
            token_count=1,
            char_count=5,
            splitter_version="recursive_v1_token300_overlap0",
            section_path=["Intro"],
        )
        d = c.to_dict()
        assert d == {
            "chunk_index": 0,
            "text": "hello",
            "section_path": ["Intro"],
            "token_count": 1,
            "char_count": 5,
        }

    def test_compat_aliases(self) -> None:
        c = Chunk(
            chunk_id="chunk_1",
            source_doc_id="doc_1",
            chunk_index=2,
            text="hello",
            token_count=7,
            char_count=5,
            splitter_version="recursive_v1_token300_overlap0",
        )
        assert c.index == 2
        assert c.tokens == 7


class TestResult:
    def test_ok(self) -> None:
        r = Result(source="test.txt", markdown="# Hello")
        assert r.ok is True

    def test_error(self) -> None:
        r = Result(source="test.txt", markdown="", error="broken")
        assert r.ok is False

    def test_compute_hash(self) -> None:
        r = Result(source="test.txt", markdown="# Hello")
        r.compute_hash()
        assert r.content_hash.startswith("sha256:")

    def test_compute_totals(self) -> None:
        r = Result(
            source="test.txt",
            markdown="# Hello",
            chunks=[
                Chunk(
                    chunk_id="chunk_a",
                    source_doc_id="doc_1",
                    chunk_index=0,
                    text="a",
                    token_count=10,
                    char_count=1,
                    splitter_version="recursive_v1_token300_overlap0",
                ),
                Chunk(
                    chunk_id="chunk_b",
                    source_doc_id="doc_1",
                    chunk_index=1,
                    text="b",
                    token_count=20,
                    char_count=1,
                    splitter_version="recursive_v1_token300_overlap0",
                ),
            ],
        )
        r.compute_totals()
        assert r.total_tokens == 30

    def test_to_dict_key_order(self) -> None:
        r = Result(source="test.txt", markdown="# Hello")
        r.compute_hash()
        r.compute_totals()
        d = r.to_dict()
        keys = list(d.keys())
        assert keys == [
            "docrunr_version",
            "source",
            "content_hash",
            "mime_type",
            "size_bytes",
            "parser",
            "duration_seconds",
            "total_tokens",
            "content",
            "chunks",
        ]

    def test_write(self, tmp_out: Path) -> None:
        r = Result(
            source="test.txt",
            markdown="# Hello\n",
            chunks=[
                Chunk(
                    chunk_id="chunk_hello",
                    source_doc_id="doc_hello",
                    chunk_index=0,
                    text="# Hello",
                    token_count=2,
                    char_count=7,
                    splitter_version="recursive_v1_token300_overlap0",
                )
            ],
            mime_type="text/plain",
            size_bytes=8,
            parser="PlainTextParser",
            duration_seconds=0.01,
        )
        r.compute_hash()
        r.compute_totals()
        md_path, json_path = r.write(tmp_out, "test")
        assert md_path.exists()
        assert json_path.exists()
        assert md_path.read_text() == "# Hello\n"

        import json

        data = json.loads(json_path.read_text())
        assert data["docrunr_version"] == docrunr.__version__
        assert data["source"] == "test.txt"
        assert data["mime_type"] == "text/plain"
        assert data["size_bytes"] == 8
        assert data["parser"] == "PlainTextParser"
        assert data["content"] == "# Hello\n"
        assert len(data["chunks"]) == 1
        assert "chunk_id" not in data["chunks"][0]
        assert data["chunks"][0]["section_path"] == []


class TestBatchReport:
    def test_add_success(self) -> None:
        report = BatchReport()
        r = Result(
            source="a.txt",
            markdown="hello",
            chunks=[
                Chunk(
                    chunk_id="chunk_1",
                    source_doc_id="doc_1",
                    chunk_index=0,
                    text="hello",
                    token_count=1,
                    char_count=5,
                    splitter_version="recursive_v1_token300_overlap0",
                )
            ],
        )
        r.compute_totals()
        report.add(r)
        assert report.succeeded == 1
        assert report.failed == 0

    def test_add_failure(self) -> None:
        report = BatchReport()
        r = Result(source="a.txt", markdown="", error="fail")
        report.add(r)
        assert report.succeeded == 0
        assert report.failed == 1

    def test_write(self, tmp_out: Path) -> None:
        report = BatchReport(total=1, succeeded=1, duration_seconds=1.5)
        report.files = [{"file": "a.txt", "status": "ok", "chunks": 1, "tokens": 10}]
        path = report.write(tmp_out)
        assert path.exists()
        assert "_report.json" in path.name
