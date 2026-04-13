"""SQLite-backed persistence for worker UI jobs and aggregate stats."""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, SimpleQueue

from docrunr_worker.job_status import ERROR, OK, PROCESSING, is_terminal, replay_stats_transition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistedJob:
    job_id: str
    status: str
    filename: str
    source_path: str
    markdown_path: str | None
    chunks_path: str | None
    total_tokens: int
    chunk_count: int
    duration_seconds: float
    error: str | None
    received_at: str
    finished_at: str | None
    updated_at: str | None
    mime_type: str
    size_bytes: int
    priority: int


class _StopSignal:
    pass


_STOP_SIGNAL = _StopSignal()


class SQLiteJobStore:
    """Asynchronous SQLite writer with synchronous read queries for UI endpoints."""

    def __init__(
        self,
        db_path: str,
        *,
        batch_size: int = 100,
    ) -> None:
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
                name="sqlite-job-store",
            )
            self._thread.start()
            logger.info("SQLite job store started at %s", self._db_path)

    def stop(self, *, timeout: float = 5.0) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.put(_STOP_SIGNAL)
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("SQLite job store writer did not stop cleanly")
        else:
            logger.info("SQLite job store stopped")

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
                "FROM worker_stats WHERE id = 1"
            ).fetchone()
            recent_row = conn.execute("SELECT COUNT(*) AS c FROM job_events").fetchone()

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
                f"SELECT COUNT(*) AS total FROM job_events {where_sql}",
                where_params,
            ).fetchone()
            rows = conn.execute(
                (
                    "SELECT job_id, status, filename, source_path, markdown_path, chunks_path, "
                    "total_tokens, chunk_count, duration_seconds, error, received_at, "
                    "finished_at, updated_at, mime_type, size_bytes, priority "
                    f"FROM job_events {where_sql} "
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
                    "markdown_path": row["markdown_path"],
                    "chunks_path": row["chunks_path"],
                    "total_tokens": int(row["total_tokens"]),
                    "chunk_count": int(row["chunk_count"]),
                    "duration_seconds": float(row["duration_seconds"]),
                    "error": row["error"],
                    "received_at": row["received_at"],
                    "finished_at": row["finished_at"],
                    "updated_at": row["updated_at"],
                    "mime_type": row["mime_type"] or "",
                    "size_bytes": int(row["size_bytes"] or 0),
                    "priority": int(row["priority"] or 0),
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
            "INSERT INTO job_events ("
            "job_id, status, filename, source_path, markdown_path, chunks_path, "
            "total_tokens, chunk_count, duration_seconds, error, "
            "received_at, finished_at, updated_at, mime_type, size_bytes, priority, "
            "replay_stats_suppress"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET "
            "status = excluded.status, "
            "filename = excluded.filename, "
            "source_path = excluded.source_path, "
            "markdown_path = excluded.markdown_path, "
            "chunks_path = excluded.chunks_path, "
            "total_tokens = excluded.total_tokens, "
            "chunk_count = excluded.chunk_count, "
            "duration_seconds = excluded.duration_seconds, "
            "error = excluded.error, "
            "replay_stats_suppress = excluded.replay_stats_suppress, "
            "received_at = CASE "
            "  WHEN excluded.status = ? THEN excluded.received_at "
            "  ELSE COALESCE(job_events.received_at, excluded.received_at) "
            "END, "
            "finished_at = CASE "
            "  WHEN excluded.status IN (?, ?) THEN excluded.finished_at "
            "  ELSE NULL "
            "END, "
            "updated_at = excluded.updated_at, "
            "mime_type = excluded.mime_type, "
            "size_bytes = excluded.size_bytes, "
            "priority = excluded.priority"
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
                        "SELECT status, replay_stats_suppress FROM job_events WHERE job_id = ?",
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
                            job.markdown_path,
                            job.chunks_path,
                            job.total_tokens,
                            job.chunk_count,
                            job.duration_seconds,
                            job.error,
                            job.received_at,
                            job.finished_at,
                            job.updated_at,
                            job.mime_type,
                            job.size_bytes,
                            job.priority,
                            new_sup,
                            PROCESSING,
                            OK,
                            ERROR,
                        ),
                    )

                last_job_at = max(transitioned_finished_at, default=None)

                conn.execute(
                    (
                        "UPDATE worker_stats "
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
                    (
                        ok_count,
                        error_count,
                        duration_total,
                        last_job_at,
                        last_job_at,
                        last_job_at,
                    ),
                )
        except Exception:
            logger.exception("Failed writing %d job event(s) to SQLite", len(events))

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=5.0,
            check_same_thread=False,
        )
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
            CREATE TABLE IF NOT EXISTS worker_stats (
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
            "INSERT INTO worker_stats "
            "(id, processed, failed, total_duration, last_job_at, jobs_total) "
            "VALUES (1, 0, 0, 0, NULL, 0) "
            "ON CONFLICT(id) DO NOTHING"
        )

        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_events'"
        ).fetchone()
        if exists is None:
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
                    priority INTEGER NOT NULL DEFAULT 0,
                    replay_stats_suppress INTEGER NOT NULL DEFAULT 0
                )
                """
            )
        else:
            SQLiteJobStore._migrate_job_events_columns(conn)
            SQLiteJobStore._migrate_job_events_lifecycle(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_job_events_received_at ON job_events(received_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_job_events_status_received "
            "ON job_events(status, received_at DESC)"
        )
        conn.execute("DROP INDEX IF EXISTS idx_job_events_finished_at")
        conn.execute("DROP INDEX IF EXISTS idx_job_events_status_finished")

    @staticmethod
    def _migrate_job_events_columns(conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(job_events)").fetchall()
        names = {str(row["name"]) for row in rows}
        if "mime_type" not in names:
            conn.execute("ALTER TABLE job_events ADD COLUMN mime_type TEXT NOT NULL DEFAULT ''")
        if "size_bytes" not in names:
            conn.execute("ALTER TABLE job_events ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0")
        if "replay_stats_suppress" not in names:
            conn.execute(
                "ALTER TABLE job_events ADD COLUMN replay_stats_suppress INTEGER NOT NULL DEFAULT 0"
            )
        if "priority" not in names:
            conn.execute("ALTER TABLE job_events ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _migrate_job_events_lifecycle(conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(job_events)").fetchall()
        names = {str(row["name"]) for row in rows}
        finished_row = next((r for r in rows if str(r["name"]) == "finished_at"), None)
        finished_not_null = finished_row is not None and int(finished_row["notnull"]) == 1

        needs_rebuild = "received_at" not in names or finished_not_null
        if not needs_rebuild:
            if "updated_at" not in names:
                conn.execute("ALTER TABLE job_events ADD COLUMN updated_at TEXT")
            return

        conn.execute(
            """
            CREATE TABLE job_events__new (
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
                priority INTEGER NOT NULL DEFAULT 0,
                replay_stats_suppress INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        has_received = "received_at" in names
        received_expr = "received_at" if has_received else "finished_at"
        has_priority = "priority" in names
        priority_expr = "COALESCE(priority, 0)" if has_priority else "0"

        conn.execute(
            f"""
            INSERT INTO job_events__new (
                job_id, status, filename, source_path, markdown_path, chunks_path,
                total_tokens, chunk_count, duration_seconds, error,
                received_at, finished_at, updated_at, mime_type, size_bytes,
                priority, replay_stats_suppress
            )
            SELECT
                job_id, status, filename, source_path, markdown_path, chunks_path,
                total_tokens, chunk_count, duration_seconds, error,
                COALESCE({received_expr}, finished_at) AS received_at,
                finished_at,
                NULL AS updated_at,
                COALESCE(mime_type, '') AS mime_type,
                COALESCE(size_bytes, 0) AS size_bytes,
                {priority_expr} AS priority,
                0 AS replay_stats_suppress
            FROM job_events
            WHERE id IN (SELECT MAX(id) FROM job_events GROUP BY job_id)
            """
        )
        conn.execute("DROP TABLE job_events")
        conn.execute("ALTER TABLE job_events__new RENAME TO job_events")
        SQLiteJobStore._recompute_worker_stats_from_job_events(conn)

    @staticmethod
    def _recompute_worker_stats_from_job_events(conn: sqlite3.Connection) -> None:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0) AS processed,
                COALESCE(SUM(CASE WHEN status = ? THEN 1 ELSE 0 END), 0) AS failed,
                COALESCE(SUM(CASE WHEN status = ? THEN duration_seconds ELSE 0 END), 0)
                    AS total_duration,
                MAX(CASE WHEN status IN (?, ?) THEN finished_at END) AS last_job_at
            FROM job_events
            """,
            (OK, ERROR, OK, OK, ERROR),
        ).fetchone()
        conn.execute(
            (
                "UPDATE worker_stats SET processed = ?, failed = ?, total_duration = ?, "
                "last_job_at = ? WHERE id = 1"
            ),
            (
                int(row["processed"]),
                int(row["failed"]),
                float(row["total_duration"]),
                row["last_job_at"],
            ),
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


def _event_to_job(event: dict[str, object]) -> PersistedJob:
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

    return PersistedJob(
        job_id=_as_non_empty_str(event.get("job_id"), default="unknown"),
        status=status,
        filename=_as_non_empty_str(event.get("filename"), default="unknown"),
        source_path=_as_non_empty_str(event.get("source_path"), default="unknown"),
        markdown_path=_as_optional_str(event.get("markdown_path")),
        chunks_path=_as_optional_str(event.get("chunks_path")),
        total_tokens=_as_int(event.get("total_tokens")),
        chunk_count=_as_int(event.get("chunk_count")),
        duration_seconds=_as_float(event.get("duration_seconds")),
        error=_as_optional_str(event.get("error")),
        received_at=received_at,
        finished_at=finished_at,
        updated_at=_as_optional_str(event.get("updated_at")),
        mime_type=_as_mime_type(event.get("mime_type")),
        size_bytes=_as_int(event.get("size_bytes")),
        priority=_as_job_priority(event.get("priority")),
    )


def _as_job_priority(value: object) -> int:
    p = _as_int(value)
    return max(0, min(255, p))


def _as_mime_type(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


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
