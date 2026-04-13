"""Deterministic recursive, boundary-aware Markdown chunking."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from bisect import bisect_right
from dataclasses import dataclass
from statistics import fmean

import tiktoken

from .models import Chunk

log = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE_TOKENS = 300
DEFAULT_CHUNK_OVERLAP_TOKENS = 0
DEFAULT_MAX_CHUNK_TOKENS = 450
DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ".", "?", "!", " ", "")
MIN_RECOMMENDED_CHUNK_TOKENS = 200

_encoder: tiktoken.Encoding | None = None
_ATX_HEADING_RE = re.compile(r"^( {0,3})(#{1,6})[ \t]+(.+?)[ \t]*(?:#+[ \t]*)?$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class ChunkingConfig:
    """Lightweight chunking configuration with deterministic defaults."""

    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS
    chunk_overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS
    separators: tuple[str, ...] = DEFAULT_SEPARATORS

    def __post_init__(self) -> None:
        if self.chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens must be > 0")
        if self.max_chunk_tokens <= 0:
            raise ValueError("max_chunk_tokens must be > 0")
        if self.chunk_size_tokens > self.max_chunk_tokens:
            raise ValueError("chunk_size_tokens must be <= max_chunk_tokens")
        if self.chunk_overlap_tokens != 0:
            raise ValueError("chunk_overlap_tokens must be 0 for deterministic baseline")
        if not self.separators:
            raise ValueError("separators cannot be empty")


@dataclass(frozen=True)
class _Span:
    """A text segment tied to character offsets in source markdown."""

    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _SectionPathState:
    """Active section path at a source offset."""

    offset: int
    path: tuple[str, ...]


@dataclass(frozen=True)
class _SectionPathResolver:
    """Resolve chunk offsets to active heading ancestry."""

    positions: tuple[int, ...]
    states: tuple[_SectionPathState, ...]

    def path_for(self, offset: int) -> list[str]:
        if not self.states:
            return []
        idx = bisect_right(self.positions, offset) - 1
        if idx < 0:
            return []
        return list(self.states[idx].path)


def _get_encoder() -> tiktoken.Encoding:
    global _encoder  # noqa: PLW0603
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


def derive_source_doc_id(source: str) -> str:
    """Derive a stable source document id from processing context."""
    normalized = _normalize_for_hash(source)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"doc_{digest[:16]}"


def splitter_version(config: ChunkingConfig) -> str:
    return f"recursive_v1_token{config.chunk_size_tokens}_overlap{config.chunk_overlap_tokens}"


def chunk_markdown(
    markdown: str,
    target_tokens: int | None = None,
    *,
    source_doc_id: str | None = None,
    config: ChunkingConfig | None = None,
) -> list[Chunk]:
    """Split Markdown into deterministic, boundary-aware, token-centered chunks.

    Offset behavior:
    - Offsets refer to the cleaned markdown input passed to this function.
    - Offsets are exact for the raw text spans selected before whitespace normalization.
    - After whitespace normalization inside chunk text, offsets are best-effort but deterministic.
    """
    active = _build_config(config=config, target_tokens=target_tokens)
    src_id = source_doc_id or derive_source_doc_id("inline_markdown")
    split_ver = splitter_version(active)

    if not markdown.strip():
        _log_distribution(src_id, [], duplicate_count=0)
        return []

    section_path_resolver = _build_section_path_resolver(markdown)
    section_seed_spans = _split_on_section_boundaries(markdown, section_path_resolver)
    packed_spans: list[_Span] = []
    for seed in section_seed_spans:
        raw_spans = _split_recursive(
            seed,
            separators=active.separators,
            target_tokens=active.chunk_size_tokens,
            max_chunk_tokens=active.max_chunk_tokens,
        )
        packed_spans.extend(
            _pack_spans(
                raw_spans,
                target_tokens=active.chunk_size_tokens,
                max_chunk_tokens=active.max_chunk_tokens,
            )
        )

    chunks: list[Chunk] = []
    seen_texts: set[tuple[str, tuple[str, ...]]] = set()
    duplicate_count = 0

    for span in packed_spans:
        text, start_offset, end_offset = _normalize_text_with_offsets(
            source=markdown,
            start=span.start,
            end=span.end,
        )

        if not text or text.isspace():
            continue

        token_count = count_tokens(text)
        if token_count <= 0:
            continue

        # Guard: recursively split again if hard cap exceeded after normalization.
        if token_count > active.max_chunk_tokens:
            enforced = _split_recursive(
                _Span(text=text, start=start_offset, end=end_offset),
                separators=active.separators,
                target_tokens=active.chunk_size_tokens,
                max_chunk_tokens=active.max_chunk_tokens,
            )
            repacked = _pack_spans(
                enforced,
                target_tokens=active.chunk_size_tokens,
                max_chunk_tokens=active.max_chunk_tokens,
            )
            for sub in repacked:
                stxt, sstart, send = _normalize_text_with_offsets(
                    source=markdown,
                    start=sub.start,
                    end=sub.end,
                )
                if not stxt or stxt.isspace():
                    continue
                sub_tokens = count_tokens(stxt)
                if sub_tokens <= 0:
                    continue
                if sub_tokens > active.max_chunk_tokens:
                    final = _split_force_token_windows(
                        _Span(text=stxt, start=sstart, end=send),
                        target_tokens=active.chunk_size_tokens,
                    )
                    for forced in final:
                        _append_chunk(
                            chunks=chunks,
                            seen_texts=seen_texts,
                            source_doc_id=src_id,
                            split_ver=split_ver,
                            span=forced,
                            section_path=section_path_resolver.path_for(forced.start),
                        )
                    continue
                dup = _append_chunk(
                    chunks=chunks,
                    seen_texts=seen_texts,
                    source_doc_id=src_id,
                    split_ver=split_ver,
                    span=_Span(text=stxt, start=sstart, end=send),
                    section_path=section_path_resolver.path_for(sstart),
                )
                if dup:
                    duplicate_count += 1
            continue

        dup = _append_chunk(
            chunks=chunks,
            seen_texts=seen_texts,
            source_doc_id=src_id,
            split_ver=split_ver,
            span=_Span(text=text, start=start_offset, end=end_offset),
            section_path=section_path_resolver.path_for(start_offset),
        )
        if dup:
            duplicate_count += 1

    _log_distribution(src_id, chunks, duplicate_count=duplicate_count)
    return chunks


def _build_config(*, config: ChunkingConfig | None, target_tokens: int | None) -> ChunkingConfig:
    if target_tokens is not None:
        base = config or ChunkingConfig()
        return ChunkingConfig(
            chunk_size_tokens=target_tokens,
            chunk_overlap_tokens=base.chunk_overlap_tokens,
            max_chunk_tokens=base.max_chunk_tokens,
            separators=base.separators,
        )
    return config or ChunkingConfig()


def _append_chunk(
    *,
    chunks: list[Chunk],
    seen_texts: set[tuple[str, tuple[str, ...]]],
    source_doc_id: str,
    split_ver: str,
    span: _Span,
    section_path: list[str],
) -> bool:
    text = span.text
    normalized_for_dedupe = (text, tuple(section_path))
    if normalized_for_dedupe in seen_texts:
        return True
    seen_texts.add(normalized_for_dedupe)

    token_count = count_tokens(text)
    char_count = len(text)
    chunk_index = len(chunks)
    chunk_hash_input = f"{source_doc_id}|{chunk_index}|{_normalize_for_hash(text)}"
    chunk_id = hashlib.sha256(chunk_hash_input.encode("utf-8")).hexdigest()

    chunks.append(
        Chunk(
            chunk_id=chunk_id,
            source_doc_id=source_doc_id,
            chunk_index=chunk_index,
            text=text,
            token_count=token_count,
            char_count=char_count,
            splitter_version=split_ver,
            section_path=list(section_path),
        )
    )
    return False


def _build_section_path_resolver(markdown: str) -> _SectionPathResolver:
    states = _build_section_path_states(markdown)
    frozen_states = tuple(states)
    return _SectionPathResolver(
        positions=tuple(state.offset for state in frozen_states),
        states=frozen_states,
    )


def _build_section_path_states(markdown: str) -> list[_SectionPathState]:
    states: list[_SectionPathState] = []
    active_path: list[str] = []
    in_fence = False
    fence_char = ""
    fence_size = 0
    offset = 0

    for line in markdown.splitlines(keepends=True):
        line_no_newline = line.rstrip("\n\r")
        fence = _FENCE_RE.match(line_no_newline)
        if fence:
            marker = fence.group(1)
            marker_char = marker[0]
            marker_len = len(marker)
            if not in_fence:
                in_fence = True
                fence_char = marker_char
                fence_size = marker_len
            elif marker_char == fence_char and marker_len >= fence_size:
                in_fence = False
                fence_char = ""
                fence_size = 0
            offset += len(line)
            continue

        if not in_fence:
            heading = _ATX_HEADING_RE.match(line_no_newline)
            if heading:
                level = len(heading.group(2))
                title = heading.group(3).strip()
                if title:
                    active_path = active_path[: level - 1]
                    active_path.append(title)
                    states.append(
                        _SectionPathState(
                            offset=offset + len(heading.group(1)),
                            path=tuple(active_path),
                        )
                    )
        offset += len(line)

    return states


def _split_on_section_boundaries(
    markdown: str, section_path_resolver: _SectionPathResolver
) -> list[_Span]:
    if not markdown:
        return []

    boundaries = [0]
    boundaries.extend(
        state.offset for state in section_path_resolver.states if 0 < state.offset < len(markdown)
    )
    boundaries.append(len(markdown))
    ordered = sorted(set(boundaries))

    out: list[_Span] = []
    for idx in range(len(ordered) - 1):
        start = ordered[idx]
        end = ordered[idx + 1]
        if start >= end:
            continue
        out.append(_Span(text=markdown[start:end], start=start, end=end))
    return out


def _split_recursive(
    span: _Span,
    *,
    separators: tuple[str, ...],
    target_tokens: int,
    max_chunk_tokens: int,
    separator_index: int = 0,
) -> list[_Span]:
    if not span.text:
        return []

    tok = count_tokens(span.text)
    if tok <= max_chunk_tokens:
        return [span]

    if separator_index >= len(separators):
        return _split_force_token_windows(span, target_tokens=target_tokens)

    separator = separators[separator_index]
    if separator == "":
        return _split_force_token_windows(span, target_tokens=target_tokens)

    pieces = _split_on_separator(span, separator)
    if len(pieces) <= 1:
        return _split_recursive(
            span,
            separators=separators,
            target_tokens=target_tokens,
            max_chunk_tokens=max_chunk_tokens,
            separator_index=separator_index + 1,
        )

    out: list[_Span] = []
    for piece in pieces:
        if not piece.text:
            continue
        ptok = count_tokens(piece.text)
        if ptok <= max_chunk_tokens:
            out.append(piece)
        else:
            out.extend(
                _split_recursive(
                    piece,
                    separators=separators,
                    target_tokens=target_tokens,
                    max_chunk_tokens=max_chunk_tokens,
                    separator_index=separator_index + 1,
                )
            )
    return out


def _split_on_separator(span: _Span, separator: str) -> list[_Span]:
    text = span.text
    parts: list[_Span] = []
    cursor = 0

    while cursor < len(text):
        at = text.find(separator, cursor)
        if at == -1:
            if cursor < len(text):
                seg = text[cursor:]
                parts.append(
                    _Span(
                        text=seg,
                        start=span.start + cursor,
                        end=span.start + len(text),
                    )
                )
            break

        end_local = at + len(separator)
        seg = text[cursor:end_local]
        parts.append(
            _Span(
                text=seg,
                start=span.start + cursor,
                end=span.start + end_local,
            )
        )
        cursor = end_local

    return parts


def _split_force_token_windows(span: _Span, *, target_tokens: int) -> list[_Span]:
    text = span.text
    if not text:
        return []

    out: list[_Span] = []
    start_local = 0
    while start_local < len(text):
        best_end = _best_token_window_end(text, start_local, target_tokens)
        if best_end <= start_local:
            best_end = start_local + 1
        out.append(
            _Span(
                text=text[start_local:best_end],
                start=span.start + start_local,
                end=span.start + best_end,
            )
        )
        start_local = best_end
    return out


def _best_token_window_end(text: str, start_local: int, target_tokens: int) -> int:
    low = start_local + 1
    high = len(text)
    best = start_local

    while low <= high:
        mid = (low + high) // 2
        tok = count_tokens(text[start_local:mid])
        if 0 < tok <= target_tokens:
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    return best


def _pack_spans(
    spans: list[_Span],
    *,
    target_tokens: int,
    max_chunk_tokens: int,
) -> list[_Span]:
    if not spans:
        return []

    out: list[_Span] = []
    current_parts: list[_Span] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current_parts, current_tokens
        if not current_parts:
            return
        start = current_parts[0].start
        end = current_parts[-1].end
        text = "".join(part.text for part in current_parts)
        out.append(_Span(text=text, start=start, end=end))
        current_parts = []
        current_tokens = 0

    for span in spans:
        if not span.text:
            continue
        tok = count_tokens(span.text)
        if tok > max_chunk_tokens:
            flush()
            forced = _split_force_token_windows(span, target_tokens=target_tokens)
            for f in forced:
                out.append(f)
            continue

        if not current_parts:
            current_parts = [span]
            current_tokens = tok
            continue

        next_tokens = current_tokens + tok
        should_add = next_tokens <= target_tokens or (
            current_tokens < MIN_RECOMMENDED_CHUNK_TOKENS and next_tokens <= max_chunk_tokens
        )

        if should_add:
            current_parts.append(span)
            current_tokens = next_tokens
        else:
            flush()
            current_parts = [span]
            current_tokens = tok

    flush()
    return out


def _normalize_text_with_offsets(*, source: str, start: int, end: int) -> tuple[str, int, int]:
    raw = source[start:end]
    if not raw:
        return "", start, end

    leading = len(raw) - len(raw.lstrip())
    trailing = len(raw) - len(raw.rstrip())
    adj_start = start + leading
    adj_end = end - trailing if trailing > 0 else end
    if adj_start > adj_end:
        adj_start = start
        adj_end = end

    core = source[adj_start:adj_end]
    normalized = _normalize_chunk_text(core)
    return normalized, adj_start, adj_end


def _normalize_chunk_text(text: str) -> str:
    # Keep chunk payload semantically identical to cleaned markdown.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    rank = max(1, math.ceil(p * len(sorted_values)))
    idx = min(rank - 1, len(sorted_values) - 1)
    return sorted_values[idx]


def _log_distribution(source_doc_id: str, chunks: list[Chunk], *, duplicate_count: int) -> None:
    if not chunks:
        log.info(
            "Chunk stats doc=%s chunks=0 duplicate_count=%d duplicate_ratio=0.00",
            source_doc_id,
            duplicate_count,
        )
        return

    counts = [c.token_count for c in chunks]
    total = len(chunks)
    ratio = duplicate_count / (total + duplicate_count) if (total + duplicate_count) > 0 else 0.0

    log.info(
        (
            "Chunk stats doc=%s chunks=%d min=%d mean=%.1f p50=%d p95=%d max=%d "
            "duplicate_count=%d duplicate_ratio=%.4f"
        ),
        source_doc_id,
        total,
        min(counts),
        fmean(counts),
        _percentile(counts, 0.50),
        _percentile(counts, 0.95),
        max(counts),
        duplicate_count,
        ratio,
    )
