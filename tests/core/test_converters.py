"""Tests for parser converter helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from docrunr.parsers._converters import parse_with_kreuzberg


class TestKreuzbergConverter:
    def test_requests_markdown_output_format(self, tmp_path: Path) -> None:
        sample = tmp_path / "legacy.doc"
        sample.write_text("dummy", encoding="utf-8")

        cfg = object()
        result = SimpleNamespace(content="# Heading\n\nBody")

        with (
            patch("kreuzberg.ExtractionConfig", return_value=cfg) as mock_config,
            patch("kreuzberg.extract_file_sync", return_value=result) as mock_extract,
        ):
            text = parse_with_kreuzberg(sample, "application/msword")

        assert text == "# Heading\n\nBody"
        mock_config.assert_called_once_with(output_format="markdown")
        mock_extract.assert_called_once_with(str(sample), "application/msword", config=cfg)

    def test_raises_on_empty_kreuzberg_output(self, tmp_path: Path) -> None:
        sample = tmp_path / "legacy.doc"
        sample.write_text("dummy", encoding="utf-8")

        with (
            patch("kreuzberg.ExtractionConfig", return_value=object()),
            patch("kreuzberg.extract_file_sync", return_value=SimpleNamespace(content="   ")),
            pytest.raises(ValueError, match="Kreuzberg returned empty content"),
        ):
            parse_with_kreuzberg(sample, "application/msword")

    def test_falls_back_when_output_format_is_unsupported(self, tmp_path: Path) -> None:
        sample = tmp_path / "legacy.doc"
        sample.write_text("dummy", encoding="utf-8")

        cfg = object()
        result = SimpleNamespace(content="plain text")
        config_side_effect = [TypeError("old API"), cfg]

        with (
            patch("kreuzberg.ExtractionConfig", side_effect=config_side_effect) as mock_config,
            patch("kreuzberg.extract_file_sync", return_value=result) as mock_extract,
        ):
            text = parse_with_kreuzberg(sample, "application/msword")

        assert text == "plain text"
        assert mock_config.call_args_list == [call(output_format="markdown"), call()]
        mock_extract.assert_called_once_with(str(sample), "application/msword", config=cfg)
