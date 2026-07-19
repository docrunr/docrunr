"""SQLite-backed API job projection and transactional outbox."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class JobRepository:
    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    content_type TEXT,
                    source_path TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    llm_profile TEXT,
                    markdown_path TEXT,
                    chunks_path TEXT,
                    tokens_used INTEGER,
                    chars_used INTEGER,
                    chunk_count INTEGER,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    llm_state TEXT,
                    llm_provider TEXT,
                    llm_artifact_path TEXT,
                    llm_chunk_count INTEGER,
                    llm_vector_count INTEGER,
                    llm_error_message TEXT,
                    llm_completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_api_jobs_created ON jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_api_jobs_state_created
                    ON jobs(state, created_at DESC);
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id) ON DELETE CASCADE,
                    body BLOB NOT NULL,
                    priority INTEGER NOT NULL,
                    published_at TEXT
                );
                """
            )

    def create_job(
        self,
        *,
        job_id: str,
        file_name: str,
        file_size: int,
        content_type: str | None,
        source_path: str,
        priority: int,
        llm_profile: str | None,
        body: bytes,
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, state, file_name, file_size, content_type, source_path,
                    priority, llm_profile, created_at, llm_state
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    file_name,
                    file_size,
                    content_type,
                    source_path,
                    priority,
                    llm_profile,
                    now,
                    "queued" if llm_profile else None,
                ),
            )
            conn.execute(
                "INSERT INTO outbox (job_id, body, priority) VALUES (?, ?, ?)",
                (job_id, body, priority),
            )

    def delete_job(self, job_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))

    def pending_outbox(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, job_id, body, priority FROM outbox "
                "WHERE published_at IS NULL ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_published(self, outbox_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox SET published_at = ? WHERE id = ?",
                (utc_now(), outbox_id),
            )

    def is_published(self, job_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT published_at FROM outbox WHERE job_id = ?", (job_id,)
            ).fetchone()
        return row is not None and row["published_at"] is not None

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_jobs(
        self, *, limit: int, offset: int, state: str | None
    ) -> tuple[list[dict[str, Any]], bool]:
        params: list[object] = []
        where = ""
        if state:
            where = "WHERE state = ?"
            params.append(state)
        params.extend((limit + 1, offset))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows[:limit]], len(rows) > limit

    def apply_lifecycle(self, payload: dict[str, Any]) -> None:
        if payload.get("state") != "processing":
            return
        job_id = str(payload.get("job_id", ""))
        if not job_id:
            return
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET state = 'processing', started_at = COALESCE(started_at, ?)
                WHERE job_id = ? AND state = 'queued'
                """,
                (str(payload.get("occurred_at") or utc_now()), job_id),
            )

    def apply_extraction_result(self, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id", ""))
        if not job_id:
            return
        ok = payload.get("status") == "ok"
        completed = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    state = ?, markdown_path = ?, chunks_path = ?, tokens_used = ?,
                    chars_used = ?, chunk_count = ?, error_message = ?,
                    started_at = COALESCE(started_at, created_at), completed_at = ?
                WHERE job_id = ?
                """,
                (
                    "succeeded" if ok else "failed",
                    payload.get("markdown_path"),
                    payload.get("chunks_path"),
                    payload.get("total_tokens"),
                    payload.get("total_chars"),
                    payload.get("chunk_count"),
                    payload.get("error"),
                    completed,
                    job_id,
                ),
            )

    def apply_llm_result(self, payload: dict[str, Any]) -> None:
        job_id = str(payload.get("extract_job_id", ""))
        if not job_id:
            return
        ok = payload.get("status") == "ok"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    llm_state = ?, llm_provider = ?, llm_artifact_path = ?,
                    llm_chunk_count = ?, llm_vector_count = ?,
                    llm_error_message = ?, llm_completed_at = ?
                WHERE job_id = ?
                """,
                (
                    "succeeded" if ok else "failed",
                    payload.get("provider"),
                    payload.get("artifact_path"),
                    payload.get("chunk_count"),
                    payload.get("vector_count"),
                    payload.get("error"),
                    utc_now(),
                    job_id,
                ),
            )

    def healthy(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
