"""Health/stats HTTP server for the LLM worker, including the bundled dashboard static assets."""

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
import re
from typing import TYPE_CHECKING, Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import parse_qs, urlparse

from docrunr_worker_llm.config import LlmWorkerSettings
from docrunr_worker_llm.job_status import ERROR, OK, PROCESSING, replay_stats_transition
from docrunr_worker_llm.rabbitmq_health import (
    configure_rabbitmq_health_probe,
    rabbitmq_reachable_for_api,
)

if TYPE_CHECKING:
    from docrunr_worker_llm.job_store import SQLiteJobStore
    from docrunr_worker_llm.storage import StorageBackend

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
class LlmWorkerStats:
    """LLM worker runtime counters with optional SQLite-backed persistence."""

    started_at: float = field(default_factory=time.time)
    processed: int = 0
    failed: int = 0
    total_duration: float = 0.0
    last_job_at: float | None = None
    rabbitmq_connected: bool = False
    _jobs_by_id: dict[str, dict[str, object]] = field(default_factory=dict, repr=False)
    _memory_last_job_finished_at_iso: str | None = field(default=None, repr=False)
    _cpu_samples: deque[float] = field(default_factory=lambda: deque(maxlen=64), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _job_store: SQLiteJobStore | None = field(default=None, repr=False)

    def attach_job_store(self, job_store: SQLiteJobStore) -> None:
        with self._lock:
            self._job_store = job_store

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
        try:
            import psutil
        except Exception:
            return {"percent": None, "history": []}

        try:
            pct_raw = psutil.cpu_percent(interval=None)
        except Exception:
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
            items.append(dict(row))
        return {
            "items": items,
            "count": len(items),
            "total": len(rows),
            "limit": bounded_limit,
        }


stats = LlmWorkerStats()
_ARTIFACT_STORAGE: StorageBackend | None = None

SESSION_COOKIE_NAME = "docrunr_llm_session"
_SESSIONS: dict[str, float] = {}
_SESSIONS_LOCK = threading.Lock()
_SESSION_TTL_SECONDS = 43200
_SESSION_COOKIE_SECURE = False

_UI_AUTH_PROTECTED_GROUPS: frozenset[str] = frozenset({"jobs", "artifacts"})


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


def set_artifact_storage(storage: StorageBackend | None) -> None:
    global _ARTIFACT_STORAGE
    _ARTIFACT_STORAGE = storage


_PROFILE_SIZE_TOKEN_RE = re.compile(r"^(\d+)([mb])$", re.IGNORECASE)
_PROFILE_TOKEN_LABELS: dict[str, str] = {
    "bge": "BGE",
    "embed": "Embed",
    "embedding": "Embedding",
    "gemma": "Gemma",
    "m3": "M3",
    "nomic": "Nomic",
    "qwen3": "Qwen3",
    "text": "Text",
}


def _humanize_llm_profile_name(profile: str) -> str:
    tokens = [token for token in profile.replace("_", "-").split("-") if token]
    if not tokens:
        return profile

    size_label = ""
    size_match = _PROFILE_SIZE_TOKEN_RE.fullmatch(tokens[-1])
    if size_match:
        size_label = f"{size_match.group(1)}{size_match.group(2).upper()}"
        tokens = tokens[:-1]

    words: list[str] = []
    for token in tokens:
        lowered = token.lower()
        words.append(_PROFILE_TOKEN_LABELS.get(lowered, token.capitalize()))

    base = " ".join(words) if words else profile
    return f"{base} ({size_label})" if size_label else base


def _label_for_litellm_profile_item(raw: dict[str, object], profile: str) -> str:
    for key in ("label", "display_name", "description"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    model_info = raw.get("model_info")
    if isinstance(model_info, dict):
        for key in ("label", "display_name", "description"):
            value = model_info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return _humanize_llm_profile_name(profile)


def _normalize_llm_profile_items(payload: object) -> list[dict[str, str]]:
    raw_items = payload
    if isinstance(payload, dict):
        raw_items = payload.get("data", [])
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_items:
        profile = ""
        label = ""
        if isinstance(raw, str):
            profile = raw.strip()
            label = _humanize_llm_profile_name(profile)
        elif isinstance(raw, dict):
            for key in ("model_name", "id", "model"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    profile = value.strip()
                    break
            if profile:
                label = _label_for_litellm_profile_item(raw, profile)
        if not profile or profile in seen:
            continue
        seen.add(profile)
        items.append({"value": profile, "label": label or profile})
    return items


def _fetch_litellm_profile_items(ws: LlmWorkerSettings) -> list[dict[str, str]]:
    base_url = ws.litellm_base_url.rstrip("/")
    url = f"{base_url}/models"
    headers = {"Accept": "application/json"}
    if ws.litellm_api_key.strip():
        headers["Authorization"] = f"Bearer {ws.litellm_api_key.strip()}"

    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=float(ws.litellm_timeout_seconds)) as response:
            body = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"LiteLLM model list request failed: {exc}") from exc

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("LiteLLM model list returned invalid JSON") from exc

    return _normalize_llm_profile_items(payload)


class _Handler(BaseHTTPRequestHandler):
    @staticmethod
    def _http_settings() -> LlmWorkerSettings:
        from docrunr_worker_llm.config import settings as global_settings

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
    def _request_has_valid_session(handler: BaseHTTPRequestHandler, ws: LlmWorkerSettings) -> bool:
        if not ws.ui_auth_enabled:
            return True
        return _Handler._session_valid(_Handler._request_session_token(handler))

    @staticmethod
    def _route_group_matches(method: str, path: str, group: str) -> bool:
        if group == "jobs":
            return path.startswith("/api/jobs")
        if group == "artifacts":
            return path.startswith("/api/artifact")
        return False

    @staticmethod
    def _path_requires_auth(ws: LlmWorkerSettings, method: str, path: str) -> bool:
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
        elif path == "/api/llm-profiles":
            try:
                self._json_response({"items": _fetch_litellm_profile_items(ws)})
            except RuntimeError:
                logger.exception("Failed to load LiteLLM profile list")
                self._json_response_with_status(
                    {"error": "Failed to load LLM profiles", "items": []},
                    502,
                )
        elif path == "/api/jobs":
            params = parse_qs(parsed.query)
            try:
                parsed_limit = int(params.get("limit", ["100"])[0])
            except (TypeError, ValueError):
                limit = 100
            else:
                limit = parsed_limit if parsed_limit > 0 else 100
            status_param = params.get("status", [None])[0]
            search = params.get("search", [None])[0]
            self._json_response(
                stats.jobs_dict(
                    limit=limit,
                    status=status_param,
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

        self.send_error(404)

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

    def _auth_session_json(self, ws: LlmWorkerSettings) -> None:
        enabled = ws.ui_auth_enabled
        authenticated = (not enabled) or self._request_has_valid_session(self, ws)
        self._json_response({"auth_enabled": enabled, "authenticated": authenticated})

    def _auth_login(self, ws: LlmWorkerSettings) -> None:
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

    def _json_response_with_status(self, data: dict[str, object], status_code: int) -> None:
        body = json.dumps(data).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _artifact_response(self, requested_path: str | None) -> None:
        if not isinstance(requested_path, str):
            self.send_error(400, "Missing path")
            return

        target_path = requested_path.strip()
        parsed_path = PurePosixPath(target_path)
        path_ok = (
            not parsed_path.is_absolute()
            and bool(parsed_path.parts)
            and parsed_path.parts[0] == "output"
            and not any(part in {"", ".", ".."} for part in parsed_path.parts)
            and parsed_path.suffix.lower() == ".json"
        )
        if not path_ok:
            self.send_error(400, "Invalid output path")
            return

        storage = _ARTIFACT_STORAGE
        if storage is None:
            self.send_error(503, "Artifact storage unavailable")
            return

        local_path = None
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
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
) -> threading.Thread:
    set_artifact_storage(storage)
    settings = LlmWorkerSettings()
    configure_rabbitmq_health_probe(settings)
    try:
        import psutil

        psutil.cpu_percent(interval=0.05)
    except Exception:
        logger.debug("CPU sampler prime skipped", exc_info=True)
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="llm-health")
    thread.start()
    logger.info("LLM worker health server listening on :%d", port)
    return thread
