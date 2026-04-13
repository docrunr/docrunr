"""Tests for quality scoring."""

from __future__ import annotations

from docrunr.quality import passes, score


class TestScore:
    def test_empty(self) -> None:
        assert score("") == 0.0
        assert score("   ") == 0.0

    def test_good_markdown(self) -> None:
        text = (
            "# Introduction\n\nThis is a well-structured document with multiple paragraphs."
            "\n\n## Methods\n\nWe used several approaches to analyze the data."
        )
        s = score(text)
        assert s > 0.5

    def test_garbage(self) -> None:
        text = "\x00\x01\x02\x03" * 50
        s = score(text)
        assert s <= 0.4


class TestPasses:
    def test_good_passes(self) -> None:
        text = "# Title\n\nA meaningful paragraph with real content and structure."
        assert passes(text) is True

    def test_empty_fails(self) -> None:
        assert passes("") is False
