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


class _FakeRubyOutput:
    label = "erb"
    mime_type = "text/x-ruby"


class _FakeRubyResult:
    output = _FakeRubyOutput()


class _FakeRubyMagika:
    def identify_path(self, path: Path) -> _FakeRubyResult:  # noqa: ARG002
        return _FakeRubyResult()


def test_detect_html_prefers_extension_when_magika_says_ruby(monkeypatch) -> None:
    monkeypatch.setattr(detect, "_get_magika", lambda: _FakeRubyMagika())
    assert detect.detect_mime(Path("page.html")) == "text/html"
    assert detect.detect_mime(Path("page.htm")) == "text/html"


def test_detect_html_keeps_pdf_when_magika_is_sure(monkeypatch) -> None:
    class _FakePdfOutput:
        label = "pdf"
        mime_type = "application/pdf"

    class _FakePdfResult:
        output = _FakePdfOutput()

    class _FakePdfMagika:
        def identify_path(self, path: Path) -> _FakePdfResult:  # noqa: ARG002
            return _FakePdfResult()

    monkeypatch.setattr(detect, "_get_magika", lambda: _FakePdfMagika())
    assert detect.detect_mime(Path("scan.html")) == "application/pdf"


def test_erb_like_html_file_is_detected_as_html(tmp_path: Path) -> None:
    path = tmp_path / "templated.html"
    path.write_text(
        "<!DOCTYPE html>\n"
        "<html><body>\n"
        "<% if user %><h1>Hello</h1><% end %>\n"
        "<p>A paragraph of document content for extraction.</p>\n"
        "</body></html>\n",
        encoding="utf-8",
    )
    assert detect.detect_mime(path) == "text/html"
