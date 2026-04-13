from __future__ import annotations

import sys

_last_progress_len = 0


def progress(message: str, *, done: bool = False) -> None:
    global _last_progress_len

    pad = ""
    if len(message) < _last_progress_len:
        pad = " " * (_last_progress_len - len(message))

    end = "\n" if done else ""
    sys.stdout.write(f"\r{message}{pad}{end}")
    sys.stdout.flush()
    _last_progress_len = 0 if done else len(message)


def log(message: str) -> None:
    global _last_progress_len
    if _last_progress_len:
        sys.stdout.write("\n")
        sys.stdout.flush()
        _last_progress_len = 0
    print(message, flush=True)
