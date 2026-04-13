"""Terminal + JSON summary after integration e2e runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def emit_integration_report(
    data_root: Path,
    staged: list[tuple[str, str, Path]],
    results: dict[str, dict[str, Any]],
) -> None:
    """Print a short table to stdout and write ``integration-report.json`` under ``data_root``."""
    rows: list[dict[str, Any]] = []
    ok = 0
    for idx, (job_id, rel, sample) in enumerate(staged, start=1):
        row = results[job_id]
        status = str(row.get("status", "?"))
        if status == "ok":
            ok += 1
        rows.append(
            {
                "index": idx,
                "job_id": job_id,
                "sample_path": str(sample),
                "filename": sample.name,
                "source_path": rel,
                "status": status,
                "markdown_path": row.get("markdown_path"),
                "chunks_path": row.get("chunks_path"),
                "chunk_count": row.get("chunk_count"),
                "total_tokens": row.get("total_tokens"),
                "duration_seconds": row.get("duration_seconds"),
                "error": row.get("error"),
            }
        )

    summary: dict[str, Any] = {
        "jobs_total": len(staged),
        "jobs_ok": ok,
        "jobs_failed": len(staged) - ok,
        "all_ok": ok == len(staged),
    }

    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_root": str(data_root.resolve()),
        "summary": summary,
        "notes": [
            "Status/chunks/tokens/duration are from each RabbitMQ result message (authoritative).",
            "Container logs may show ERROR from a parser that failed before another parser "
            "succeeded for the same file.",
        ],
        "jobs": rows,
    }

    report_path = data_root / "integration-report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _print_table(summary, staged, results)
    print(f"\nIntegration report written: {report_path.resolve()}")


def _print_table(
    summary: dict[str, Any],
    staged: list[tuple[str, str, Path]],
    results: dict[str, dict[str, Any]],
) -> None:
    n = summary["jobs_total"]
    ok_n = summary["jobs_ok"]
    line = "=" * 72
    print(f"\n{line}")
    tail = " ✓" if summary["all_ok"] else " ✗"
    print(f"DocRunr integration — {ok_n}/{n} jobs OK{tail}")
    print(line)
    header = f"{'#':>3}  {'filename':<36}  {'status':<6}  {'chunks':>6}  {'tokens':>7}  {'sec':>5}"
    print(header)
    print("-" * len(header))
    for idx, (job_id, _rel, sample) in enumerate(staged, start=1):
        row = results[job_id]
        status = str(row.get("status", "?"))
        name = sample.name
        if len(name) > 36:
            name = name[:33] + "..."
        chunks = row.get("chunk_count", "")
        tokens = row.get("total_tokens", "")
        dur = row.get("duration_seconds", "")
        print(f"{idx:>3}  {name:<36}  {status:<6}  {chunks!s:>6}  {tokens!s:>7}  {dur!s:>5}")
    print(line)
