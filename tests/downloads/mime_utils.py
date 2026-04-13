from __future__ import annotations

import re
import urllib.parse

from tests.downloads.models import MIME_DEFS, MIME_TO_EXT, Candidate, Source, Target

_FOLDER_SLUG_RE = re.compile(r"[^a-z0-9]+")


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def build_target(raw_mimetypes: list[str]) -> Target:
    aliases: set[str] = set()
    exts: set[str] = set()
    mimes: set[str] = set()
    ckan: set[str] = set()
    europa: set[str] = set()

    for token in raw_mimetypes:
        key = token.strip().lower().lstrip(".")
        if not key:
            continue

        defs = MIME_DEFS.get(key)
        if defs:
            aliases.add(key)
            exts.update(x.lower() for x in defs["ext"])
            mimes.update(x.lower() for x in defs["mime"])
            ckan.update(x.upper() for x in defs["ckan"])
            europa.update(x.upper() for x in defs["eu"])
            continue

        if "/" in key:
            mimes.add(key)
            guessed_ext = MIME_TO_EXT.get(key)
            if guessed_ext:
                exts.add(guessed_ext)
            continue

        aliases.add(key)
        exts.add(key)
        ckan.add(key.upper())
        europa.add(key.upper())

    if not aliases and not exts and not mimes:
        raise ValueError("Provide at least one mimetype, for example: pdf")

    return Target(
        aliases=aliases,
        extensions=exts,
        mime_types=mimes,
        ckan_format_ids=ckan,
        europa_format_ids=europa,
    )


def build_fq(source: Source, target: Target) -> str | None:
    if not target.ckan_format_ids:
        return None

    values: list[str] = []
    for fmt in sorted(target.ckan_format_ids):
        if source.fq_mode == "uri":
            values.append(f'"http://publications.europa.eu/resource/authority/file-type/{fmt}"')
        else:
            values.append(fmt)

    if not values:
        return None
    if len(values) == 1:
        return f"res_format:{values[0]}"
    return f"res_format:({' OR '.join(values)})"


def normalize_content_type(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.split(";", 1)[0].strip().lower() or None


def extension_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return MIME_TO_EXT.get(content_type)


def extension_from_url(url: str) -> str | None:
    try:
        path = urllib.parse.urlsplit(url).path
    except Exception:  # noqa: BLE001
        return None

    if "." not in path:
        return None
    ext = path.rsplit(".", 1)[-1].lower()
    return ext if ext and len(ext) <= 8 else None


def extract_format_token(value: str | None) -> str | None:
    if not value:
        return None

    token = value.strip()
    if not token:
        return None
    if "/" in token:
        token = token.rsplit("/", 1)[-1]
    return token.strip().upper() or None


def matches_candidate(candidate: Candidate, target: Target) -> bool:
    fmt = extract_format_token(candidate.format_hint)
    if fmt and (fmt in target.ckan_format_ids or fmt in target.europa_format_ids):
        return True

    mime = (candidate.mime_hint or "").lower()
    if mime in target.mime_types:
        return True

    ext = extension_from_url(candidate.url)
    return bool(ext and ext in target.extensions)


def should_keep_download(*, content_type: str | None, final_url: str, target: Target) -> bool:
    ct = normalize_content_type(content_type)
    if ct and ct in target.mime_types:
        return True

    ext = extension_from_content_type(ct) or extension_from_url(final_url)
    return bool(ext and ext in target.extensions)


def _slugify_for_folder(value: str) -> str:
    slug = _FOLDER_SLUG_RE.sub("-", value.encode("ascii", errors="ignore").decode("ascii").lower())
    slug = slug.strip("-")
    return slug or "unknown"


def mime_folder_name(content_type: str | None, final_url: str) -> str:
    normalized = normalize_content_type(content_type)
    url_ext = extension_from_url(final_url)
    if normalized:
        known_ext = extension_from_content_type(normalized)
        if known_ext:
            return known_ext
        if url_ext:
            return url_ext
        return _slugify_for_folder(normalized.replace("/", "-"))[:40] or "unknown"

    if url_ext:
        return url_ext
    return "unknown"


def display_mimetype(content_type: str | None, final_url: str) -> str:
    normalized = normalize_content_type(content_type)
    if normalized:
        return normalized

    ext = extension_from_url(final_url)
    if ext:
        return ext
    return "unknown"


def target_label(target: Target) -> str:
    return ",".join(sorted(target.aliases or target.extensions or target.mime_types))
