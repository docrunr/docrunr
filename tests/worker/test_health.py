"""Tests for health stats tracking."""

from __future__ import annotations

from docrunr_worker.health import WorkerStats, _artifact_content_type, _is_allowed_output_path
from docrunr_worker.job_status import PROCESSING


class TestWorkerStats:
    def test_initial_state(self) -> None:
        s = WorkerStats()
        assert s.processed == 0
        assert s.failed == 0
        assert s.avg_duration == 0.0
        assert s.last_job_at is None

    def test_record_job_counts_successes_for_memory_stats(self) -> None:
        s = WorkerStats()
        s.record_job(
            {
                "job_id": "a",
                "status": "ok",
                "duration_seconds": 2.0,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/a.pdf",
                "finished_at": "2026-04-02T10:00:00Z",
            }
        )
        s.record_job(
            {
                "job_id": "b",
                "status": "ok",
                "duration_seconds": 4.0,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/b.pdf",
                "finished_at": "2026-04-02T10:00:01Z",
            }
        )
        assert s.processed == 2
        assert s.avg_duration == 3.0
        assert s.stats_dict()["last_job_at"] == "2026-04-02T10:00:01Z"

    def test_record_job_counts_failures_for_memory_stats(self) -> None:
        s = WorkerStats()
        s.record_job(
            {
                "job_id": "x",
                "status": "error",
                "duration_seconds": 0.0,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/x.pdf",
                "finished_at": "2026-04-02T12:00:00Z",
                "error": "boom",
            }
        )
        assert s.failed == 1
        assert s.stats_dict()["last_job_at"] == "2026-04-02T12:00:00Z"

    def test_health_dict(self) -> None:
        s = WorkerStats()
        h = s.health_dict()
        assert h["status"] == "ok"
        assert h["rabbitmq"] == "disconnected"
        assert isinstance(h["uptime_seconds"], int)

    def test_stats_dict(self) -> None:
        s = WorkerStats()
        s.record_job(
            {
                "job_id": "solo",
                "status": "ok",
                "duration_seconds": 1.5,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/solo.pdf",
                "finished_at": "2026-04-02T09:00:00Z",
            }
        )
        d = s.stats_dict()
        assert d["processed"] == 1
        assert d["failed"] == 0
        assert d["avg_duration_seconds"] == 1.5
        assert d["last_job_at"] == "2026-04-02T09:00:00Z"
        assert d["recent_jobs_count"] == 1

    def test_rabbitmq_connected(self) -> None:
        s = WorkerStats()
        s.rabbitmq_connected = True
        assert s.health_dict()["rabbitmq"] == "connected"

    def test_overview_dict(self) -> None:
        s = WorkerStats()
        overview = s.overview_dict()
        assert overview["health"]
        assert overview["stats"]
        cpu = overview["cpu"]
        assert isinstance(cpu, dict)
        assert "percent" in cpu
        assert "history" in cpu
        assert isinstance(cpu["history"], list)

    def test_record_job_and_jobs_dict(self) -> None:
        s = WorkerStats()
        s.record_job(
            {
                "job_id": "job-1",
                "filename": "report.pdf",
                "source_path": "input/2026/04/11/14/job-1.pdf",
                "status": "ok",
            }
        )
        s.record_job(
            {
                "job_id": "job-2",
                "filename": "invoice.pdf",
                "source_path": "input/2026/04/11/14/job-2.pdf",
                "status": "error",
            }
        )

        all_jobs = s.jobs_dict()
        assert all_jobs["count"] == 2
        assert all_jobs["total"] == 2
        assert isinstance(all_jobs["items"], list)
        first = all_jobs["items"][0]
        assert isinstance(first, dict)
        assert first["job_id"] == "job-2"
        assert first["finished_at"]

        errored = s.jobs_dict(status="error")
        assert errored["count"] == 1
        assert errored["items"][0]["job_id"] == "job-2"

        searched = s.jobs_dict(search="report")
        assert searched["count"] == 1
        assert searched["items"][0]["job_id"] == "job-1"

    def test_jobs_dict_filters_processing_in_memory(self) -> None:
        s = WorkerStats()
        s.record_job(
            {
                "job_id": "p1",
                "filename": "a.pdf",
                "source_path": "input/2026/04/11/14/a.pdf",
                "status": PROCESSING,
            }
        )
        s.record_job(
            {
                "job_id": "done",
                "filename": "b.pdf",
                "source_path": "input/2026/04/11/14/b.pdf",
                "status": "ok",
            }
        )
        only = s.jobs_dict(status=PROCESSING)
        assert only["total"] == 1
        assert only["items"][0]["job_id"] == "p1"

    def test_memory_replay_after_ok_does_not_recount_terminal(self) -> None:
        s = WorkerStats()
        s.record_job(
            {
                "job_id": "j",
                "status": "ok",
                "duration_seconds": 1.0,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/j.pdf",
                "finished_at": "2026-04-02T10:00:00Z",
            }
        )
        s.record_job(
            {
                "job_id": "j",
                "status": PROCESSING,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/j.pdf",
            }
        )
        s.record_job(
            {
                "job_id": "j",
                "status": "error",
                "duration_seconds": 0.5,
                "filename": "f.pdf",
                "source_path": "input/2026/04/11/14/j.pdf",
                "finished_at": "2026-04-02T11:00:00Z",
                "error": "replay",
            }
        )
        d = s.stats_dict()
        assert d["processed"] == 1
        assert d["failed"] == 0
        assert d["recent_jobs_count"] == 1


def test_allowed_output_paths() -> None:
    assert _is_allowed_output_path("output/2026/04/11/14/job-1.md")
    assert _is_allowed_output_path("output/2026/04/11/14/job-1.json")
    assert not _is_allowed_output_path("/output/2026/04/11/14/job-1.md")
    assert not _is_allowed_output_path("input/2026/04/11/14/job-1.md")
    assert not _is_allowed_output_path("output/../../etc/passwd")
    assert not _is_allowed_output_path("output/2026/04/11/14/job-1.txt")


def test_artifact_content_type() -> None:
    assert _artifact_content_type("output/2026/04/11/14/job-1.md") == "text/markdown; charset=utf-8"
    assert (
        _artifact_content_type("output/2026/04/11/14/job-1.json")
        == "application/json; charset=utf-8"
    )
