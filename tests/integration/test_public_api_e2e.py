"""End-to-end upload and polling through the dedicated public API."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def _base_url() -> str:
    return os.environ.get("DOCRUNR_API_URL", "http://127.0.0.1:8082").rstrip("/")


def _request(path: str, *, data: bytes | None = None, headers: dict[str, str] | None = None):
    request_headers = dict(headers or {})
    if token := os.environ.get("API_KEY"):
        request_headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{_base_url()}{path}",
        data=data,
        headers=request_headers,
        method="POST" if data is not None else "GET",
    )
    return urllib.request.urlopen(request, timeout=30)


def _multipart(
    boundary: str,
    *,
    filename: str,
    content: bytes,
    llm_profile: str | None = None,
) -> bytes:
    parts: list[bytes] = []
    if llm_profile:
        parts.append(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="llm_profile"\r\n\r\n'
                f"{llm_profile}\r\n"
            ).encode()
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode()
        + content
        + b"\r\n"
    )
    return b"".join(parts) + f"--{boundary}--\r\n".encode()


def _wait_for_job(job_id: str, *, llm: bool = False) -> dict[str, object]:
    deadline = time.monotonic() + 600
    job: dict[str, object] = {}
    while time.monotonic() < deadline:
        with _request(f"/api/v1/jobs/{job_id}") as response:
            job = json.loads(response.read())["data"]
        state = (job.get("llm_transform") or {}).get("state") if llm else job.get("state")
        if state in {"succeeded", "failed"}:
            return job
        time.sleep(1)
    return job


def test_public_api_upload_to_markdown() -> None:
    try:
        with _request("/health") as response:
            if response.status != 200:
                pytest.skip("DocRunr API is not ready")
    except (urllib.error.URLError, TimeoutError):
        pytest.skip("DocRunr API is not running")

    boundary = "----docrunrPublicApiE2E"
    document = b"DocRunr public API integration test."
    body = _multipart(boundary, filename="api-test.txt", content=document)
    with _request(
        "/api/v1/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    ) as response:
        assert response.status == 201
        job_id = json.loads(response.read())["data"]["job_id"]

    assert _wait_for_job(job_id)["state"] == "succeeded"

    with _request(f"/api/v1/jobs/{job_id}/result?format=markdown") as response:
        assert response.status == 200
        assert b"DocRunr public API integration test" in response.read()


@pytest.mark.llm_jobs
def test_public_api_upload_to_embeddings() -> None:
    try:
        with _request("/api/v1/llm/profiles") as response:
            profiles = json.loads(response.read())["data"]["profiles"]
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            pytest.skip("LiteLLM is unavailable")
        raise
    except urllib.error.URLError:
        pytest.skip("DocRunr API is not running")
    if not profiles:
        pytest.skip("LiteLLM exposes no embedding profiles")

    profile = str(profiles[0])
    boundary = "----docrunrPublicApiLlmE2E"
    body = _multipart(
        boundary,
        filename="api-llm-test.txt",
        content=b"Embedding integration test.",
        llm_profile=profile,
    )
    with _request(
        "/api/v1/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    ) as response:
        job_id = json.loads(response.read())["data"]["job_id"]

    job = _wait_for_job(job_id, llm=True)
    llm_transform = job["llm_transform"]
    assert isinstance(llm_transform, dict)
    assert llm_transform["state"] == "succeeded"
    with _request(f"/api/v1/jobs/{job_id}/result?format=embeddings") as response:
        assert response.status == 200
        assert json.loads(response.read())["data"]["job_id"] == job_id
