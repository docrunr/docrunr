"""Centralized LLM worker job lifecycle statuses for persistence and UI."""

from __future__ import annotations

PROCESSING = "processing"
OK = "ok"
ERROR = "error"

TERMINAL_STATUSES: frozenset[str] = frozenset({OK, ERROR})


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def replay_stats_transition(
    cur_status: str | None,
    cur_suppress: int,
    incoming_status: str,
    *,
    incoming_duration_seconds: float = 0.0,
    incoming_finished_at: str | None = None,
) -> tuple[int, int, float, str | None, int]:
    """Per-event effect on aggregate counters and the ``replay_stats_suppress`` row flag.

    Same semantics as extraction worker: after a successful **ok**, a later replay should not
    bump ``processed``/``failed`` again.

    Returns ``(ok_delta, err_delta, duration_delta, finished_at_if_counted, new_replay_suppress)``.
    """
    incoming = incoming_status.strip() if incoming_status else ""
    prior_terminal = cur_status is not None and is_terminal(cur_status)

    if incoming == PROCESSING:
        new_suppress = 1 if prior_terminal and cur_status == OK else 0
        return 0, 0, 0.0, None, new_suppress

    if is_terminal(incoming):
        if cur_suppress == 1:
            return 0, 0, 0.0, None, 0
        if not prior_terminal:
            fin = incoming_finished_at
            if incoming == OK:
                return 1, 0, incoming_duration_seconds, fin, 0
            if incoming == ERROR:
                return 0, 1, 0.0, fin, 0
            return 0, 0, 0.0, None, 0
        return 0, 0, 0.0, None, cur_suppress

    return 0, 0, 0.0, None, cur_suppress
