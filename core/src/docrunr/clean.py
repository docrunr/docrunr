"""Markdown normalization — deterministic cleanup rules."""

from __future__ import annotations

import re
import unicodedata


def clean_markdown(text: str) -> str:
    """Apply all cleaning passes to raw extracted Markdown."""
    blocks = _split_fenced_blocks(text)
    cleaned_parts: list[str] = []
    for is_fenced, block in blocks:
        if is_fenced:
            cleaned_parts.append(block)
            continue

        block = _normalize_unicode(block)
        block = _strip_page_numbers(block)
        block = _normalize_whitespace(block)
        block = _fix_header_spacing(block)
        block = _normalize_lists(block)
        block = _normalize_toc_blocks(block)
        block = _clean_tables(block)
        block = _collapse_blank_lines(block)
        cleaned_parts.append(block)

    return "".join(cleaned_parts).strip() + "\n"


def _normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


_PAGE_NUM_PATTERNS = [
    re.compile(r"^[-—–]\s*\d+\s*[-—–]$", re.MULTILINE),
    re.compile(r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$", re.MULTILINE),
]


def _strip_page_numbers(text: str) -> str:
    for pat in _PAGE_NUM_PATTERNS:
        text = pat.sub("", text)
    return text


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r" {2,}", " ", text)
    return text


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


_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_TOC_HEADING_RE = re.compile(
    r"^(?:table\s+of\s+contents?|contents?|toc|indice|índice|sum[aá]rio|"
    r"sommaire|inhalt(?:sverzeichnis)?|inhoudsopgave|contingut|contenido|"
    r"contenidos|目次|目录|目錄|spis\s+treści|sisällys)$",
    re.IGNORECASE,
)
_TOC_LEADER_RE = re.compile(r"(?:[.\-_=·]\s*){4,}|[.\-_=·]{5,}")
_TOC_SEPARATOR_CELL_RE = re.compile(r"^[\s:.\-_=·]+$")
_TOC_PAGE_RE = re.compile(
    r"^(?:\(\s*)?(?:p(?:g|age|agina|ágina)?\.?\s*)?"
    r"(?P<page>\d{1,5}(?:\s*[-–]\s*\d{1,5})?|[ivxlcdm]{1,12})"
    r"(?:\s*\))?$",
    re.IGNORECASE,
)


def _normalize_toc_blocks(text: str) -> str:
    lines = text.split("\n")
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        output.append(line)
        i += 1
        if not _is_toc_heading_line(line):
            continue

        start = i
        end = _find_toc_region_end(lines, start)
        output.extend(_normalize_toc_region(lines[start:end]))
        i = end
    return "\n".join(output)


def _is_toc_heading_line(line: str) -> bool:
    candidate = line.strip()
    candidate = re.sub(r"^\s{0,3}#{1,6}\s+", "", candidate)
    candidate = candidate.strip("*_`[]() ")
    candidate = candidate.strip(":：- ")
    candidate = re.sub(r"\s+", " ", candidate)
    return bool(candidate and _TOC_HEADING_RE.fullmatch(candidate))


def _find_toc_region_end(lines: list[str], start: int) -> int:
    saw_entry = False
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if _MARKDOWN_HEADING_RE.match(line) and not _is_toc_heading_line(line):
            break
        if not stripped:
            i += 1
            continue
        if _looks_like_toc_line(stripped):
            saw_entry = True
            i += 1
            continue
        if saw_entry:
            break
        # Allow a single short, non-empty lead-in row like "Section | Page".
        if len(stripped) <= 64:
            i += 1
            continue
        break
    return i


def _looks_like_toc_line(line: str) -> bool:
    if "|" in line:
        return True
    if _is_separator_only_line(line):
        return True
    if _TOC_LEADER_RE.search(line):
        return True
    if re.search(r"\t", line):
        return True
    if re.match(r"^(?:[-*+]\s+)?\d+(?:\.\d+)*\s+\S+", line):
        return True
    return _split_title_and_page(line) is not None


def _normalize_toc_region(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "|" in line:
            j = i
            while j < len(lines) and "|" in lines[j]:
                j += 1
            table_block = lines[i:j]
            normalized_table = _normalize_toc_table_block(table_block)
            if normalized_table is None:
                out.extend(table_block)
            else:
                out.extend(normalized_table)
            i = j
            continue

        normalized_line = _normalize_toc_line(line)
        if normalized_line is not None:
            out.append(normalized_line)
        i += 1
    return out


def _normalize_toc_table_block(lines: list[str]) -> list[str] | None:
    rows = [_split_markdown_table_row(line) for line in lines]
    if not rows:
        return None

    normalized: list[str] = []
    converted = 0
    for idx, cells in enumerate(rows):
        if _is_separator_row(cells):
            continue
        if idx == 0 and len(rows) > 1 and _is_separator_row(rows[1]):
            # Header row in canonical markdown tables.
            continue

        entry = _toc_entry_from_cells(cells)
        if entry is None:
            continue
        normalized.append(entry)
        converted += 1

    if converted == 0:
        return None
    return normalized


def _split_markdown_table_row(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.split("|")]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return True
    for cell in cells:
        if not cell:
            continue
        if not _TOC_SEPARATOR_CELL_RE.fullmatch(cell):
            return False
    return True


def _toc_entry_from_cells(cells: list[str]) -> str | None:
    cleaned_cells = [_clean_toc_fragment(cell) for cell in cells]
    if not any(cleaned_cells):
        return None

    page_idx: int | None = None
    page_value: str | None = None
    for idx in range(len(cleaned_cells) - 1, -1, -1):
        page = _extract_page(cleaned_cells[idx])
        if page is not None:
            page_idx = idx
            page_value = page
            break

    title_parts: list[str] = []
    for idx, cell in enumerate(cleaned_cells):
        if idx == page_idx:
            continue
        if not cell:
            continue
        if _is_separator_only_line(cell):
            continue
        title_parts.append(cell)

    title = " ".join(title_parts).strip(" -–—:;")
    if not title:
        return None
    if page_value:
        return f"{title} — page {page_value}"
    return title


def _normalize_toc_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return line
    if _is_separator_only_line(stripped):
        return None

    split = _split_title_and_page(stripped)
    if split is not None:
        title, page = split
        if page is None:
            return title
        return f"{title} — page {page}"

    if _TOC_LEADER_RE.search(stripped):
        cleaned = _clean_toc_fragment(stripped)
        return cleaned if cleaned else None

    return line


def _split_title_and_page(text: str) -> tuple[str, str | None] | None:
    raw = text.strip()
    cleaned = _clean_toc_fragment(raw)
    if not cleaned:
        return None

    parts = cleaned.split()
    for split in range(1, len(parts)):
        title_candidate = " ".join(parts[:-split]).strip(" -–—:;")
        page_candidate = " ".join(parts[-split:])
        page = _extract_page(page_candidate)
        if page is None:
            continue
        if not title_candidate:
            return None
        if not (_TOC_LEADER_RE.search(raw) or "\t" in raw or re.search(r"\s{2,}", raw)):
            return None
        return title_candidate, page

    if _TOC_LEADER_RE.search(raw):
        return cleaned.strip(" -–—:;"), None
    return None


def _extract_page(text: str) -> str | None:
    candidate = text.strip()
    if not candidate:
        return None
    m = _TOC_PAGE_RE.fullmatch(candidate)
    if not m:
        return None
    value = m.group("page").upper()
    value = re.sub(r"\s*[-–]\s*", "-", value)
    return value


def _clean_toc_fragment(text: str) -> str:
    cleaned = _TOC_LEADER_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" \t|")


def _is_separator_only_line(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 3:
        return False
    stripped = stripped.replace(" ", "")
    return bool(stripped) and all(ch in "-_=·.:" for ch in stripped)


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
