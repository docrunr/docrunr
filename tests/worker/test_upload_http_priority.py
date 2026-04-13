"""HTTP-layer tests for ``POST /api/uploads`` priority query handling."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread
from unittest.mock import patch

import pytest
from docrunr_worker.config import WorkerSettings
from docrunr_worker.health import UploadServerContext, _Handler, set_upload_context
from docrunr_worker.storage import LocalStorage


def _multipart_body(*, boundary: str, filename: str, content: bytes) -> tuple[bytes, str]:
    b = boundary.encode("ascii")
    body = b"".join(
        [
            b"--" + b + b"\r\n",
            f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content,
            b"\r\n--" + b + b"--\r\n",
        ]
    )
    ct = f'multipart/form-data; boundary="{boundary}"'
    return body, ct


@pytest.fixture
def upload_http_server(tmp_path):
    storage = LocalStorage(str(tmp_path))
    settings = WorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        rabbitmq_queue="docrunr.jobs",
    )
    set_upload_context(UploadServerContext(storage=storage, settings=settings))
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        set_upload_context(None)


def test_post_upload_invalid_priority_returns_400(upload_http_server: int) -> None:
    conn = HTTPConnection("127.0.0.1", upload_http_server)
    conn.request(
        "POST",
        "/api/uploads?priority=not-an-int",
        body=b"x",
        headers={"Content-Type": "text/plain", "Content-Length": "1"},
    )
    resp = conn.getresponse()
    assert resp.status == 400
    data = json.loads(resp.read().decode())
    assert data["items"] == []
    assert "priority" in data.get("error", "").lower()


def test_post_upload_priority_passed_to_publish(upload_http_server: int) -> None:
    body, ct = _multipart_body(
        boundary="bprio",
        filename="z.pdf",
        content=b"%PDF-1.4",
    )
    captured: list[dict] = []

    def _capture(**kwargs: object) -> None:
        captured.append(dict(kwargs))

    with patch("docrunr_worker.uploads.publish_durable_bytes", side_effect=_capture):
        conn = HTTPConnection("127.0.0.1", upload_http_server)
        conn.request(
            "POST",
            "/api/uploads?priority=88",
            body=body,
            headers={"Content-Type": ct, "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        assert resp.status == 202
        payload = json.loads(resp.read().decode())

    assert len(captured) == 1
    assert captured[0]["priority"] == 88
    msg = json.loads(captured[0]["body"].decode())
    assert msg["priority"] == 88
    assert payload["items"][0]["priority"] == 88
