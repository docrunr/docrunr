"""Tests for parser converter helpers."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from docrunr.parsers._converters import (
    _ensure_tessdata_prefix,
    parse_image_with_tesseract,
    parse_with_kreuzberg,
    preprocess_image_for_ocr,
)
from PIL import Image, ImageDraw


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


def _png_info(data: bytes) -> tuple[tuple[int, int], str]:
    with Image.open(BytesIO(data)) as img:
        return img.size, img.mode


def _save_rgb(
    path: Path, size: tuple[int, int], color: tuple[int, int, int] = (255, 255, 255)
) -> None:
    Image.new("RGB", size, color).save(path)


class TestTessdataPrefix:
    def test_does_not_overwrite_existing_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESSDATA_PREFIX", "/already/set")
        assert _ensure_tessdata_prefix() == "/already/set"

    def test_skips_directory_without_traineddata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
        empty = tmp_path / "empty"
        empty.mkdir()
        good = tmp_path / "good"
        good.mkdir()
        (good / "eng.traineddata").write_bytes(b"data")

        with patch("docrunr.parsers._converters._TESSDATA_CANDIDATES", (empty, good)):
            assert _ensure_tessdata_prefix() == str(good)

    def test_returns_none_when_no_traineddata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
        empty = tmp_path / "empty"
        empty.mkdir()
        with patch("docrunr.parsers._converters._TESSDATA_CANDIDATES", (empty,)):
            assert _ensure_tessdata_prefix() is None


class TestImagePreprocess:
    def test_converts_to_grayscale(self, tmp_path: Path) -> None:
        sample = tmp_path / "color.png"
        _save_rgb(sample, (80, 60), (12, 34, 200))
        size, mode = _png_info(preprocess_image_for_ocr(sample))
        assert mode == "L"
        assert size == (160, 120)

    def test_flattens_alpha_onto_white(self, tmp_path: Path) -> None:
        sample = tmp_path / "alpha.png"
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((8, 8, 23, 23), fill=(10, 10, 10, 255))
        img.save(sample)

        data = preprocess_image_for_ocr(sample)
        with Image.open(BytesIO(data)) as out:
            assert out.mode == "L"
            assert out.getpixel((0, 0)) == 255
            assert out.getpixel((32, 32)) < 40

    def test_upscales_small_images_2x(self, tmp_path: Path) -> None:
        sample = tmp_path / "small.png"
        _save_rgb(sample, (400, 200))
        size, _mode = _png_info(preprocess_image_for_ocr(sample))
        assert size == (800, 400)

    def test_does_not_upscale_large_images(self, tmp_path: Path) -> None:
        sample = tmp_path / "large.png"
        _save_rgb(sample, (1200, 800))
        size, _mode = _png_info(preprocess_image_for_ocr(sample))
        assert size == (1200, 800)

    def test_does_not_downscale_large_scans(self, tmp_path: Path) -> None:
        sample = tmp_path / "scan.png"
        _save_rgb(sample, (2400, 3200))
        size, _mode = _png_info(preprocess_image_for_ocr(sample))
        assert size == (2400, 3200)

    def test_caps_upscale_factor_at_2000px(self, tmp_path: Path) -> None:
        sample = tmp_path / "banner.png"
        _save_rgb(sample, (1800, 200))
        size, _mode = _png_info(preprocess_image_for_ocr(sample))
        assert size == (2000, 222)


class TestTesseractImageConverter:
    def test_calls_extract_bytes_sync_with_tesseract_ocr(self, tmp_path: Path) -> None:
        sample = tmp_path / "shot.png"
        _save_rgb(sample, (64, 48))
        cfg = object()
        result = SimpleNamespace(content="Hello OCR")

        with (
            patch("kreuzberg.OcrConfig", return_value="ocr") as mock_ocr,
            patch("kreuzberg.ExtractionConfig", return_value=cfg) as mock_config,
            patch("kreuzberg.extract_bytes_sync", return_value=result) as mock_extract,
        ):
            text = parse_image_with_tesseract(sample)

        assert text == "Hello OCR"
        mock_ocr.assert_called_once_with(backend="tesseract", language="eng+nld")
        mock_config.assert_called_once_with(output_format="markdown", ocr="ocr")
        args, kwargs = mock_extract.call_args
        assert args[1] == "image/png"
        assert kwargs["config"] is cfg
        assert isinstance(args[0], bytes)
        assert args[0].startswith(b"\x89PNG\r\n\x1a\n")

    def test_raises_on_empty_tesseract_output(self, tmp_path: Path) -> None:
        sample = tmp_path / "shot.png"
        _save_rgb(sample, (64, 48))

        with (
            patch("kreuzberg.OcrConfig", return_value="ocr"),
            patch("kreuzberg.ExtractionConfig", return_value=object()),
            patch("kreuzberg.extract_bytes_sync", return_value=SimpleNamespace(content="   ")),
            pytest.raises(ValueError, match="Tesseract OCR returned empty content"),
        ):
            parse_image_with_tesseract(sample)
