from __future__ import annotations


def human_size(size: int) -> str:
    value = float(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.2f} {unit}"


def _bar(done: int, total: int) -> str:
    width = 26
    ratio = 0.0 if total <= 0 else min(1.0, done / total)
    filled = int(width * ratio)
    return "#" * filled + "-" * (width - filled)


def gathering_progress(found: int, target: int, scanned: int, discovered: int) -> str:
    bar = _bar(found, target)
    return f"gather   [{bar}] {found}/{target} files | scanned {scanned}/{discovered}"


def download_progress(done: int, total: int, downloaded_bytes: int, known_total_bytes: int) -> str:
    bar = _bar(done, total)
    message = f"download [{bar}] {done}/{total} files | {human_size(downloaded_bytes)}"
    if known_total_bytes > 0:
        pct = min(100.0, (downloaded_bytes / known_total_bytes) * 100)
        message += f" of ~{human_size(known_total_bytes)} ({pct:.1f}%)"
    return message
