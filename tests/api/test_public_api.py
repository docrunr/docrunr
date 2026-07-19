from __future__ import annotations

import json
from pathlib import Path

from docrunr_api.app import create_app
from docrunr_api.config import ApiSettings
from docrunr_api.repository import JobRepository
from docrunr_runtime.storage import LocalStorage
from fastapi.testclient import TestClient


class FakeBroker:
    ready = True

    def __init__(self, repository: JobRepository) -> None:
        self.repository = repository

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def wait_published(self, job_id: str, *, timeout: float = 10.0) -> bool:
        del timeout
        for item in self.repository.pending_outbox():
            if item["job_id"] == job_id:
                self.repository.mark_published(int(item["id"]))
                return True
        return False


class FakeProfiles:
    async def list_profiles(self) -> list[str]:
        return ["embed-local"]


def make_client(tmp_path: Path, *, api_key: str = "") -> tuple[TestClient, JobRepository]:
    settings = ApiSettings(
        api_host="127.0.0.1",
        api_key=api_key,
        api_db_path=str(tmp_path / "api.sqlite"),
        storage_base_path=str(tmp_path / "storage"),
        litellm_base_url="http://litellm.test",
    )
    repository = JobRepository(settings.api_db_path)
    app = create_app(
        settings,
        repository=repository,
        broker=FakeBroker(repository),  # type: ignore[arg-type]
        storage=LocalStorage(settings.storage_base_path),
        profiles=FakeProfiles(),  # type: ignore[arg-type]
    )
    return TestClient(app), repository


def test_swagger_is_served_at_root(tmp_path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        assert client.get("/").status_code == 200
        spec = client.get("/openapi.json").json()
    assert "/api/v1/documents" in spec["paths"]
    assert spec["paths"]["/api/v1/documents"]["post"]["operationId"] == (
        "PublicApiController_submitDocument"
    )


def test_openapi_snapshot_is_current() -> None:
    expected = json.loads((Path(__file__).parents[2] / "api" / "openapi.json").read_text())
    assert create_app().openapi() == expected


def test_bearer_auth_uses_error_envelope(tmp_path) -> None:
    client, _ = make_client(tmp_path, api_key="secret")
    with client:
        response = client.get("/api/v1/jobs")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
        accepted = client.get("/api/v1/jobs", headers={"Authorization": "Bearer secret"})
        assert accepted.status_code == 200


def test_upload_and_job_projection(tmp_path) -> None:
    client, repository = make_client(tmp_path)
    with client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 201
        job_id = response.json()["data"]["job_id"]

        queued = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        assert queued["state"] == "queued"

        repository.apply_lifecycle({"job_id": job_id, "state": "processing"})
        repository.apply_extraction_result(
            {
                "job_id": job_id,
                "status": "ok",
                "markdown_path": f"output/{job_id}.md",
                "chunks_path": f"output/{job_id}.json",
                "total_tokens": 2,
                "total_chars": 5,
                "chunk_count": 1,
                "error": None,
            }
        )
        completed = client.get(f"/api/v1/jobs/{job_id}").json()["data"]
        assert completed["state"] == "succeeded"
        assert completed["result"]["available"] is True


def test_result_formats_and_not_ready_error(tmp_path) -> None:
    client, repository = make_client(tmp_path)
    storage = LocalStorage(str(tmp_path / "storage"))
    repository.initialize()
    repository.create_job(
        job_id="job-1",
        file_name="a.txt",
        file_size=1,
        content_type="text/plain",
        source_path="input/job-1.txt",
        priority=0,
        llm_profile=None,
        body=b"{}",
    )
    with client:
        pending = client.get("/api/v1/jobs/job-1/result")
        assert pending.status_code == 409
        assert pending.json()["error"]["code"] == "JOB_NOT_READY"

        markdown_source = tmp_path / "markdown"
        markdown_source.write_text("# Result")
        chunks_source = tmp_path / "chunks"
        chunks_source.write_text(json.dumps({"chunks": [{"text": "Result"}]}))
        storage.write(markdown_source, "output/job-1.md")
        storage.write(chunks_source, "output/job-1.json")
        repository.apply_extraction_result(
            {
                "job_id": "job-1",
                "status": "ok",
                "markdown_path": "output/job-1.md",
                "chunks_path": "output/job-1.json",
            }
        )

        markdown = client.get("/api/v1/jobs/job-1/result?format=markdown")
        assert markdown.status_code == 200
        assert markdown.text == "# Result"
        chunks = client.get("/api/v1/jobs/job-1/result?format=json")
        assert chunks.json()["data"]["result"]["chunks"][0]["text"] == "Result"


def test_list_pagination_and_validation(tmp_path) -> None:
    client, repository = make_client(tmp_path)
    repository.initialize()
    for index in range(3):
        repository.create_job(
            job_id=f"job-{index}",
            file_name=f"{index}.txt",
            file_size=1,
            content_type="text/plain",
            source_path=f"input/job-{index}.txt",
            priority=0,
            llm_profile=None,
            body=b"{}",
        )
    with client:
        page = client.get("/api/v1/jobs?limit=2").json()["data"]
        assert len(page["items"]) == 2
        assert page["has_more"] is True
        invalid = client.get("/api/v1/jobs?limit=0")
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
