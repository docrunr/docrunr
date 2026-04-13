"""Unit tests for RabbitMQ integration helpers (no live services required)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from tests.integration.rmq_helpers import collect_results_for


@dataclass(frozen=True)
class _Delivery:
    delivery_tag: int


class _FakeChannel:
    def __init__(self, payloads: list[bytes]) -> None:
        self._payloads = payloads
        self._next_tag = 1
        self.acked: list[int] = []
        self.nacked: list[tuple[int, bool]] = []

    def basic_get(self, _queue: str, auto_ack: bool = False) -> tuple[object, object, bytes]:
        assert auto_ack is False
        if not self._payloads:
            return (None, None, b"")
        body = self._payloads.pop(0)
        method = _Delivery(delivery_tag=self._next_tag)
        self._next_tag += 1
        return (method, None, body)

    def basic_ack(self, delivery_tag: int) -> None:
        self.acked.append(delivery_tag)

    def basic_nack(self, delivery_tag: int, requeue: bool) -> None:
        self.nacked.append((delivery_tag, requeue))


def test_collect_results_acks_unknown_messages_and_continues() -> None:
    channel = _FakeChannel(
        [
            json.dumps({"job_id": "other-job", "status": "ok"}).encode(),
            json.dumps({"job_id": "job-1", "status": "ok"}).encode(),
        ]
    )

    results = collect_results_for(
        channel,  # type: ignore[arg-type]
        {"job-1"},
        timeout_sec=0.1,
        poll_interval_sec=0.0,
    )

    assert set(results) == {"job-1"}
    assert channel.acked == [1, 2]
    assert channel.nacked == []


def test_collect_results_nacks_and_raises_on_invalid_payload() -> None:
    channel = _FakeChannel([b"not-json"])

    with pytest.raises(json.JSONDecodeError):
        collect_results_for(
            channel,  # type: ignore[arg-type]
            {"job-1"},
            timeout_sec=0.1,
            poll_interval_sec=0.0,
        )

    assert channel.acked == []
    assert channel.nacked == [(1, True)]
