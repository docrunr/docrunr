"""Markdown normalization — deterministic cleanup rules."""

from __future__ import annotations

import re
import unicodedata

from ._clean_toc import is_separator_only_line, normalize_toc_blocks
from ._text import normalize_for_comparison


def clean_markdown(text: str) -> str:
    """Apply all cleaning passes to raw extracted Markdown."""
    blocks = _split_fenced_blocks(text)
    cleaned_parts: list[str] = []
    for is_fenced, block in blocks:
        if is_fenced:
            cleaned_parts.append(block)
            continue

        block = _normalize_unicode(block)
        block = _strip_repeated_headers_and_footers(block)
        block = _normalize_page_breaks(block)
        block = _strip_page_numbers(block)
        block = _normalize_whitespace(block)
        block = _normalize_dehyphenation(block)
        block = _fix_header_spacing(block)
        block = _normalize_lists(block)
        block = _repair_list_continuations(block)
        block = normalize_toc_blocks(block)
        block = _clean_tables(block)
        block = _collapse_blank_lines(block)
        cleaned_parts.append(block)

    return "".join(cleaned_parts).strip() + "\n"


def _normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _strip_repeated_headers_and_footers(text: str) -> str:
    pages = _split_pages(text)
    if len(pages) < 2:
        return text

    header = _select_repeated_edge(pages, first=True)
    footer = _select_repeated_edge(pages, first=False)
    if header is None and footer is None:
        return text

    cleaned_pages = [_strip_page_edge(page, header=header, footer=footer) for page in pages]
    return "\n\n".join(page.strip("\n") for page in cleaned_pages if page.strip())


def _split_pages(text: str) -> list[str]:
    if "\f" not in text:
        return [text]
    return [page for page in text.split("\f") if page.strip()]


def _select_repeated_edge(pages: list[str], *, first: bool) -> str | None:
    counts: dict[str, int] = {}
    for page in pages:
        candidate = _page_edge_line(page, first=first)
        if candidate is None:
            continue
        counts[candidate] = counts.get(candidate, 0) + 1

    threshold = max(2, (len(pages) + 1) // 2)
    for candidate, count in counts.items():
        if count >= threshold:
            return candidate
    return None


def _page_edge_line(page: str, *, first: bool) -> str | None:
    lines = [line.strip() for line in page.split("\n") if line.strip()]
    if not lines:
        return None
    candidate = lines[0] if first else lines[-1]
    if _is_page_number_line(candidate):
        return None
    if len(candidate) > 80:
        return None
    if candidate.startswith(("#", "|", "```", "~~~")):
        return None
    if re.match(r"^(?:[-*+]|\d+[.)])\s+", candidate):
        return None
    return normalize_for_comparison(candidate)


def _strip_page_edge(page: str, *, header: str | None, footer: str | None) -> str:
    lines = page.split("\n")
    non_empty = [idx for idx, line in enumerate(lines) if line.strip()]
    if not non_empty:
        return page

    if header is not None:
        first_idx = non_empty[0]
        if normalize_for_comparison(lines[first_idx]) == header:
            lines[first_idx] = ""

    if footer is not None:
        footer_candidates = [idx for idx, line in enumerate(lines) if line.strip()]
        if footer_candidates:
            last_idx = footer_candidates[-1]
            if normalize_for_comparison(lines[last_idx]) == footer:
                lines[last_idx] = ""

    return "\n".join(lines)


def _normalize_page_breaks(text: str) -> str:
    return text.replace("\f", "\n\n")


_PAGE_NUM_PATTERNS = [
    re.compile(r"^[-—–]\s*\d+\s*[-—–]$", re.MULTILINE),
    re.compile(r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$", re.MULTILINE),
]


def _strip_page_numbers(text: str) -> str:
    for pat in _PAGE_NUM_PATTERNS:
        text = pat.sub("", text)
    return text


def _is_page_number_line(text: str) -> bool:
    stripped = text.strip()
    return any(pat.fullmatch(stripped) for pat in _PAGE_NUM_PATTERNS)


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r" {2,}", " ", text)
    return text


def _normalize_dehyphenation(text: str) -> str:
    return re.sub(r"([a-z]{2,})-[ \t]*\n(?:[ \t]*\n)*[ \t]*(?=[a-z])", r"\1", text)


def _fix_header_spacing(text: str) -> str:
    text = re.sub(r"\n{3,}(#{1,6}\s)", r"\n\n\1", text)
    text = re.sub(r"(#{1,6}\s[^\n]+)\n(?!\n)", r"\1\n\n", text)
    return text


def _normalize_lists(text: str) -> str:
    text = re.sub(r"^(\s*)[•●○◦▪▸►]\s*", r"\1- ", text, flags=re.MULTILINE)

    # PDF markers (parsers flatten nesting): circle → L2, section → L3.
    text = re.sub(r"^- o ", "  - ", text, flags=re.MULTILINE)
    text = re.sub(r"^o ", "  - ", text, flags=re.MULTILINE)
    text = re.sub(r"^- § ", "    - ", text, flags=re.MULTILINE)
    text = re.sub(r"^§ ", "    - ", text, flags=re.MULTILINE)

    # MarkItDown nested lists: uses 1-space indent with cycling markers.
    # Fix indentation so nested items render properly in markdown.
    text = _fix_markitdown_list_indent(text)

    # Normalize all remaining list markers (* + ▸) to -
    text = re.sub(r"^(\s*)[*+] ", r"\1- ", text, flags=re.MULTILINE)

    return text


_LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+.+$")


def _repair_list_continuations(text: str) -> str:
    lines = text.split("\n")
    repaired: list[str] = []

    for idx, line in enumerate(lines):
        if not line.strip():
            if _blank_line_precedes_list_continuation(lines, repaired, idx):
                continue
            repaired.append(line)
            continue

        continuation_indent = _list_continuation_indent(lines, repaired, idx)
        if continuation_indent is None:
            repaired.append(line)
            continue

        repaired.append(f"{' ' * continuation_indent}{line.strip()}")

    return "\n".join(repaired)


def _blank_line_precedes_list_continuation(lines: list[str], repaired: list[str], idx: int) -> bool:
    prev_idx = _last_nonempty_index(repaired)
    next_idx = _next_nonempty_index(lines, idx)
    if prev_idx is None or next_idx is None:
        return False
    previous = repaired[prev_idx]
    current = lines[next_idx]
    if not _LIST_ITEM_RE.match(previous):
        return False
    return _list_continuation_indent(
        lines, repaired, next_idx
    ) is not None and not _LIST_ITEM_RE.match(current)


def _list_continuation_indent(lines: list[str], repaired: list[str], idx: int) -> int | None:
    line = lines[idx]
    if _LIST_ITEM_RE.match(line):
        return None
    if line.startswith((" ", "\t")):
        return None
    if _looks_like_block_boundary(line):
        return None

    prev_idx = _last_nonempty_index(repaired)
    next_idx = _next_nonempty_index(lines, idx)
    if prev_idx is None or next_idx is None:
        return None

    previous = repaired[prev_idx]
    previous_match = _LIST_ITEM_RE.match(previous)
    if previous_match is None:
        return None

    next_line = lines[next_idx]
    if not _LIST_ITEM_RE.match(next_line):
        return None

    return len(previous_match.group(1)) + 2


def _last_nonempty_index(lines: list[str]) -> int | None:
    for idx in range(len(lines) - 1, -1, -1):
        if lines[idx].strip():
            return idx
    return None


def _next_nonempty_index(lines: list[str], idx: int) -> int | None:
    for pos in range(idx + 1, len(lines)):
        if lines[pos].strip():
            return pos
    return None


def _looks_like_block_boundary(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped.startswith(("#", "|", "```", "~~~", ">")) or is_separator_only_line(stripped)
    )


_MARKITDOWN_MARKER_DEPTH = {"+": 2, "-": 3, "*": 4}


def _fix_markitdown_list_indent(text: str) -> str:
    """Fix MarkItDown's 1-space nested list indentation to proper markdown.

    Mammoth (used by MarkItDown for DOCX) cycles markers to encode depth:
    * = level 1/4/7, + = level 2/5/8, - = level 3/6/9.
    """
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        m = re.match(r"^( +)([*+\-]) (.*)$", line)
        if m:
            marker = m.group(2)
            content = m.group(3)
            depth = _MARKITDOWN_MARKER_DEPTH.get(marker, 2)
            result.append(f"{'  ' * depth}- {content}")
        else:
            result.append(line)
    return "\n".join(result)


def _clean_tables(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if "|" in line:
            cells = line.split("|")
            cells = [c.strip() for c in cells]
            line = " | ".join(cells)
            if line.startswith(" | "):
                line = "|" + line[2:]
            if line.endswith(" | "):
                line = line[:-2] + "|"
        cleaned.append(line)
    return "\n".join(cleaned)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


_FENCE_OPEN_RE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})")


def _split_fenced_blocks(text: str) -> list[tuple[bool, str]]:
    """Split markdown into (is_fenced_code_block, text) segments."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return [(False, text)]

    parts: list[tuple[bool, str]] = []
    current: list[str] = []
    in_fence = False
    fence_char = ""
    min_len = 0

    for line in lines:
        if in_fence:
            current.append(line)
            if _is_fence_close_line(line, fence_char=fence_char, min_len=min_len):
                parts.append((True, "".join(current)))
                current = []
                in_fence = False
            continue

        match = _FENCE_OPEN_RE.match(line)
        if not match:
            current.append(line)
            continue

        if current:
            parts.append((False, "".join(current)))
            current = []

        fence = match.group("fence")
        fence_char = fence[0]
        min_len = len(fence)
        in_fence = True
        current.append(line)

    if current:
        parts.append((in_fence, "".join(current)))

    return parts


def _is_fence_close_line(line: str, *, fence_char: str, min_len: int) -> bool:
    stripped = line.strip()
    if len(stripped) < min_len:
        return False
    return all(ch == fence_char for ch in stripped)
