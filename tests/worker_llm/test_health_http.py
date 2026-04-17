"""HTTP checks for the LLM worker API."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

import pytest
from docrunr_worker_llm import health as health_mod
from docrunr_worker_llm.config import LlmWorkerSettings
from docrunr_worker_llm.health import _Handler


@pytest.fixture
def llm_http_server(monkeypatch: pytest.MonkeyPatch):
    settings = LlmWorkerSettings(
        rabbitmq_host="127.0.0.1",
        rabbitmq_port=5672,
        ui_password="secret-ui",
    )
    monkeypatch.setattr(_Handler, "_http_settings", staticmethod(lambda: settings))
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()


def test_llm_profiles_endpoint_is_public_and_returns_items(
    llm_http_server: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_mod,
        "_fetch_litellm_profile_items",
        lambda _ws: [
            {"value": "nomic-embed-text-137m", "label": "Nomic Embed Text (137M)"},
            {"value": "embedding-gemma-300m", "label": "Embedding Gemma (300M)"},
        ],
    )

    conn = HTTPConnection("127.0.0.1", llm_http_server)
    conn.request("GET", "/api/llm-profiles")
    resp = conn.getresponse()

    assert resp.status == 200
    data = json.loads(resp.read().decode())
    assert data == {
        "items": [
            {"value": "nomic-embed-text-137m", "label": "Nomic Embed Text (137M)"},
            {"value": "embedding-gemma-300m", "label": "Embedding Gemma (300M)"},
        ]
    }


def test_llm_profiles_endpoint_returns_502_on_fetch_failure(
    llm_http_server: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_ws: LlmWorkerSettings) -> list[dict[str, str]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(health_mod, "_fetch_litellm_profile_items", _raise)

    conn = HTTPConnection("127.0.0.1", llm_http_server)
    conn.request("GET", "/api/llm-profiles")
    resp = conn.getresponse()

    assert resp.status == 502
    data = json.loads(resp.read().decode())
    assert data == {"error": "Failed to load LLM profiles", "items": []}


def test_normalize_llm_profile_items_humanizes_labels() -> None:
    items = health_mod._normalize_llm_profile_items(
        {
            "data": [
                {"model_name": "nomic-embed-text-137m"},
                {"model_name": "embedding-gemma-300m"},
                {"model_name": "bge-m3-560m"},
                {"model_name": "qwen3-embedding-8b"},
            ]
        }
    )

    assert items == [
        {"value": "nomic-embed-text-137m", "label": "Nomic Embed Text (137M)"},
        {"value": "embedding-gemma-300m", "label": "Embedding Gemma (300M)"},
        {"value": "bge-m3-560m", "label": "BGE M3 (560M)"},
        {"value": "qwen3-embedding-8b", "label": "Qwen3 Embedding (8B)"},
    ]
