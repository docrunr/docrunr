from __future__ import annotations

from docrunr_api.repository import JobRepository


def test_outbox_and_result_projection_are_restart_safe(tmp_path) -> None:
    path = tmp_path / "api.sqlite"
    repository = JobRepository(str(path))
    repository.initialize()
    repository.create_job(
        job_id="job-1",
        file_name="a.txt",
        file_size=1,
        content_type="text/plain",
        source_path="input/job-1.txt",
        priority=0,
        llm_profile="embed-local",
        body=b'{"job_id":"job-1"}',
    )

    restarted = JobRepository(str(path))
    restarted.initialize()
    outbox = restarted.pending_outbox()
    assert len(outbox) == 1
    restarted.mark_published(int(outbox[0]["id"]))
    assert restarted.is_published("job-1")

    terminal = {
        "job_id": "job-1",
        "status": "ok",
        "chunks_path": "output/job-1.json",
        "markdown_path": "output/job-1.md",
        "chunk_count": 1,
    }
    restarted.apply_extraction_result(terminal)
    restarted.apply_extraction_result(terminal)
    restarted.apply_llm_result(
        {
            "extract_job_id": "job-1",
            "status": "ok",
            "artifact_path": "output/job-1.embeddings.json",
            "vector_count": 1,
        }
    )
    job = restarted.get_job("job-1")
    assert job is not None
    assert job["state"] == "succeeded"
    assert job["llm_state"] == "succeeded"
