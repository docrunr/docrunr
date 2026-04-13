"""Minimal health/stats HTTP endpoint; uses psutil for optional host CPU samples."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import mimetypes
import os
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlparse

from docrunr_worker.config import WorkerSettings
from docrunr_worker.job_messages import InvalidJobPriorityError, parse_upload_priority_query
from docrunr_worker.job_status import ERROR, OK, PROCESSING, replay_stats_transition
from docrunr_worker.rabbitmq_health import (
    configure_rabbitmq_health_probe,
    rabbitmq_reachable_for_api,
)
from docrunr_worker.uploads import UploadRequestError, process_upload_request

if TYPE_CHECKING:
    from docrunr_worker.job_store import SQLiteJobStore
    from docrunr_worker.storage import StorageBackend

logger = logging.getLogger(__name__)


def _coerce_job_int(value: object) -> int:
    try:
        return int(cast(Any, value) or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_job_float(value: object) -> float:
    try:
        return float(cast(Any, value) or 0)
    except (TypeError, ValueError):
        return 0.0


def _max_iso_z(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _finished_at_iso_for_stats(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    text = str(value).strip()
    return text if text else None


@dataclass
class WorkerStats:
    """Worker runtime counters with optional SQLite-backed persistence."""

    started_at: float = field(default_factory=time.time)
    processed: int = 0
    failed: int = 0
    total_duration: float = 0.0
    last_job_at: float | None = None
    # Consumer latch (connect/stop/reconnect). Overview health uses AMQP probe when configured.
    rabbitmq_connected: bool = False
    _jobs_by_id: dict[str, dict[str, object]] = field(default_factory=dict, repr=False)
    _memory_last_job_finished_at_iso: str | None = field(default=None, repr=False)
    _cpu_samples: deque[float] = field(default_factory=lambda: deque(maxlen=64), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _job_store: SQLiteJobStore | None = field(default=None, repr=False)

    def attach_job_store(self, job_store: SQLiteJobStore) -> None:
        with self._lock:
            self._job_store = job_store

    def record_success(self, _duration: float) -> None:  # skylos: ignore — caller passes duration
        """No-op: aggregate stats come from :meth:`record_job` (SQLite or memory)."""

    def record_failure(self) -> None:
        """No-op: aggregate stats come from :meth:`record_job` (SQLite or memory)."""

    @property
    def avg_duration(self) -> float:
        with self._lock:
            if self.processed == 0:
                return 0.0
            return round(self.total_duration / self.processed, 2)

    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)

    def health_dict(self) -> dict[str, object]:
        # ``health.rabbitmq`` = worker is ready for jobs: broker accepts AMQP (cached probe) AND
        # the consumer has completed ``connect()`` (latch). Probe alone is insufficient—e.g.
        # queue declare failures after TCP would still probe green.
        probed = rabbitmq_reachable_for_api()
        if probed is None:
            reachable = self.rabbitmq_connected
        else:
            reachable = probed and self.rabbitmq_connected
        return {
            "status": "ok",
            "rabbitmq": "connected" if reachable else "disconnected",
            "uptime_seconds": self.uptime_seconds,
        }

    def stats_dict(self) -> dict[str, object]:
        job_store = self._job_store
        if job_store is not None:
            try:
                return job_store.stats_dict()
            except Exception:
                logger.exception("Failed to read stats from SQLite; falling back to memory")

        with self._lock:
            avg = round(self.total_duration / self.processed, 2) if self.processed else 0.0
            return {
                "processed": self.processed,
                "failed": self.failed,
                "avg_duration_seconds": avg,
                "last_job_at": self._memory_last_job_finished_at_iso,
                "recent_jobs_count": len(self._jobs_by_id),
            }

    def overview_dict(self) -> dict[str, object]:
        return {
            "health": self.health_dict(),
            "stats": self.stats_dict(),
            "cpu": self.cpu_dict(),
        }

    def cpu_dict(self) -> dict[str, object]:
        """Rolling host CPU % from psutil (interval=None; sample on each overview request)."""
        try:
            import psutil
        except Exception:
            return {"percent": None, "history": []}

        try:
            pct_raw = psutil.cpu_percent(interval=None)
        except Exception:
            logger.debug("cpu_percent failed", exc_info=True)
            return {"percent": None, "history": []}

        pct = round(float(pct_raw), 1)
        with self._lock:
            self._cpu_samples.append(pct)
            history = list(self._cpu_samples)
        return {"percent": pct, "history": history}

    def record_job(self, result: dict[str, object]) -> None:
        event = dict(result)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        event.setdefault("updated_at", now_iso)
        if event.get("status") == PROCESSING:
            event.setdefault("received_at", now_iso)
        else:
            event.setdefault("finished_at", now_iso)
        job_store = self._job_store
        if job_store is not None:
            try:
                job_store.enqueue_job(event)
                return
            except Exception:
                logger.exception("Failed to persist job in SQLite; using memory fallback")
        with self._lock:
            job_id = str(event.get("job_id", "unknown"))
            prior = self._jobs_by_id.get(job_id)
            cur_status = str(prior["status"]) if prior and prior.get("status") is not None else None
            raw_sup = prior.get("replay_stats_suppress", 0) if prior else 0
            cur_suppress = _coerce_job_int(raw_sup)
            st = str(event.get("status", ""))
            fin_iso = _finished_at_iso_for_stats(event.get("finished_at"))
            raw_dur = event.get("duration_seconds", 0) or 0
            incoming_duration_seconds = _coerce_job_float(raw_dur)
            ok_d, err_d, dur_d, counted_fin, new_sup = replay_stats_transition(
                cur_status,
                cur_suppress,
                st,
                incoming_duration_seconds=incoming_duration_seconds,
                incoming_finished_at=fin_iso,
            )
            self.processed += ok_d
            self.failed += err_d
            self.total_duration += dur_d
            if counted_fin:
                self._memory_last_job_finished_at_iso = _max_iso_z(
                    self._memory_last_job_finished_at_iso,
                    counted_fin,
                )
            self._upsert_memory_job(event, replay_suppress=new_sup)

    def _upsert_memory_job(self, incoming: dict[str, object], *, replay_suppress: int) -> None:
        job_id = str(incoming.get("job_id", "unknown"))
        prior = self._jobs_by_id.get(job_id)
        if incoming.get("status") == PROCESSING:
            row = {**(prior or {}), **incoming}
            row.pop("finished_at", None)
        else:
            row = {**(prior or {}), **incoming}
        row["replay_stats_suppress"] = replay_suppress
        self._jobs_by_id[job_id] = row

    def jobs_dict(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, object]:
        job_store = self._job_store
        if job_store is not None:
            try:
                return job_store.jobs_dict(limit=limit, status=status, search=search)
            except Exception:
                logger.exception("Failed to query jobs from SQLite; falling back to memory")

        with self._lock:
            rows = list(self._jobs_by_id.values())
            rows.sort(
                key=lambda r: (
                    str(r.get("finished_at") or r.get("received_at") or ""),
                    str(r.get("job_id", "")),
                ),
                reverse=True,
            )

        if status in {OK, ERROR, PROCESSING}:
            rows = [row for row in rows if row.get("status") == status]

        if search:
            needle = search.casefold()
            rows = [
                row
                for row in rows
                if needle in str(row.get("job_id", "")).casefold()
                or needle in str(row.get("filename", "")).casefold()
                or needle in str(row.get("source_path", "")).casefold()
            ]

        bounded_limit = max(1, min(limit, 500))
        items: list[dict[str, object]] = []
        for row in rows[:bounded_limit]:
            item = dict(row)
            item["priority"] = max(0, min(255, _coerce_job_int(item.get("priority"))))
            items.append(item)
        return {
            "items": items,
            "count": len(items),
            "total": len(rows),
            "limit": bounded_limit,
        }


stats = WorkerStats()
_ARTIFACT_STORAGE: StorageBackend | None = None


@dataclass(frozen=True)
class UploadServerContext:
    """Storage + queue settings for POST ``/api/uploads``."""

    storage: StorageBackend
    settings: WorkerSettings


_UPLOAD_CONTEXT: UploadServerContext | None = None

SESSION_COOKIE_NAME = "docrunr_session"
_SESSIONS: dict[str, float] = {}
_SESSIONS_LOCK = threading.Lock()
_SESSION_TTL_SECONDS = 43200
_SESSION_COOKIE_SECURE = False

# When ``ui_password`` is set, these API surfaces require a valid session (not configurable).
_UI_AUTH_PROTECTED_GROUPS: frozenset[str] = frozenset({"jobs", "artifacts", "uploads"})


def set_artifact_storage(storage: StorageBackend | None) -> None:
    global _ARTIFACT_STORAGE
    _ARTIFACT_STORAGE = storage


def set_upload_context(context: UploadServerContext | None) -> None:
    global _UPLOAD_CONTEXT
    _UPLOAD_CONTEXT = context


def _resolve_ui_dist() -> Path | None:
    """Resolve bundled ui_dist (Docker) or ui/dist (local builds)."""
    here = Path(__file__).resolve().parent
    repo_root = here.parents[3] if len(here.parents) > 3 else here
    configured = os.environ.get("DOCRUNR_UI_DIST")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend((here / "ui_dist", repo_root / "ui" / "dist"))

    for path in candidates:
        try:
            resolved = path.resolve()
            if (resolved / "index.html").is_file():
                return resolved
        except OSError:
            continue
    return None


_UI_DIST: Path | None = _resolve_ui_dist()


class _Handler(BaseHTTPRequestHandler):
    @staticmethod
    def _http_settings() -> WorkerSettings:
        if _UPLOAD_CONTEXT is not None:
            return _UPLOAD_CONTEXT.settings
        from docrunr_worker.config import settings as global_settings

        return global_settings

    @staticmethod
    def _password_matches(expected: str, received: str) -> bool:
        digest = hashlib.sha256
        return hmac.compare_digest(
            digest(expected.encode("utf-8")).digest(),
            digest(received.encode("utf-8")).digest(),
        )

    @staticmethod
    def _parse_cookie_value(cookie_header: str | None, name: str) -> str | None:
        if not cookie_header:
            return None
        prefix = name + "="
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(prefix):
                return part[len(prefix) :].strip() or None
        return None

    @staticmethod
    def _session_expiry_unix() -> float:
        return time.time() + float(_SESSION_TTL_SECONDS)

    @staticmethod
    def _session_create() -> str:
        token = secrets.token_urlsafe(32)
        with _SESSIONS_LOCK:
            _SESSIONS[token] = _Handler._session_expiry_unix()
        return token

    @staticmethod
    def _session_valid(token: str | None) -> bool:
        if not token:
            return False
        now = time.time()
        with _SESSIONS_LOCK:
            exp = _SESSIONS.get(token)
            if exp is None:
                return False
            if now > exp:
                del _SESSIONS[token]
                return False
            return True

    @staticmethod
    def _session_revoke(token: str | None) -> None:
        if not token:
            return
        with _SESSIONS_LOCK:
            _SESSIONS.pop(token, None)

    @staticmethod
    def _request_session_token(handler: BaseHTTPRequestHandler) -> str | None:
        return _Handler._parse_cookie_value(handler.headers.get("Cookie"), SESSION_COOKIE_NAME)

    @staticmethod
    def _request_has_valid_session(handler: BaseHTTPRequestHandler, ws: WorkerSettings) -> bool:
        if not ws.ui_auth_enabled:
            return True
        return _Handler._session_valid(_Handler._request_session_token(handler))

    @staticmethod
    def _route_group_matches(method: str, path: str, group: str) -> bool:
        if group == "jobs":
            return path.startswith("/api/jobs")
        if group == "artifacts":
            return path.startswith("/api/artifact")
        if group == "uploads":
            return path == "/api/uploads" and method == "POST"
        return False

    @staticmethod
    def _path_requires_auth(ws: WorkerSettings, method: str, path: str) -> bool:
        if not ws.ui_auth_enabled:
            return False
        if path in {"/health", "/stats"} or path == "/api/overview":
            return False
        if path.startswith("/api/auth/"):
            return False
        if not path.startswith("/api/"):
            return False
        return any(
            _Handler._route_group_matches(method, path, g) for g in _UI_AUTH_PROTECTED_GROUPS
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        ws = self._http_settings()

        if path == "/api/auth/session":
            self._auth_session_json(ws)
            return

        if self._path_requires_auth(ws, "GET", path) and not self._request_has_valid_session(
            self, ws
        ):
            self._json_response_with_status({"error": "unauthorized"}, 401)
            return

        if path == "/health":
            self._json_response(stats.health_dict())
        elif path == "/stats":
            self._json_response(stats.stats_dict())
        elif path == "/api/overview":
            self._json_response(stats.overview_dict())
        elif path == "/api/jobs":
            params = parse_qs(parsed.query)
            try:
                parsed_limit = int(params.get("limit", ["100"])[0])
            except (TypeError, ValueError):
                limit = 100
            else:
                limit = parsed_limit if parsed_limit > 0 else 100
            status = params.get("status", [None])[0]
            search = params.get("search", [None])[0]
            self._json_response(
                stats.jobs_dict(
                    limit=limit,
                    status=status,
                    search=search.strip() if isinstance(search, str) else None,
                )
            )
        elif path == "/api/artifact":
            params = parse_qs(parsed.query)
            self._artifact_response(params.get("path", [None])[0])
        else:
            if not self._ui_response(path):
                self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        ws = self._http_settings()

        if path == "/api/auth/login":
            self._auth_login(ws)
            return
        if path == "/api/auth/logout":
            self._auth_logout()
            return

        if self._path_requires_auth(ws, "POST", path) and not self._request_has_valid_session(
            self, ws
        ):
            self._json_response_with_status({"error": "unauthorized"}, 401)
            return

        if path != "/api/uploads":
            self.send_error(404)
            return

        ctx = _UPLOAD_CONTEXT
        if ctx is None:
            self.send_error(503, "Upload unavailable")
            return

        try:
            raw_len = self.headers.get("Content-Length", "0")
            length = int(raw_len)
        except (TypeError, ValueError):
            self.send_error(400, "Invalid Content-Length")
            return

        if length <= 0:
            self._json_response_with_status({"error": "Request body required", "items": []}, 400)
            return

        try:
            body = self.rfile.read(length)
        except OSError:
            logger.exception("Failed to read upload body")
            self.send_error(400, "Read failed")
            return

        content_type = self.headers.get("Content-Type")
        params = parse_qs(parsed.query)
        try:
            priority = parse_upload_priority_query(params.get("priority", [None])[0])
        except InvalidJobPriorityError as exc:
            self._json_response_with_status({"error": str(exc), "items": []}, 400)
            return
        try:
            result = process_upload_request(
                body=body,
                content_type=content_type,
                storage=ctx.storage,
                settings=ctx.settings,
                priority=priority,
            )
        except UploadRequestError as exc:
            self._json_response_with_status({"error": str(exc), "items": []}, 400)
            return
        except Exception:
            logger.exception("Upload handling failed")
            self.send_error(500, "Upload failed")
            return

        self._json_response_with_status(result, 202)

    def _session_cookie_header(self, token: str) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            f"Max-Age={_SESSION_TTL_SECONDS}",
        ]
        if _SESSION_COOKIE_SECURE:
            parts.append("Secure")
        return "; ".join(parts)

    def _clear_session_cookie_header(self) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}=",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            "Max-Age=0",
        ]
        if _SESSION_COOKIE_SECURE:
            parts.append("Secure")
        return "; ".join(parts)

    def _auth_session_json(self, ws: WorkerSettings) -> None:
        enabled = ws.ui_auth_enabled
        authenticated = (not enabled) or self._request_has_valid_session(self, ws)
        self._json_response(
            {
                "auth_enabled": enabled,
                "authenticated": authenticated,
            }
        )

    def _auth_login(self, ws: WorkerSettings) -> None:
        if not ws.ui_auth_enabled:
            self._json_response_with_status({"error": "auth_disabled"}, 400)
            return
        try:
            raw_len = self.headers.get("Content-Length", "0")
            length = int(raw_len)
        except (TypeError, ValueError):
            self._json_response_with_status({"error": "invalid_content_length"}, 400)
            return
        if length <= 0 or length > 65536:
            self._json_response_with_status({"error": "invalid_body"}, 400)
            return
        try:
            raw = self.rfile.read(length)
            obj = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._json_response_with_status({"error": "invalid_json"}, 400)
            return
        if not isinstance(obj, dict):
            self._json_response_with_status({"error": "invalid_json"}, 400)
            return
        password = obj.get("password")
        if not isinstance(password, str):
            self._json_response_with_status({"error": "password_required"}, 400)
            return

        if not self._password_matches(ws.ui_password, password):
            self._json_response_with_status({"error": "invalid_password"}, 401)
            return

        prior = self._request_session_token(self)
        self._session_revoke(prior)
        token = self._session_create()
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", self._session_cookie_header(token))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_logout(self) -> None:
        self._session_revoke(self._request_session_token(self))
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", self._clear_session_cookie_header())
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_response(self, data: dict[str, object]) -> None:
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_response_with_status(self, data: dict[str, object], status: int) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _artifact_response(self, requested_path: str | None) -> None:
        if not isinstance(requested_path, str):
            self.send_error(400, "Missing path")
            return

        target_path = requested_path.strip()
        if not _is_allowed_output_path(target_path):
            self.send_error(400, "Invalid output path")
            return

        storage = _ARTIFACT_STORAGE
        if storage is None:
            self.send_error(503, "Artifact storage unavailable")
            return

        local_path: Path | None = None
        try:
            local_path = storage.read(target_path)
            if not local_path.is_file():
                self.send_error(404, "Artifact not found")
                return
            body = local_path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "Artifact not found")
            return
        except Exception:
            logger.exception("Failed to serve artifact path=%s", target_path)
            self.send_error(500, "Artifact read failed")
            return
        finally:
            if local_path is not None:
                try:
                    storage.cleanup(local_path)
                except Exception:
                    logger.debug("Artifact cleanup failed for %s", local_path, exc_info=True)

        self.send_response(200)
        self.send_header("Content-Type", _artifact_content_type(target_path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _ui_response(self, path: str) -> bool:
        global _UI_DIST
        if _UI_DIST is None or not (_UI_DIST / "index.html").is_file():
            _UI_DIST = _resolve_ui_dist()
        ui_dist = _UI_DIST
        if ui_dist is None:
            if path == "/":
                self.send_error(503, "UI assets not found")
                return True
            return False

        if path == "/":
            return self._static_file_response(ui_dist / "index.html")

        rel_path = Path(path.lstrip("/"))
        requested = (ui_dist / rel_path).resolve()
        try:
            requested.relative_to(ui_dist)
        except ValueError:
            return False

        if requested.is_file():
            return self._static_file_response(requested)

        # SPA fallback for non-file paths (e.g. /jobs).
        if rel_path.parts and rel_path.parts[0] in {"api", "assets", "health", "stats"}:
            return False
        if "." not in rel_path.name:
            return self._static_file_response(ui_dist / "index.html")

        return False

    def _static_file_response(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(500)
            return True

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
            "image/svg+xml",
        }:
            content_type = f"{content_type}; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def log_message(self, format: str, *args: object) -> None:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("health_http: " + format, *args)


def start_health_server(
    port: int,
    *,
    storage: StorageBackend | None = None,
    upload_context: UploadServerContext | None = None,
) -> threading.Thread:
    set_artifact_storage(storage)
    set_upload_context(upload_context)
    configure_rabbitmq_health_probe(upload_context.settings if upload_context is not None else None)
    try:
        import psutil

        # Prime cpu_percent so the first API sample is meaningful.
        psutil.cpu_percent(interval=0.05)
    except Exception:
        logger.debug("CPU sampler prime skipped", exc_info=True)
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="health")
    thread.start()
    logger.info("Health server listening on :%d", port)
    return thread


def _artifact_content_type(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "text/markdown; charset=utf-8"


def _is_allowed_output_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    if parsed.is_absolute():
        return False
    if not parsed.parts or parsed.parts[0] != "output":
        return False
    if any(part in {"", ".", ".."} for part in parsed.parts):
        return False
    return parsed.suffix.lower() in {".md", ".json"}
