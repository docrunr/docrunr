"""Tests for SQLite-backed worker UI persistence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from docrunr_worker.handler import parse_job_request_from_body
from docrunr_worker.job_status import PROCESSING
from docrunr_worker.job_store import SQLiteJobStore


def _job(
    *,
    job_id: str,
    status: str,
    filename: str,
    source_path: str,
    finished_at: str | None = None,
    duration_seconds: float,
    total_tokens: int = 0,
    chunk_count: int = 0,
    markdown_path: str | None = None,
    chunks_path: str | None = None,
    error: str | None = None,
    mime_type: str = "",
    size_bytes: int = 0,
    received_at: str | None = None,
    priority: int = 0,
) -> dict[str, object]:
    out: dict[str, object] = {
        "job_id": job_id,
        "status": status,
        "filename": filename,
        "source_path": source_path,
        "markdown_path": markdown_path,
        "chunks_path": chunks_path,
        "total_tokens": total_tokens,
        "chunk_count": chunk_count,
        "duration_seconds": duration_seconds,
        "error": error,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "priority": priority,
    }
    if finished_at is not None:
        out["finished_at"] = finished_at
    if received_at:
        out["received_at"] = received_at
    return out


def test_persists_jobs_and_stats(tmp_path: Path) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path), batch_size=10)
    store.start()

    store.enqueue_job(
        _job(
            job_id="job-1",
            status="ok",
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            markdown_path="output/2026/04/11/14/a.md",
            chunks_path="output/2026/04/11/14/a.json",
            total_tokens=10,
            chunk_count=2,
            duration_seconds=1.25,
            finished_at="2026-04-02T19:39:38Z",
            mime_type="application/pdf",
            size_bytes=12_288,
        )
    )
    store.enqueue_job(
        _job(
            job_id="job-2",
            status="error",
            filename="b.pdf",
            source_path="input/2026/04/11/14/b.pdf",
            duration_seconds=0.5,
            error="boom",
            finished_at="2026-04-02T19:39:39Z",
        )
    )

    store.stop()

    jobs = store.jobs_dict(limit=100)
    assert jobs["total"] == 2
    assert jobs["count"] == 2
    assert jobs["items"][0]["job_id"] == "job-2"
    assert jobs["items"][1]["job_id"] == "job-1"
    assert jobs["items"][1]["mime_type"] == "application/pdf"
    assert jobs["items"][1]["size_bytes"] == 12_288
    assert jobs["items"][1]["priority"] == 0
    assert jobs["items"][0]["mime_type"] == ""
    assert jobs["items"][0]["size_bytes"] == 0
    assert jobs["items"][0]["priority"] == 0

    stats = store.stats_dict()
    assert stats["processed"] == 1
    assert stats["failed"] == 1
    assert stats["avg_duration_seconds"] == 1.25
    assert stats["last_job_at"] == "2026-04-02T19:39:39Z"
    assert stats["recent_jobs_count"] == 2


def test_filters_and_searches_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()

    store.enqueue_job(
        _job(
            job_id="alpha",
            status="ok",
            filename="contract.docx",
            source_path="input/2026/04/11/14/alpha.docx",
            duration_seconds=0.9,
            finished_at="2026-04-02T19:39:38Z",
        )
    )
    store.enqueue_job(
        _job(
            job_id="beta",
            status="error",
            filename="invoice.pdf",
            source_path="input/2026/04/11/14/beta.pdf",
            duration_seconds=0.3,
            error="failed",
            finished_at="2026-04-02T19:39:39Z",
        )
    )
    store.enqueue_job(
        _job(
            job_id="gamma",
            status="ok",
            filename="notes.txt",
            source_path="input/2026/04/11/14/gamma.txt",
            duration_seconds=0.2,
            finished_at="2026-04-02T19:39:40Z",
        )
    )

    store.stop()

    errored = store.jobs_dict(limit=100, status="error")
    assert errored["total"] == 1
    assert errored["items"][0]["job_id"] == "beta"

    searched = store.jobs_dict(limit=100, search="invoice")
    assert searched["total"] == 1
    assert searched["items"][0]["job_id"] == "beta"


def test_processing_then_terminal_upserts_single_row_and_stats_ignore_processing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()

    store.enqueue_job(
        _job(
            job_id="job-a",
            status=PROCESSING,
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            duration_seconds=0.0,
            received_at="2026-04-02T19:39:30Z",
        )
    )
    store.enqueue_job(
        _job(
            job_id="job-a",
            status="ok",
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            markdown_path="output/2026/04/11/14/a.md",
            chunks_path="output/2026/04/11/14/a.json",
            total_tokens=3,
            chunk_count=1,
            duration_seconds=0.8,
            finished_at="2026-04-02T19:39:40Z",
            mime_type="application/pdf",
            size_bytes=100,
        )
    )

    store.stop()

    jobs = store.jobs_dict(limit=100)
    assert jobs["total"] == 1
    row = jobs["items"][0]
    assert row["job_id"] == "job-a"
    assert row["status"] == "ok"
    assert row["received_at"] == "2026-04-02T19:39:30Z"
    assert row["finished_at"] == "2026-04-02T19:39:40Z"

    stats = store.stats_dict()
    assert stats["processed"] == 1
    assert stats["failed"] == 0
    assert stats["avg_duration_seconds"] == 0.8


def test_status_filter_accepts_processing(tmp_path: Path) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()
    store.enqueue_job(
        _job(
            job_id="p1",
            status=PROCESSING,
            filename="x.pdf",
            source_path="input/2026/04/11/14/x.pdf",
            duration_seconds=0.0,
            received_at="2026-04-02T20:00:00Z",
        )
    )
    store.enqueue_job(
        _job(
            job_id="done",
            status="ok",
            filename="y.pdf",
            source_path="input/2026/04/11/14/y.pdf",
            duration_seconds=0.1,
            finished_at="2026-04-02T20:00:01Z",
        )
    )
    store.stop()

    only_proc = store.jobs_dict(limit=100, status=PROCESSING)
    assert only_proc["total"] == 1
    assert only_proc["items"][0]["job_id"] == "p1"


def test_persists_across_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    first = SQLiteJobStore(str(db_path))
    first.start()
    first.enqueue_job(
        _job(
            job_id="job-1",
            status="ok",
            filename="x.pdf",
            source_path="input/2026/04/11/14/x.pdf",
            duration_seconds=0.4,
            finished_at="2026-04-02T19:39:38Z",
        )
    )
    first.stop()

    second = SQLiteJobStore(str(db_path))
    second.start()
    second.stop()

    jobs = second.jobs_dict(limit=100)
    assert jobs["total"] == 1
    assert jobs["items"][0]["job_id"] == "job-1"


def test_repeated_terminal_ok_upsert_does_not_recount_stats(tmp_path: Path) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()
    store.enqueue_job(
        _job(
            job_id="dup",
            status=PROCESSING,
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            duration_seconds=0.0,
            received_at="2026-04-02T10:00:00Z",
        )
    )
    store.enqueue_job(
        _job(
            job_id="dup",
            status="ok",
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            duration_seconds=2.0,
            finished_at="2026-04-02T10:00:01Z",
        )
    )
    store.enqueue_job(
        _job(
            job_id="dup",
            status="ok",
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            duration_seconds=99.0,
            finished_at="2026-04-02T10:00:02Z",
        )
    )
    store.stop()
    stats = store.stats_dict()
    assert stats["processed"] == 1
    assert stats["avg_duration_seconds"] == 2.0


def test_identical_malformed_body_distinct_delivery_ids_two_rows_and_failures(
    tmp_path: Path,
) -> None:
    """Same bytes as ``{}`` but different consumer delivery ids → one row per attempt."""
    body = b"{}"
    id_a = parse_job_request_from_body(body, delivery_id="aaa").job_id
    id_b = parse_job_request_from_body(body, delivery_id="bbb").job_id
    assert id_a != id_b
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()
    for jid, ts in [(id_a, "2026-04-02T12:00:00Z"), (id_b, "2026-04-02T12:00:01Z")]:
        store.enqueue_job(
            _job(
                job_id=jid,
                status="error",
                filename="unknown",
                source_path="unknown",
                duration_seconds=0.0,
                finished_at=ts,
                error="bad",
            )
        )
    store.stop()
    jobs = store.jobs_dict(limit=100)
    assert jobs["total"] == 2
    assert store.stats_dict()["failed"] == 2
    assert store.stats_dict()["recent_jobs_count"] == 2


def test_distinct_malformed_parse_bodies_distinct_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "docrunr.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()
    body_a = b"{}"
    body_b = json.dumps({"job_id": "x"}).encode()
    id_a = parse_job_request_from_body(body_a).job_id
    id_b = parse_job_request_from_body(body_b).job_id
    assert id_a != id_b
    for jid, ts in [(id_a, "2026-04-02T11:00:00Z"), (id_b, "2026-04-02T11:00:01Z")]:
        store.enqueue_job(
            _job(
                job_id=jid,
                status="error",
                filename="unknown",
                source_path="unknown",
                duration_seconds=0.0,
                finished_at=ts,
                error="bad",
            )
        )
    store.stop()
    jobs = store.jobs_dict(limit=100)
    assert jobs["total"] == 2
    assert {jobs["items"][0]["job_id"], jobs["items"][1]["job_id"]} == {id_a, id_b}


def test_cross_batch_replay_after_ok_does_not_recount_failure(tmp_path: Path) -> None:
    """Separate writer sessions: DB already ``ok``; later ``processing`` + ``error`` is a replay."""
    db_path = tmp_path / "docrunr.sqlite"
    first = SQLiteJobStore(str(db_path))
    first.start()
    first.enqueue_job(
        _job(
            job_id="replay-j",
            status="ok",
            filename="f.pdf",
            source_path="input/2026/04/11/14/replay-j.pdf",
            duration_seconds=1.0,
            finished_at="2026-04-02T10:00:00Z",
        )
    )
    first.stop()

    second = SQLiteJobStore(str(db_path))
    second.start()
    second.enqueue_job(
        _job(
            job_id="replay-j",
            status=PROCESSING,
            filename="f.pdf",
            source_path="input/2026/04/11/14/replay-j.pdf",
            duration_seconds=0.0,
            received_at="2026-04-02T11:00:00Z",
        )
    )
    second.enqueue_job(
        _job(
            job_id="replay-j",
            status="error",
            filename="f.pdf",
            source_path="input/2026/04/11/14/replay-j.pdf",
            duration_seconds=0.5,
            finished_at="2026-04-02T11:00:01Z",
            error="replay",
        )
    )
    second.stop()

    stats = second.stats_dict()
    assert stats["processed"] == 1
    assert stats["failed"] == 0


def test_migration_recomputes_worker_stats_after_dedupe(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE worker_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            processed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            total_duration REAL NOT NULL,
            last_job_at TEXT,
            jobs_total INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO worker_stats (id, processed, failed, total_duration, last_job_at, jobs_total) "
        "VALUES (1, 2, 0, 5.0, '2099-01-01T00:00:00Z', 0)"
    )
    conn.execute(
        """
        CREATE TABLE job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            status TEXT NOT NULL,
            filename TEXT NOT NULL,
            source_path TEXT NOT NULL,
            markdown_path TEXT,
            chunks_path TEXT,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            duration_seconds REAL NOT NULL DEFAULT 0,
            error TEXT,
            finished_at TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for rid, dur, fts in [
        (1, 1.0, "2026-04-01T12:00:00Z"),
        (2, 4.0, "2026-04-01T13:00:00Z"),
    ]:
        conn.execute(
            (
                "INSERT INTO job_events (id, job_id, status, filename, source_path, "
                "duration_seconds, finished_at) VALUES (?, 'same', 'ok', 'f', "
                "'input/2026/04/11/14/f.pdf', ?, ?)"
            ),
            (rid, dur, fts),
        )
    conn.commit()
    conn.close()

    store = SQLiteJobStore(str(db_path))
    store.start()
    store.stop()

    jobs = store.jobs_dict(limit=100)
    assert jobs["total"] == 1
    assert jobs["items"][0]["duration_seconds"] == 4.0

    stats = store.stats_dict()
    assert stats["processed"] == 1
    assert stats["failed"] == 0
    assert stats["avg_duration_seconds"] == 4.0
    assert stats["last_job_at"] == "2026-04-01T13:00:00Z"


def test_schema_migration_adds_priority_column(tmp_path: Path) -> None:
    """Existing DBs without ``priority`` get the column via ALTER."""
    db_path = tmp_path / "noprio.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE worker_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            processed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            total_duration REAL NOT NULL DEFAULT 0,
            last_job_at TEXT,
            jobs_total INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO worker_stats (id, processed, failed, total_duration, last_job_at, jobs_total) "
        "VALUES (1, 0, 0, 0, NULL, 0)"
    )
    conn.execute(
        """
        CREATE TABLE job_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            filename TEXT NOT NULL,
            source_path TEXT NOT NULL,
            markdown_path TEXT,
            chunks_path TEXT,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            duration_seconds REAL NOT NULL DEFAULT 0,
            error TEXT,
            received_at TEXT NOT NULL,
            finished_at TEXT,
            updated_at TEXT,
            mime_type TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            replay_stats_suppress INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "INSERT INTO job_events (job_id, status, filename, source_path, duration_seconds, "
        "received_at) VALUES ('j', 'ok', 'f.pdf', 'input/2026/04/11/14/j.pdf', 1.0, "
        "'2026-04-02T10:00:00Z')"
    )
    conn.commit()
    conn.close()

    store = SQLiteJobStore(str(db_path))
    store.start()
    store.enqueue_job(
        _job(
            job_id="j",
            status="ok",
            filename="f.pdf",
            source_path="input/2026/04/11/14/j.pdf",
            duration_seconds=1.0,
            finished_at="2026-04-02T10:00:00Z",
            priority=99,
        )
    )
    store.stop()

    cols = sqlite3.connect(db_path).execute("PRAGMA table_info(job_events)").fetchall()
    names = {str(r[1]) for r in cols}
    assert "priority" in names
    jobs = store.jobs_dict(limit=10)
    assert jobs["items"][0]["priority"] == 99


def test_persisted_priority_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "prio.sqlite"
    store = SQLiteJobStore(str(db_path))
    store.start()
    store.enqueue_job(
        _job(
            job_id="high",
            status="processing",
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            duration_seconds=0.0,
            received_at="2026-04-02T10:00:00Z",
            priority=200,
        )
    )
    store.enqueue_job(
        _job(
            job_id="high",
            status="ok",
            filename="a.pdf",
            source_path="input/2026/04/11/14/a.pdf",
            duration_seconds=0.5,
            finished_at="2026-04-02T10:00:01Z",
            priority=200,
        )
    )
    store.stop()
    jobs = store.jobs_dict(limit=10)
    assert jobs["items"][0]["priority"] == 200
