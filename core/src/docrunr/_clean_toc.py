"""Table-of-contents normalization helpers."""

from __future__ import annotations

import re

from ._text import normalize_for_comparison

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


def normalize_toc_blocks(text: str) -> str:
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


def is_separator_only_line(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 3:
        return False
    stripped = stripped.replace(" ", "")
    return bool(stripped) and all(ch in "-_=·.:" for ch in stripped)


def _is_toc_heading_line(line: str) -> bool:
    candidate = line.strip()
    candidate = re.sub(r"^\s{0,3}#{1,6}\s+", "", candidate)
    candidate = candidate.strip("*_`[]() ")
    candidate = candidate.strip(":：- ")
    candidate = normalize_for_comparison(candidate)
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
        if len(stripped) <= 64:
            i += 1
            continue
        break
    return i


def _looks_like_toc_line(line: str) -> bool:
    if "|" in line:
        return True
    if is_separator_only_line(line):
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
        if is_separator_only_line(cell):
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
    if is_separator_only_line(stripped):
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
