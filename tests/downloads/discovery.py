from __future__ import annotations

import json
import random
import urllib.parse
import urllib.request
from collections import deque
from typing import Any

from tests.downloads.mime_utils import build_fq, matches_candidate
from tests.downloads.models import (
    DEFAULT_SOURCES,
    SOURCES,
    USER_AGENT,
    Candidate,
    Source,
    Target,
)


def fetch_json(url: str, timeout: int) -> dict[str, Any] | None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def discover_ckan(
    source: Source,
    *,
    target: Target,
    timeout: int,
    need: int,
    rng: random.Random,
) -> list[Candidate]:
    out: list[Candidate] = []
    rows = 100
    max_pages = max(3, min(8, need * 2))
    starts = [rows * index for index in range(max_pages)]
    rng.shuffle(starts)
    candidate_cap = max(40, need * 12)
    fq = build_fq(source, target)
    failed_requests = 0

    for start in starts:
        if len(out) >= candidate_cap:
            break

        params = {"q": "*:*", "rows": str(rows), "start": str(start)}
        if fq:
            params["fq"] = fq

        url = f"{source.endpoint}?{urllib.parse.urlencode(params)}"
        payload = fetch_json(url, timeout)
        if not payload or not payload.get("success"):
            failed_requests += 1
            if failed_requests >= 2:
                break
            continue
        failed_requests = 0

        result = payload.get("result") or {}
        packages = result.get("results")
        if not isinstance(packages, list) or not packages:
            continue

        for package in packages:
            if not isinstance(package, dict):
                continue
            for resource in package.get("resources") or []:
                if not isinstance(resource, dict):
                    continue

                raw = str(resource.get("url") or "").strip()
                if not raw.startswith(("http://", "https://")):
                    continue

                out.append(
                    Candidate(
                        url=raw,
                        source=source.key,
                        format_hint=str(resource.get("format") or "").strip() or None,
                        mime_hint=str(resource.get("mimetype") or "").strip().lower() or None,
                    )
                )
                if len(out) >= candidate_cap:
                    break
            if len(out) >= candidate_cap:
                break

    return out


def _normalize_eu_media_type(value: Any) -> str | None:
    if isinstance(value, str) and value:
        if value.startswith("http") and "/media-types/" in value:
            return value.rsplit("/", 1)[-1].lower()
        return value.lower()
    return None


def discover_europa(
    source: Source,
    *,
    timeout: int,
    need: int,
    rng: random.Random,
) -> list[Candidate]:
    out: list[Candidate] = []
    rows = 100
    max_pages = max(3, min(8, need * 2))
    starts = [rows * index for index in range(max_pages)]
    rng.shuffle(starts)
    candidate_cap = max(40, need * 12)
    failed_requests = 0

    for start in starts:
        if len(out) >= candidate_cap:
            break

        params = {"q": "*", "rows": str(rows), "start": str(start)}
        url = f"{source.endpoint}?{urllib.parse.urlencode(params)}"
        payload = fetch_json(url, timeout)
        if not payload:
            failed_requests += 1
            if failed_requests >= 2:
                break
            continue
        failed_requests = 0

        result = payload.get("result") or {}
        datasets = result.get("results")
        if not isinstance(datasets, list) or not datasets:
            continue

        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            for dist in dataset.get("distributions") or []:
                if not isinstance(dist, dict):
                    continue

                format_hint = None
                fmt = dist.get("format")
                if isinstance(fmt, dict):
                    format_hint = str(fmt.get("id") or "").strip() or None
                elif isinstance(fmt, str):
                    format_hint = fmt.strip() or None

                media_hint = _normalize_eu_media_type(dist.get("media_type"))

                for key in ("download_url", "access_url"):
                    raw = dist.get(key)
                    urls = raw if isinstance(raw, list) else [raw]
                    for item in urls:
                        if not isinstance(item, str):
                            continue

                        value = item.strip()
                        if value.startswith(("http://", "https://")):
                            out.append(
                                Candidate(
                                    url=value,
                                    source=source.key,
                                    format_hint=format_hint,
                                    mime_hint=media_hint,
                                )
                            )
                            if len(out) >= candidate_cap:
                                break
                    if len(out) >= candidate_cap:
                        break
                if len(out) >= candidate_cap:
                    break
            if len(out) >= candidate_cap:
                break

    return out


def collect_candidates(
    target: Target,
    count: int,
    timeout: int,
    rng: random.Random,
) -> list[Candidate]:
    selected_sources: list[Source] = []
    for key in DEFAULT_SOURCES:
        source = SOURCES.get(key)
        if source:
            selected_sources.append(source)

    rng.shuffle(selected_sources)
    candidate_target = max(60, count * 20)
    by_source: dict[str, list[Candidate]] = {}
    seen_urls: set[str] = set()

    for source in selected_sources:
        need = max(count * 2, 8)
        if source.kind == "ckan":
            discovered = discover_ckan(source, target=target, timeout=timeout, need=need, rng=rng)
        else:
            discovered = discover_europa(source, timeout=timeout, need=need, rng=rng)

        source_candidates: list[Candidate] = []
        for candidate in discovered:
            if candidate.url in seen_urls:
                continue
            if not matches_candidate(candidate, target):
                continue

            seen_urls.add(candidate.url)
            source_candidates.append(candidate)

        if source_candidates:
            rng.shuffle(source_candidates)
            by_source[source.key] = source_candidates

    if not by_source:
        return []

    # Interleave candidates across sources so a single catalog does not dominate.
    source_order = list(by_source.keys())
    rng.shuffle(source_order)
    queue: deque[str] = deque(source_order)
    out: list[Candidate] = []

    while queue and len(out) < candidate_target:
        source_key = queue.popleft()
        bucket = by_source[source_key]
        if not bucket:
            continue

        out.append(bucket.pop())
        if bucket:
            queue.append(source_key)

    return out
