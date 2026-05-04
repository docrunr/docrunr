"""Data models for DocRunr."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any


def _package_version() -> str:
    try:
        return version("docrunr")
    except PackageNotFoundError:
        return "0.0.0"


@dataclass(frozen=True)
class Chunk:
    """A single text chunk from a document."""

    chunk_id: str
    source_doc_id: str
    chunk_index: int
    text: str
    token_count: int
    char_count: int
    splitter_version: str
    start_offset: int = 0
    end_offset: int = 0
    section_path: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.end_offset == 0 and self.char_count > 0:
            object.__setattr__(self, "end_offset", self.start_offset + self.char_count)

    @property
    def index(self) -> int:
        """Backward-compatible alias for chunk_index."""
        return self.chunk_index

    @property
    def tokens(self) -> int:
        """Backward-compatible alias for token_count."""
        return self.token_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_index": self.chunk_index,
            "text": self.text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "section_path": list(self.section_path),
            "token_count": self.token_count,
            "char_count": self.char_count,
        }


@dataclass
class Result:
    """Processing result for a single document."""

    source: str
    markdown: str = ""
    chunks: list[Chunk] = field(default_factory=list)
    content_hash: str = ""
    total_tokens: int = 0
    mime_type: str = ""
    size_bytes: int = 0
    parser: str = ""
    duration_seconds: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def compute_hash(self) -> None:
        self.content_hash = "sha256:" + hashlib.sha256(self.markdown.encode()).hexdigest()

    def compute_totals(self) -> None:
        self.total_tokens = sum(c.token_count for c in self.chunks)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict with stable key order."""
        return {
            "docrunr_version": _package_version(),
            "source": self.source,
            "content_hash": self.content_hash,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "parser": self.parser,
            "duration_seconds": round(self.duration_seconds, 2),
            "total_tokens": self.total_tokens,
            "content": self.markdown,
            "chunks": [c.to_dict() for c in self.chunks],
        }

    def write(self, out_dir: Path, stem: str) -> tuple[Path, Path]:
        """Write .md and .json files. Returns (md_path, json_path)."""
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / f"{stem}.md"
        json_path = out_dir / f"{stem}.json"
        md_path.write_text(self.markdown, encoding="utf-8")
        json_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return md_path, json_path


@dataclass
class BatchReport:
    """Summary report for batch processing."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_seconds: float = 0.0
    files: list[dict[str, Any]] = field(default_factory=list)

    def add(self, result: Result) -> None:
        self.total += 1
        if result.ok:
            self.succeeded += 1
            self.files.append(
                {
                    "file": result.source,
                    "status": "ok",
                    "chunks": len(result.chunks),
                    "tokens": result.total_tokens,
                }
            )
        else:
            self.failed += 1
            self.files.append({"file": result.source, "status": "error", "error": result.error})

    def write(self, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "_report.json"
        data = {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "duration_seconds": round(self.duration_seconds, 2),
            "files": self.files,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
