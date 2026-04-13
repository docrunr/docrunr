"""HTTP auth for protected worker API routes (session cookie, optional password)."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

import pytest
from docrunr_worker.config import WorkerSettings
from docrunr_worker.health import (
    _SESSIONS,
    SESSION_COOKIE_NAME,
    UploadServerContext,
    _Handler,
    set_artifact_storage,
    set_upload_context,
)
from docrunr_worker.storage import LocalStorage


def _parse_set_cookie_session(set_cookie: str | None) -> str | None:
    if not set_cookie:
        return None
    for part in set_cookie.split(","):
        part = part.strip()
        prefix = SESSION_COOKIE_NAME + "="
        if part.startswith(prefix):
            return part[len(prefix) :].split(";", 1)[0].strip()
    return None


@pytest.fixture
def auth_http_server(tmp_path):
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_queue="docrunr.jobs",
        ui_password="secret-ui",
    )
    _SESSIONS.clear()
    set_upload_context(UploadServerContext(storage=storage, settings=settings))
    set_artifact_storage(storage)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, settings
    finally:
        server.shutdown()
        _SESSIONS.clear()
        set_upload_context(None)
        set_artifact_storage(None)


def test_public_endpoints_ok_without_session(auth_http_server: tuple[int, WorkerSettings]) -> None:
    port, _settings = auth_http_server
    for path in ("/health", "/stats", "/api/overview"):
        conn = HTTPConnection("127.0.0.1", port)
        conn.request("GET", path)
        resp = conn.getresponse()
        assert resp.status == 200, path
        resp.read()


def test_auth_session_enabled_without_login(
    auth_http_server: tuple[int, WorkerSettings],
) -> None:
    port, _settings = auth_http_server
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/api/auth/session")
    resp = conn.getresponse()
    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data == {"auth_enabled": True, "authenticated": False}


def test_protected_jobs_401_without_cookie(auth_http_server: tuple[int, WorkerSettings]) -> None:
    port, _settings = auth_http_server
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/api/jobs")
    resp = conn.getresponse()
    assert resp.status == 401
    assert json.loads(resp.read().decode()) == {"error": "unauthorized"}


def test_login_failure_401(auth_http_server: tuple[int, WorkerSettings]) -> None:
    port, _settings = auth_http_server
    body = json.dumps({"password": "wrong"}).encode()
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/api/auth/login",
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    resp = conn.getresponse()
    assert resp.status == 401
    payload = json.loads(resp.read().decode())
    assert payload.get("error") == "invalid_password"


def test_login_success_then_jobs_200(auth_http_server: tuple[int, WorkerSettings]) -> None:
    port, _settings = auth_http_server
    body = json.dumps({"password": "secret-ui"}).encode()
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/api/auth/login",
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    resp = conn.getresponse()
    assert resp.status == 200
    login_payload = json.loads(resp.read().decode())
    assert login_payload == {"ok": True}
    cookie_header = resp.getheader("Set-Cookie")
    token = _parse_set_cookie_session(cookie_header)
    assert token

    conn2 = HTTPConnection("127.0.0.1", port)
    conn2.request("GET", "/api/jobs", headers={"Cookie": f"{SESSION_COOKIE_NAME}={token}"})
    resp2 = conn2.getresponse()
    assert resp2.status == 200
    jobs = json.loads(resp2.read().decode())
    assert "items" in jobs


def test_logout_clears_session(auth_http_server: tuple[int, WorkerSettings]) -> None:
    port, _settings = auth_http_server
    body = json.dumps({"password": "secret-ui"}).encode()
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        "/api/auth/login",
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    resp = conn.getresponse()
    assert resp.status == 200
    resp.read()
    cookie_header = resp.getheader("Set-Cookie")
    token = _parse_set_cookie_session(cookie_header)
    assert token

    conn2 = HTTPConnection("127.0.0.1", port)
    conn2.request(
        "POST",
        "/api/auth/logout",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={token}", "Content-Length": "0"},
    )
    resp2 = conn2.getresponse()
    assert resp2.status == 200
    resp2.read()

    conn3 = HTTPConnection("127.0.0.1", port)
    conn3.request("GET", "/api/jobs", headers={"Cookie": f"{SESSION_COOKIE_NAME}={token}"})
    resp3 = conn3.getresponse()
    assert resp3.status == 401


def test_password_disabled_jobs_public(tmp_path) -> None:
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_queue="docrunr.jobs",
        ui_password="",
    )
    _SESSIONS.clear()
    set_upload_context(UploadServerContext(storage=storage, settings=settings))
    set_artifact_storage(storage)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/api/jobs")
        resp = conn.getresponse()
        assert resp.status == 200
        resp.read()
    finally:
        server.shutdown()
        _SESSIONS.clear()
        set_upload_context(None)
        set_artifact_storage(None)
