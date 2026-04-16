"""Tests for LLM worker SQLite job store."""

from __future__ import annotations

import time
from pathlib import Path

from docrunr_worker_llm.job_store import SQLiteJobStore


def test_create_and_query_empty(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    store = SQLiteJobStore(str(db))
    store.start()
    try:
        result = store.stats_dict()
        assert result["processed"] == 0
        assert result["failed"] == 0
        assert result["recent_jobs_count"] == 0
    finally:
        store.stop()


def test_enqueue_and_query_job(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    store = SQLiteJobStore(str(db))
    store.start()
    try:
        store.enqueue_job(
            {
                "job_id": "j1",
                "status": "ok",
                "filename": "test.pdf",
                "source_path": "input/test.pdf",
                "chunks_path": "output/test.json",
                "llm_profile": "embed-local",
                "provider": "openai",
                "chunk_count": 5,
                "vector_count": 5,
                "duration_seconds": 1.5,
                "artifact_path": "output/test.embeddings.json",
                "error": None,
            }
        )
        time.sleep(1.0)

        jobs = store.jobs_dict()
        assert jobs["total"] == 1
        assert jobs["items"][0]["job_id"] == "j1"
        assert jobs["items"][0]["llm_profile"] == "embed-local"

        stats = store.stats_dict()
        assert stats["processed"] == 1
        assert stats["failed"] == 0
    finally:
        store.stop()


def test_enqueue_error_job(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    store = SQLiteJobStore(str(db))
    store.start()
    try:
        store.enqueue_job(
            {
                "job_id": "j2",
                "status": "error",
                "filename": "bad.pdf",
                "source_path": "input/bad.pdf",
                "chunks_path": "output/bad.json",
                "llm_profile": "",
                "provider": "",
                "chunk_count": 0,
                "vector_count": 0,
                "duration_seconds": 0.0,
                "artifact_path": None,
                "error": "LiteLLM timeout",
            }
        )
        time.sleep(1.0)

        stats = store.stats_dict()
        assert stats["processed"] == 0
        assert stats["failed"] == 1
    finally:
        store.stop()


def test_filter_by_status(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    store = SQLiteJobStore(str(db))
    store.start()
    try:
        for i, status in enumerate(["ok", "error", "ok"]):
            store.enqueue_job(
                {
                    "job_id": f"j{i}",
                    "status": status,
                    "filename": f"file{i}.pdf",
                    "source_path": f"input/file{i}.pdf",
                    "chunks_path": f"output/file{i}.json",
                    "llm_profile": "",
                    "provider": "",
                    "chunk_count": 0,
                    "vector_count": 0,
                    "duration_seconds": 0.0,
                    "artifact_path": None,
                    "error": "fail" if status == "error" else None,
                }
            )
        time.sleep(1.0)

        ok_jobs = store.jobs_dict(status="ok")
        assert ok_jobs["total"] == 2

        err_jobs = store.jobs_dict(status="error")
        assert err_jobs["total"] == 1
    finally:
        store.stop()
