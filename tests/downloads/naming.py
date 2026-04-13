from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")
UTC_TZ = datetime.UTC if hasattr(datetime, "UTC") else timezone.utc  # noqa: UP017


def slugify(value: str, *, max_len: int = 72) -> str:
    ascii_value = value.encode("ascii", errors="ignore").decode("ascii").lower()
    slug = _SLUG_RE.sub("-", ascii_value).strip("-")
    if not slug:
        slug = "document"
    return slug[:max_len].rstrip("-") or "document"


def readable_filename(source: str, final_url: str, extension: str, out_dir: Path) -> Path:
    parsed = urllib.parse.urlsplit(final_url)
    stem = Path(urllib.parse.unquote(parsed.path)).stem
    if stem.lower() in {"", "download", "file", "resource", "index"}:
        stem = parsed.netloc or "document"

    base = slugify(f"{source}-{stem}")
    date_tag = datetime.now(UTC_TZ).strftime("%Y%m%d")
    candidate = out_dir / f"{base}-{date_tag}.{extension}"

    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        maybe = out_dir / f"{base}-{date_tag}-{suffix}.{extension}"
        if not maybe.exists():
            return maybe
        suffix += 1
