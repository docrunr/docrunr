"""Tests for MIME detection."""

from __future__ import annotations

from pathlib import Path

import docrunr.detect as detect


class _FakeOutput:
    label = "ppt"
    mime_type = "application/octet-stream"


class _FakeResult:
    output = _FakeOutput()


class _FakeMagika:
    def identify_path(self, path: Path) -> _FakeResult:  # noqa: ARG002
        return _FakeResult()


def test_detect_ppt_from_magika_label(monkeypatch) -> None:
    monkeypatch.setattr(detect, "_get_magika", lambda: _FakeMagika())
    assert detect.detect_mime(Path("slides.bin")) == "application/vnd.ms-powerpoint"


def test_detect_ppt_from_extension_fallback(monkeypatch) -> None:
    def _raise() -> _FakeMagika:
        raise RuntimeError("magika unavailable")

    monkeypatch.setattr(detect, "_get_magika", _raise)
    assert detect.detect_mime(Path("slides.ppt")) == "application/vnd.ms-powerpoint"


class _FakeTextOutput:
    label = "txt"
    mime_type = "text/plain"


class _FakeTextResult:
    output = _FakeTextOutput()


class _FakeTextMagika:
    def identify_path(self, path: Path) -> _FakeTextResult:  # noqa: ARG002
        return _FakeTextResult()


def test_detect_html_prefers_extension_when_magika_is_generic_text(monkeypatch) -> None:
    monkeypatch.setattr(detect, "_get_magika", lambda: _FakeTextMagika())
    assert detect.detect_mime(Path("page.html")) == "text/html"
