"""SQLite-backed persistence for LLM worker UI jobs and aggregate stats."""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, SimpleQueue

from docrunr_worker_llm.job_status import (
    ERROR,
    OK,
    PROCESSING,
    is_terminal,
    replay_stats_transition,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistedLlmJob:
    job_id: str
    status: str
    filename: str
    source_path: str
    chunks_path: str
    llm_profile: str
    provider: str
    chunk_count: int
    vector_count: int
    duration_seconds: float
    artifact_path: str | None
    error: str | None
    received_at: str
    finished_at: str | None
    updated_at: str | None


class _StopSignal:
    pass


_STOP_SIGNAL = _StopSignal()


class SQLiteJobStore:
    """Asynchronous SQLite writer with synchronous read queries for UI endpoints."""

    def __init__(self, db_path: str, *, batch_size: int = 100) -> None:
        self._db_path = Path(db_path)
        self._batch_size = max(1, batch_size)
        self._queue: SimpleQueue[dict[str, object] | _StopSignal] = SimpleQueue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._open_connection() as conn:
                self._ensure_schema(conn)

            self._thread = threading.Thread(
                target=self._writer_loop,
                daemon=True,
                name="sqlite-llm-job-store",
            )
            self._thread.start()
            logger.info("SQLite LLM job store started at %s", self._db_path)

    def stop(self, *, timeout: float = 5.0) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.put(_STOP_SIGNAL)
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("SQLite LLM job store writer did not stop cleanly")
        else:
            logger.info("SQLite LLM job store stopped")

    def enqueue_job(self, event: dict[str, object]) -> None:
        payload = dict(event)
        now = _now_utc_iso()
        payload.setdefault("updated_at", now)
        status = _as_non_empty_str(payload.get("status"), default="")
        if status == PROCESSING:
            payload.setdefault("received_at", now)
        else:
            payload.setdefault("finished_at", now)
        self._queue.put(payload)

    def stats_dict(self) -> dict[str, object]:
        with self._open_connection() as conn:
            row = conn.execute(
                "SELECT processed, failed, total_duration, last_job_at "
                "FROM llm_worker_stats WHERE id = 1"
            ).fetchone()
            recent_row = conn.execute("SELECT COUNT(*) AS c FROM llm_job_events").fetchone()

        recent_jobs_count = int(recent_row["c"]) if recent_row is not None else 0
        if row is None:
            return {
                "processed": 0,
                "failed": 0,
                "avg_duration_seconds": 0.0,
                "last_job_at": None,
                "recent_jobs_count": recent_jobs_count,
            }

        processed = int(row["processed"])
        total_duration = float(row["total_duration"])
        avg_duration = round(total_duration / processed, 2) if processed else 0.0
        return {
            "processed": processed,
            "failed": int(row["failed"]),
            "avg_duration_seconds": avg_duration,
            "last_job_at": row["last_job_at"],
            "recent_jobs_count": recent_jobs_count,
        }

    def jobs_dict(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, object]:
        bounded_limit = max(1, min(limit, 500))
        where_sql, where_params = _build_where_clause(status=status, search=search)

        with self._open_connection() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS total FROM llm_job_events {where_sql}",
                where_params,
            ).fetchone()
            rows = conn.execute(
                (
                    "SELECT job_id, status, filename, source_path, chunks_path, "
                    "llm_profile, provider, chunk_count, vector_count, duration_seconds, "
                    "artifact_path, error, received_at, finished_at, updated_at "
                    f"FROM llm_job_events {where_sql} "
                    "ORDER BY COALESCE(finished_at, received_at) DESC, id DESC LIMIT ?"
                ),
                [*where_params, bounded_limit],
            ).fetchall()

        items: list[dict[str, object]] = []
        for row in rows:
            items.append(
                {
                    "job_id": row["job_id"],
                    "status": row["status"],
                    "filename": row["filename"],
                    "source_path": row["source_path"],
                    "chunks_path": row["chunks_path"],
                    "llm_profile": row["llm_profile"] or "",
                    "provider": row["provider"] or "",
                    "chunk_count": int(row["chunk_count"]),
                    "vector_count": int(row["vector_count"]),
                    "duration_seconds": float(row["duration_seconds"]),
                    "artifact_path": row["artifact_path"],
                    "error": row["error"],
                    "received_at": row["received_at"],
                    "finished_at": row["finished_at"],
                    "updated_at": row["updated_at"],
                }
            )

        total = int(total_row["total"]) if total_row is not None else 0
        return {
            "items": items,
            "count": len(items),
            "total": total,
            "limit": bounded_limit,
        }

    def _writer_loop(self) -> None:
        with self._open_connection() as conn:
            self._ensure_schema(conn)
            should_stop = False
            while not should_stop:
                try:
                    first = self._queue.get(timeout=0.5)
                except Empty:
                    continue

                if isinstance(first, _StopSignal):
                    should_stop = True
                    continue

                batch: list[dict[str, object]] = [first]
                while len(batch) < self._batch_size:
                    try:
                        item = self._queue.get_nowait()
                    except Empty:
                        break
                    if isinstance(item, _StopSignal):
                        should_stop = True
                        break
                    batch.append(item)

                self._flush_batch(conn, batch)

            tail: list[dict[str, object]] = []
            while True:
                try:
                    item = self._queue.get_nowait()
                except Empty:
                    break
                if isinstance(item, _StopSignal):
                    continue
                tail.append(item)
                if len(tail) >= self._batch_size:
                    self._flush_batch(conn, tail)
                    tail = []
            if tail:
                self._flush_batch(conn, tail)

    def _flush_batch(self, conn: sqlite3.Connection, events: list[dict[str, object]]) -> None:
        if not events:
            return

        upsert_sql = (
            "INSERT INTO llm_job_events ("
            "job_id, status, filename, source_path, chunks_path, "
            "llm_profile, provider, chunk_count, vector_count, duration_seconds, "
            "artifact_path, error, received_at, finished_at, updated_at, "
            "replay_stats_suppress"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET "
            "status = excluded.status, "
            "filename = excluded.filename, "
            "source_path = excluded.source_path, "
            "chunks_path = excluded.chunks_path, "
            "llm_profile = excluded.llm_profile, "
            "provider = excluded.provider, "
            "chunk_count = excluded.chunk_count, "
            "vector_count = excluded.vector_count, "
            "duration_seconds = excluded.duration_seconds, "
            "artifact_path = excluded.artifact_path, "
            "error = excluded.error, "
            "replay_stats_suppress = excluded.replay_stats_suppress, "
            "received_at = CASE "
            "  WHEN excluded.status = ? THEN excluded.received_at "
            "  ELSE COALESCE(llm_job_events.received_at, excluded.received_at) "
            "END, "
            "finished_at = CASE "
            "  WHEN excluded.status IN (?, ?) THEN excluded.finished_at "
            "  ELSE NULL "
            "END, "
            "updated_at = excluded.updated_at"
        )

        try:
            with conn:
                ok_count = 0
                error_count = 0
                duration_total = 0.0
                transitioned_finished_at: list[str] = []

                for event in events:
                    job = _event_to_job(event)
                    prow = conn.execute(
                        "SELECT status, replay_stats_suppress FROM llm_job_events WHERE job_id = ?",
                        (job.job_id,),
                    ).fetchone()
                    cur_status = str(prow["status"]) if prow else None
                    cur_suppress = int(prow["replay_stats_suppress"]) if prow is not None else 0

                    ok_d, err_d, dur_d, fin_iso, new_sup = replay_stats_transition(
                        cur_status,
                        cur_suppress,
                        job.status,
                        incoming_duration_seconds=job.duration_seconds,
                        incoming_finished_at=job.finished_at,
                    )
                    ok_count += ok_d
                    error_count += err_d
                    duration_total += dur_d
                    if fin_iso:
                        transitioned_finished_at.append(fin_iso)

                    conn.execute(
                        upsert_sql,
                        (
                            job.job_id,
                            job.status,
                            job.filename,
                            job.source_path,
                            job.chunks_path,
                            job.llm_profile,
                            job.provider,
                            job.chunk_count,
                            job.vector_count,
                            job.duration_seconds,
                            job.artifact_path,
                            job.error,
                            job.received_at,
                            job.finished_at,
                            job.updated_at,
                            new_sup,
                            PROCESSING,
                            OK,
                            ERROR,
                        ),
                    )

                last_job_at = max(transitioned_finished_at, default=None)
                conn.execute(
                    (
                        "UPDATE llm_worker_stats "
                        "SET processed = processed + ?, "
                        "failed = failed + ?, "
                        "total_duration = total_duration + ?, "
                        "last_job_at = CASE "
                        "  WHEN ? IS NULL THEN last_job_at "
                        "  WHEN last_job_at IS NULL OR ? > last_job_at THEN ? "
                        "  ELSE last_job_at "
                        "END "
                        "WHERE id = 1"
                    ),
                    (ok_count, error_count, duration_total, last_job_at, last_job_at, last_job_at),
                )
        except Exception:
            logger.exception("Failed writing %d LLM job event(s) to SQLite", len(events))

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_worker_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                processed INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                total_duration REAL NOT NULL DEFAULT 0,
                last_job_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO llm_worker_stats (id, processed, failed, total_duration, last_job_at) "
            "VALUES (1, 0, 0, 0, NULL) "
            "ON CONFLICT(id) DO NOTHING"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                filename TEXT NOT NULL,
                source_path TEXT NOT NULL,
                chunks_path TEXT NOT NULL DEFAULT '',
                llm_profile TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                vector_count INTEGER NOT NULL DEFAULT 0,
                duration_seconds REAL NOT NULL DEFAULT 0,
                artifact_path TEXT,
                error TEXT,
                received_at TEXT NOT NULL,
                finished_at TEXT,
                updated_at TEXT,
                replay_stats_suppress INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_job_events_received_at "
            "ON llm_job_events(received_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_llm_job_events_status_received "
            "ON llm_job_events(status, received_at DESC)"
        )


def _build_where_clause(*, status: str | None, search: str | None) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []

    if status in {OK, ERROR, PROCESSING}:
        clauses.append("status = ?")
        params.append(status)

    if search:
        needle = f"%{search.casefold()}%"
        clauses.append(
            "(LOWER(job_id) LIKE ? OR LOWER(filename) LIKE ? OR LOWER(source_path) LIKE ?)"
        )
        params.extend([needle, needle, needle])

    if not clauses:
        return "", params
    return f"WHERE {' AND '.join(clauses)}", params


def _event_to_job(event: dict[str, object]) -> PersistedLlmJob:
    status = _as_non_empty_str(event.get("status"), default="unknown")
    finished_at = _as_optional_str(event.get("finished_at"))
    received_raw = _as_optional_str(event.get("received_at"))
    now = _now_utc_iso()
    if status == PROCESSING:
        received_at = received_raw or now
        finished_at = None
    else:
        received_at = received_raw or finished_at or now
        if is_terminal(status) and finished_at is None:
            finished_at = now

    return PersistedLlmJob(
        job_id=_as_non_empty_str(event.get("job_id"), default="unknown"),
        status=status,
        filename=_as_non_empty_str(event.get("filename"), default="unknown"),
        source_path=_as_non_empty_str(event.get("source_path"), default="unknown"),
        chunks_path=_as_non_empty_str(event.get("chunks_path"), default=""),
        llm_profile=_as_non_empty_str(event.get("llm_profile"), default=""),
        provider=_as_non_empty_str(event.get("provider"), default=""),
        chunk_count=_as_int(event.get("chunk_count")),
        vector_count=_as_int(event.get("vector_count")),
        duration_seconds=_as_float(event.get("duration_seconds")),
        artifact_path=_as_optional_str(event.get("artifact_path")),
        error=_as_optional_str(event.get("error")),
        received_at=received_at,
        finished_at=finished_at,
        updated_at=_as_optional_str(event.get("updated_at")),
    )


def _as_non_empty_str(value: object, *, default: str) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return default


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return str(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _now_utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
