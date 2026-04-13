from __future__ import annotations

import random
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import TypeAlias

from tests.downloads.console import log, progress
from tests.downloads.discovery import collect_candidates
from tests.downloads.formatting import download_progress, gathering_progress, human_size
from tests.downloads.mime_utils import (
    build_target,
    extension_from_content_type,
    extension_from_url,
    mime_folder_name,
    normalize_content_type,
    parse_csv,
    should_keep_download,
)
from tests.downloads.models import OUT_ROOT, USER_AGENT, Candidate, PlannedDownload, Target
from tests.downloads.naming import readable_filename

DownloadSuccess: TypeAlias = tuple[Path, int, str, str]
DownloadAttempt: TypeAlias = tuple[DownloadSuccess | None, str | None]
ProbeAttempt: TypeAlias = tuple[PlannedDownload | None, str | None]
_MAX_FAILURE_DETAILS_PER_TYPE = 12


def parse_content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _error_message(exc: Exception, *, prefix: str) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{prefix}: {exc.__class__.__name__}: {detail}"
    return f"{prefix}: {exc.__class__.__name__}"


def _record_failure(
    bucket: dict[str, list[str]],
    requested_type: str,
    message: str,
) -> None:
    entries = bucket[requested_type]
    if len(entries) >= _MAX_FAILURE_DETAILS_PER_TYPE:
        return
    entries.append(message)


def probe_candidate(candidate: Candidate, timeout: int) -> ProbeAttempt:
    request = urllib.request.Request(
        candidate.url,
        headers={"User-Agent": USER_AGENT},
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                PlannedDownload(
                    candidate=candidate,
                    final_url=response.geturl() or candidate.url,
                    content_type=(
                        normalize_content_type(response.headers.get("content-type"))
                        or candidate.mime_hint
                    ),
                    content_length=parse_content_length(response.headers.get("content-length")),
                ),
                None,
            )
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 404, 405, 406, 501}:
            return (
                PlannedDownload(
                    candidate=candidate,
                    final_url=candidate.url,
                    content_type=candidate.mime_hint,
                    content_length=None,
                ),
                None,
            )
        return None, f"HEAD HTTPError {exc.code}: {exc.reason or 'request failed'}"
    except Exception as exc:  # noqa: BLE001
        return None, _error_message(exc, prefix="HEAD request failed")


def download_one(
    planned: PlannedDownload,
    target: Target,
    timeout: int,
) -> DownloadAttempt:
    request = urllib.request.Request(planned.final_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            final_url = response.geturl() or planned.final_url
            content_type = response.headers.get("content-type")
    except urllib.error.HTTPError as exc:
        return None, f"GET HTTPError {exc.code}: {exc.reason or 'request failed'}"
    except Exception as exc:  # noqa: BLE001
        return None, _error_message(exc, prefix="GET request failed")

    if not should_keep_download(content_type=content_type, final_url=final_url, target=target):
        return None, "Downloaded content did not match requested mimetype or extension"

    normalized_type = normalize_content_type(content_type) or planned.content_type
    extension = (
        extension_from_content_type(normalized_type) or extension_from_url(final_url) or "bin"
    )

    folder = OUT_ROOT / mime_folder_name(normalized_type, final_url)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return None, _error_message(exc, prefix="Failed to create output directory")

    destination = readable_filename(planned.candidate.source, final_url, extension, folder)
    try:
        destination.write_bytes(content)
    except Exception as exc:  # noqa: BLE001
        return None, _error_message(exc, prefix="Failed to write downloaded file")

    display_type = normalized_type or extension
    return (destination, len(content), final_url, display_type), None


def run_downloads(mimetype: str, count: int, timeout: int, seed: int | None) -> int:
    if count <= 0:
        log("[error] count must be > 0")
        return 1
    if timeout <= 0:
        log("[error] timeout must be > 0")
        return 1

    raw_types = parse_csv(mimetype)
    requested_types: list[str] = []
    seen_types: set[str] = set()
    for raw in raw_types:
        normalized = raw.strip().lower()
        if normalized and normalized not in seen_types:
            requested_types.append(normalized)
            seen_types.add(normalized)

    if not requested_types:
        log("[error] invalid mimetype: provide at least one type")
        return 1

    rng = random.Random(seed)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    requested_total = count * len(requested_types)
    grouped: list[tuple[str, Target, list[Candidate]]] = []
    discovered_total = 0
    progress(gathering_progress(0, requested_total, 0, discovered_total))

    for requested_type in requested_types:
        try:
            target = build_target([requested_type])
        except Exception as exc:  # noqa: BLE001
            log(f"[error] invalid mimetype '{requested_type}': {exc}")
            return 1

        candidates = collect_candidates(target, count, timeout, rng)
        discovered_total += len(candidates)
        grouped.append((requested_type, target, candidates))
        progress(gathering_progress(0, requested_total, 0, discovered_total))

    if not grouped or discovered_total == 0:
        progress(gathering_progress(0, requested_total, 0, discovered_total), done=True)
        log("[error] no matching candidates found")
        return 1

    planned: list[tuple[PlannedDownload, Target, str]] = []
    planned_by_type: dict[str, int] = defaultdict(int)
    probe_failures_by_type: dict[str, list[str]] = defaultdict(list)
    probe_failure_counts_by_type: dict[str, int] = defaultdict(int)
    scanned = 0
    for requested_type, target, candidates in grouped:
        for candidate in candidates:
            if planned_by_type[requested_type] >= count:
                break

            scanned += 1
            probe, probe_error = probe_candidate(candidate, timeout)
            if not probe:
                probe_failure_counts_by_type[requested_type] += 1
                if probe_error:
                    _record_failure(
                        probe_failures_by_type,
                        requested_type,
                        f"{candidate.url} -> {probe_error}",
                    )
                progress(
                    gathering_progress(len(planned), requested_total, scanned, discovered_total)
                )
                continue

            planned.append((probe, target, requested_type))
            planned_by_type[requested_type] += 1
            progress(gathering_progress(len(planned), requested_total, scanned, discovered_total))

    progress(
        gathering_progress(len(planned), requested_total, scanned, discovered_total),
        done=True,
    )

    if not planned:
        log("[error] no downloadable URLs found")
        return 1

    known_total_bytes = sum(item.content_length or 0 for item, _, _ in planned)

    processed = 0
    downloaded = 0
    downloaded_bytes = 0
    failed = 0
    downloaded_by_type: dict[str, int] = defaultdict(int)
    failed_by_type: dict[str, int] = defaultdict(int)
    download_failures_by_type: dict[str, list[str]] = defaultdict(list)
    download_failure_counts_by_type: dict[str, int] = defaultdict(int)
    progress(download_progress(0, requested_total, downloaded_bytes, known_total_bytes))

    for item, target, requested_type in planned:
        processed += 1
        result, error = download_one(item, target, timeout)
        if result:
            _, size_bytes, _, _ = result
            downloaded += 1
            downloaded_bytes += size_bytes
            downloaded_by_type[requested_type] += 1

        progress(
            download_progress(processed, requested_total, downloaded_bytes, known_total_bytes),
            done=processed == len(planned),
        )

        if not result:
            failed += 1
            failed_by_type[requested_type] += 1
            download_failure_counts_by_type[requested_type] += 1
            if error:
                _record_failure(
                    download_failures_by_type,
                    requested_type,
                    f"{item.final_url} -> {error}",
                )
            continue

    log("\nSummary")
    log(f"  requested={requested_total}")
    log(f"  planned={len(planned)}")
    log(f"  downloaded={downloaded}")
    log(f"  failed={failed}")
    log(f"  bytes={human_size(downloaded_bytes)}")
    for requested_type in requested_types:
        log(
            "  "
            f"{requested_type}: requested={count} "
            f"planned={planned_by_type[requested_type]} "
            f"downloaded={downloaded_by_type[requested_type]} "
            f"failed={failed_by_type[requested_type]}"
        )

    if any(probe_failures_by_type.values()) or any(download_failures_by_type.values()):
        log("\nFailure details")
        for requested_type in requested_types:
            probe_failures = probe_failures_by_type[requested_type]
            download_failures = download_failures_by_type[requested_type]
            if not probe_failures and not download_failures:
                continue

            log(f"  {requested_type}:")
            for detail in probe_failures:
                log(f"    probe: {detail}")
            for detail in download_failures:
                log(f"    download: {detail}")

            hidden_probe = max(
                0, probe_failure_counts_by_type[requested_type] - len(probe_failures)
            )
            hidden_download = max(
                0, download_failure_counts_by_type[requested_type] - len(download_failures)
            )
            hidden = hidden_probe + hidden_download
            if hidden > 0:
                log(f"    ... {hidden} more failure(s) omitted")

    if downloaded < requested_total:
        log(f"[warn] requested {requested_total} but downloaded {downloaded}")

    return 0 if downloaded > 0 else 1
